"""
研究工作流引擎
参考DeerFlow的LangGraph工作流设计，实现状态驱动的研究流程
"""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Callable, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from .state import ResearchState, ResearchPhase, ResearchTask
from .models import WorkflowConfig, WorkflowEvent, WorkflowTransition
from ..core.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    """工作流状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransitionCondition(Enum):
    """转换条件"""
    ALWAYS = "always"
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    ON_CONDITION = "on_condition"
    ON_TIMEOUT = "on_timeout"
    MANUAL = "manual"


@dataclass
class WorkflowNode:
    """工作流节点"""
    node_id: str
    name: str
    description: str
    phase: ResearchPhase
    handler: Callable
    timeout: Optional[int] = None
    retry_count: int = 0
    max_retries: int = 3
    conditions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowEdge:
    """工作流边"""
    source_node: str
    target_node: str
    condition: TransitionCondition
    condition_data: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0


@dataclass
class WorkflowExecution:
    """工作流执行实例"""
    execution_id: str
    session_id: str
    workflow_id: str
    status: WorkflowStatus
    current_node: Optional[str] = None
    state: Optional[ResearchState] = None
    context: Dict[str, Any] = field(default_factory=dict)
    events: List[WorkflowEvent] = field(default_factory=list)
    transitions: List[WorkflowTransition] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class WorkflowEngine:
    """工作流引擎
    
    基于状态图的研究工作流执行引擎：
    1. 工作流定义和管理
    2. 状态转换控制
    3. 事件驱动执行
    4. 异常处理和恢复
    5. 流程监控和日志
    """
    
    def __init__(self):
        self.workflows: Dict[str, ResearchWorkflow] = {}
        self.executions: Dict[str, WorkflowExecution] = {}
        self.orchestrator = None  # Lazy initialized
        self.llm_service = LLMService()
        self._running = False
        self._event_queue = asyncio.Queue()
        
    async def initialize(self):
        """初始化工作流引擎"""
        # Lazy import to avoid circular dependency
        if self.orchestrator is None:
            from ..agents.orchestrator import ResearchOrchestrator
            self.orchestrator = ResearchOrchestrator()
        
        await self.orchestrator.initialize()
        
        # 注册默认工作流
        await self._register_default_workflows()
        
        # 启动事件处理器
        await self._start_event_processor()
        
        self._running = True
        logger.info("Workflow engine initialized")
    
    async def register_workflow(self, workflow: 'ResearchWorkflow'):
        """注册工作流"""
        self.workflows[workflow.workflow_id] = workflow
        logger.info(f"Workflow registered: {workflow.workflow_id}")
    
    async def start_workflow(
        self,
        workflow_id: str,
        session_id: str,
        user_id: str,
        initial_data: Dict[str, Any]
    ) -> str:
        """启动工作流"""
        
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow = self.workflows[workflow_id]
        execution_id = f"exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session_id}"
        
        # 创建执行实例
        execution = WorkflowExecution(
            execution_id=execution_id,
            session_id=session_id,
            workflow_id=workflow_id,
            status=WorkflowStatus.IDLE,
            context=initial_data.copy()
        )
        
        # 创建研究状态
        research_state = ResearchState(
            session_id=session_id,
            user_id=user_id,
            topic=initial_data.get("topic", ""),
            objective=initial_data.get("objective", ""),
            current_phase=ResearchPhase.PLANNING,
            agents=[],
            knowledge_bases=initial_data.get("knowledge_bases", []),
            mcp_tools=initial_data.get("mcp_tools", []),
            tasks=[],
            findings=[],
            final_report=None,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        execution.state = research_state
        execution.current_node = workflow.start_node
        
        self.executions[execution_id] = execution
        
        # 启动执行
        await self._start_execution(execution_id)
        
        return execution_id
    
    async def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """获取执行状态"""
        execution = self.executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        
        return {
            "execution_id": execution_id,
            "session_id": execution.session_id,
            "workflow_id": execution.workflow_id,
            "status": execution.status.value,
            "current_node": execution.current_node,
            "current_phase": execution.state.current_phase.value if execution.state else None,
            "progress": await self._calculate_progress(execution),
            "events_count": len(execution.events),
            "transitions_count": len(execution.transitions),
            "created_at": execution.created_at.isoformat(),
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "error": execution.error
        }
    
    async def pause_execution(self, execution_id: str) -> bool:
        """暂停执行"""
        execution = self.executions.get(execution_id)
        if not execution or execution.status != WorkflowStatus.RUNNING:
            return False
        
        execution.status = WorkflowStatus.PAUSED
        
        # 暂停底层编排器
        await self.orchestrator.pause_session(execution.session_id)
        
        await self._emit_event(execution_id, "execution_paused", {})
        
        return True
    
    async def resume_execution(self, execution_id: str) -> bool:
        """恢复执行"""
        execution = self.executions.get(execution_id)
        if not execution or execution.status != WorkflowStatus.PAUSED:
            return False
        
        execution.status = WorkflowStatus.RUNNING
        
        # 恢复底层编排器
        await self.orchestrator.resume_session(execution.session_id)
        
        await self._emit_event(execution_id, "execution_resumed", {})
        
        return True
    
    async def cancel_execution(self, execution_id: str) -> bool:
        """取消执行"""
        execution = self.executions.get(execution_id)
        if not execution:
            return False
        
        execution.status = WorkflowStatus.CANCELLED
        execution.completed_at = datetime.now()
        
        # 取消底层编排器
        await self.orchestrator.cancel_session(execution.session_id)
        
        await self._emit_event(execution_id, "execution_cancelled", {})
        
        return True
    
    async def get_execution_result(self, execution_id: str) -> Dict[str, Any]:
        """获取执行结果"""
        execution = self.executions.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")
        
        # 获取底层结果
        orchestrator_results = await self.orchestrator.get_session_results(execution.session_id)
        
        return {
            "execution_info": {
                "execution_id": execution_id,
                "workflow_id": execution.workflow_id,
                "status": execution.status.value,
                "duration": (
                    (execution.completed_at - execution.started_at).total_seconds()
                    if execution.started_at and execution.completed_at else None
                )
            },
            "research_state": execution.state.__dict__ if execution.state else None,
            "workflow_events": [event.__dict__ for event in execution.events],
            "workflow_transitions": [trans.__dict__ for trans in execution.transitions],
            "orchestrator_results": orchestrator_results
        }
    
    async def _start_execution(self, execution_id: str):
        """开始执行工作流"""
        execution = self.executions[execution_id]
        workflow = self.workflows[execution.workflow_id]
        
        execution.status = WorkflowStatus.RUNNING
        execution.started_at = datetime.now()
        
        try:
            await self._emit_event(execution_id, "execution_started", {})
            
            # 执行工作流
            await self._execute_workflow(execution_id)
            
            if execution.status == WorkflowStatus.RUNNING:
                execution.status = WorkflowStatus.COMPLETED
                execution.completed_at = datetime.now()
                await self._emit_event(execution_id, "execution_completed", {})
            
        except Exception as e:
            execution.status = WorkflowStatus.FAILED
            execution.completed_at = datetime.now()
            execution.error = str(e)
            
            logger.error(f"Workflow execution failed: {e}")
            await self._emit_event(execution_id, "execution_failed", {"error": str(e)})
    
    async def _execute_workflow(self, execution_id: str):
        """执行工作流"""
        execution = self.executions[execution_id]
        workflow = self.workflows[execution.workflow_id]
        
        current_node_id = execution.current_node
        
        while current_node_id and execution.status == WorkflowStatus.RUNNING:
            
            # 获取当前节点
            current_node = workflow.nodes.get(current_node_id)
            if not current_node:
                raise ValueError(f"Node {current_node_id} not found in workflow")
            
            # 执行节点
            result = await self._execute_node(execution_id, current_node)
            
            # 记录转换
            await self._emit_event(execution_id, "node_executed", {
                "node_id": current_node_id,
                "node_name": current_node.name,
                "result": result
            })
            
            # 确定下一个节点
            next_node_id = await self._determine_next_node(execution_id, current_node_id, result)
            
            if next_node_id:
                # 记录状态转换
                transition = WorkflowTransition(
                    transition_id=f"trans_{len(execution.transitions) + 1}",
                    execution_id=execution_id,
                    from_node=current_node_id,
                    to_node=next_node_id,
                    condition_met="success" if result.get("success") else "failure",
                    timestamp=datetime.now().isoformat(),
                    metadata={"result": result}
                )
                execution.transitions.append(transition)
                
                # 更新当前节点
                execution.current_node = next_node_id
                current_node_id = next_node_id
                
                await self._emit_event(execution_id, "node_transition", {
                    "from_node": transition.from_node,
                    "to_node": transition.to_node,
                    "condition": transition.condition_met
                })
            else:
                # 工作流结束
                break
    
    async def _execute_node(self, execution_id: str, node: WorkflowNode) -> Dict[str, Any]:
        """执行工作流节点"""
        execution = self.executions[execution_id]
        
        try:
            # 更新研究状态的当前阶段
            if execution.state:
                execution.state.current_phase = node.phase
                execution.state.updated_at = datetime.now().isoformat()
            
            # 准备节点执行上下文
            node_context = {
                "execution_id": execution_id,
                "session_id": execution.session_id,
                "node_id": node.node_id,
                "state": execution.state,
                "context": execution.context,
                "orchestrator": self.orchestrator
            }
            
            # 执行节点处理器
            if asyncio.iscoroutinefunction(node.handler):
                result = await node.handler(node_context)
            else:
                result = node.handler(node_context)
            
            return result if isinstance(result, dict) else {"success": True, "result": result}
            
        except Exception as e:
            logger.error(f"Node execution failed: {node.node_id}, error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _determine_next_node(
        self, 
        execution_id: str, 
        current_node_id: str, 
        result: Dict[str, Any]
    ) -> Optional[str]:
        """确定下一个节点"""
        execution = self.executions[execution_id]
        workflow = self.workflows[execution.workflow_id]
        
        # 查找从当前节点出发的边
        outgoing_edges = [
            edge for edge in workflow.edges 
            if edge.source_node == current_node_id
        ]
        
        if not outgoing_edges:
            return None  # 工作流结束
        
        # 按优先级排序边
        outgoing_edges.sort(key=lambda e: e.weight, reverse=True)
        
        # 评估转换条件
        for edge in outgoing_edges:
            if await self._evaluate_transition_condition(execution_id, edge, result):
                return edge.target_node
        
        return None  # 没有满足条件的转换
    
    async def _evaluate_transition_condition(
        self,
        execution_id: str,
        edge: WorkflowEdge,
        result: Dict[str, Any]
    ) -> bool:
        """评估转换条件"""
        
        if edge.condition == TransitionCondition.ALWAYS:
            return True
        elif edge.condition == TransitionCondition.ON_SUCCESS:
            return result.get("success", False)
        elif edge.condition == TransitionCondition.ON_FAILURE:
            return not result.get("success", False)
        elif edge.condition == TransitionCondition.ON_CONDITION:
            # 评估自定义条件
            condition_expr = edge.condition_data.get("expression", "")
            return await self._evaluate_custom_condition(execution_id, condition_expr, result)
        elif edge.condition == TransitionCondition.MANUAL:
            # 需要人工干预
            return await self._check_manual_approval(execution_id, edge)
        else:
            return False
    
    async def _evaluate_custom_condition(
        self,
        execution_id: str,
        condition_expr: str,
        result: Dict[str, Any]
    ) -> bool:
        """评估自定义条件"""
        # 简单的条件评估实现
        # 在实际项目中可以使用更复杂的表达式引擎
        
        if not condition_expr:
            return True
        
        # 示例条件格式: "result.findings_count > 5"
        try:
            # 构建评估上下文
            context = {
                "result": result,
                "execution": self.executions[execution_id]
            }
            
            # 简单的条件检查
            if "findings_count" in condition_expr:
                findings_count = len(result.get("findings", []))
                if "> 5" in condition_expr:
                    return findings_count > 5
                elif ">= 3" in condition_expr:
                    return findings_count >= 3
            
            return True
            
        except Exception as e:
            logger.error(f"Condition evaluation failed: {e}")
            return False
    
    async def _check_manual_approval(self, execution_id: str, edge: WorkflowEdge) -> bool:
        """检查人工审批"""
        # 在实际项目中，这里会等待人工审批
        # 当前返回True表示自动通过
        return True
    
    async def _calculate_progress(self, execution: WorkflowExecution) -> float:
        """计算执行进度"""
        workflow = self.workflows[execution.workflow_id]
        total_nodes = len(workflow.nodes)
        
        if total_nodes == 0:
            return 0.0
        
        # 根据已执行的节点数计算进度
        executed_nodes = len(set(trans.from_node for trans in execution.transitions))
        
        if execution.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED]:
            return 1.0
        
        return executed_nodes / total_nodes
    
    async def _emit_event(self, execution_id: str, event_type: str, data: Dict[str, Any]):
        """发出工作流事件"""
        execution = self.executions[execution_id]
        
        event = WorkflowEvent(
            event_id=f"event_{len(execution.events) + 1}",
            execution_id=execution_id,
            event_type=event_type,
            timestamp=datetime.now().isoformat(),
            data=data
        )
        
        execution.events.append(event)
        await self._event_queue.put(event)
    
    async def _start_event_processor(self):
        """启动事件处理器"""
        
        async def processor():
            while self._running:
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                    await self._process_workflow_event(event)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Event processing error: {e}")
        
        asyncio.create_task(processor())
    
    async def _process_workflow_event(self, event: WorkflowEvent):
        """处理工作流事件"""
        # 可以在这里添加事件处理逻辑
        # 比如通知外部系统、更新状态、触发其他操作等
        
        logger.debug(f"Processing workflow event: {event.event_type} for {event.execution_id}")
        
        # 示例：记录关键事件
        if event.event_type in ["execution_started", "execution_completed", "execution_failed"]:
            logger.info(f"Workflow event: {event.event_type} - {event.data}")
    
    async def _register_default_workflows(self):
        """注册默认工作流"""
        
        # 创建标准研究工作流
        standard_workflow = await self._create_standard_research_workflow()
        await self.register_workflow(standard_workflow)
        
        # 创建快速研究工作流
        quick_workflow = await self._create_quick_research_workflow()
        await self.register_workflow(quick_workflow)
        
        # 创建深度研究工作流
        deep_workflow = await self._create_deep_research_workflow()
        await self.register_workflow(deep_workflow)
    
    async def _create_standard_research_workflow(self) -> 'ResearchWorkflow':
        """创建标准研究工作流"""
        
        workflow = ResearchWorkflow(
            workflow_id="standard_research",
            name="标准研究工作流",
            description="适用于大多数研究场景的标准工作流",
            version="1.0"
        )
        
        # 添加节点
        workflow.add_node(WorkflowNode(
            node_id="planning",
            name="研究规划",
            description="分析研究目标，制定研究计划",
            phase=ResearchPhase.PLANNING,
            handler=self._planning_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="research",
            name="信息收集",
            description="执行信息收集和研究任务",
            phase=ResearchPhase.RESEARCH,
            handler=self._research_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="analysis",
            name="深度分析",
            description="分析研究发现，生成洞察",
            phase=ResearchPhase.ANALYSIS,
            handler=self._analysis_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="reporting",
            name="报告生成",
            description="生成最终研究报告",
            phase=ResearchPhase.REPORTING,
            handler=self._reporting_handler
        ))
        
        # 添加边
        workflow.add_edge(WorkflowEdge(
            source_node="planning",
            target_node="research",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.add_edge(WorkflowEdge(
            source_node="research",
            target_node="analysis",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.add_edge(WorkflowEdge(
            source_node="analysis",
            target_node="reporting",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.start_node = "planning"
        workflow.end_nodes = ["reporting"]
        
        return workflow
    
    async def _create_quick_research_workflow(self) -> 'ResearchWorkflow':
        """创建快速研究工作流"""
        
        workflow = ResearchWorkflow(
            workflow_id="quick_research",
            name="快速研究工作流",
            description="用于快速获取研究结果的简化工作流",
            version="1.0"
        )
        
        # 添加节点（简化版）
        workflow.add_node(WorkflowNode(
            node_id="quick_planning",
            name="快速规划",
            description="简化的研究规划",
            phase=ResearchPhase.PLANNING,
            handler=self._quick_planning_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="quick_research",
            name="快速研究",
            description="并行执行研究和分析",
            phase=ResearchPhase.RESEARCH,
            handler=self._quick_research_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="quick_reporting",
            name="快速报告",
            description="生成简化报告",
            phase=ResearchPhase.REPORTING,
            handler=self._quick_reporting_handler
        ))
        
        # 添加边
        workflow.add_edge(WorkflowEdge(
            source_node="quick_planning",
            target_node="quick_research",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.add_edge(WorkflowEdge(
            source_node="quick_research",
            target_node="quick_reporting",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.start_node = "quick_planning"
        workflow.end_nodes = ["quick_reporting"]
        
        return workflow
    
    async def _create_deep_research_workflow(self) -> 'ResearchWorkflow':
        """创建深度研究工作流"""
        
        workflow = ResearchWorkflow(
            workflow_id="deep_research",
            name="深度研究工作流",
            description="用于复杂研究任务的深度工作流",
            version="1.0"
        )
        
        # 添加节点（扩展版）
        workflow.add_node(WorkflowNode(
            node_id="initial_planning",
            name="初始规划",
            description="初步研究规划",
            phase=ResearchPhase.PLANNING,
            handler=self._planning_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="preliminary_research",
            name="初步研究",
            description="初步信息收集",
            phase=ResearchPhase.RESEARCH,
            handler=self._research_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="plan_refinement",
            name="计划优化",
            description="基于初步发现优化研究计划",
            phase=ResearchPhase.PLANNING,
            handler=self._plan_refinement_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="deep_research",
            name="深度研究",
            description="深入信息收集和研究",
            phase=ResearchPhase.RESEARCH,
            handler=self._deep_research_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="comprehensive_analysis",
            name="综合分析",
            description="全面分析和洞察生成",
            phase=ResearchPhase.ANALYSIS,
            handler=self._comprehensive_analysis_handler
        ))
        
        workflow.add_node(WorkflowNode(
            node_id="final_reporting",
            name="最终报告",
            description="生成详细研究报告",
            phase=ResearchPhase.REPORTING,
            handler=self._reporting_handler
        ))
        
        # 添加边（包含反馈循环）
        workflow.add_edge(WorkflowEdge(
            source_node="initial_planning",
            target_node="preliminary_research",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.add_edge(WorkflowEdge(
            source_node="preliminary_research",
            target_node="plan_refinement",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.add_edge(WorkflowEdge(
            source_node="plan_refinement",
            target_node="deep_research",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.add_edge(WorkflowEdge(
            source_node="deep_research",
            target_node="comprehensive_analysis",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        workflow.add_edge(WorkflowEdge(
            source_node="comprehensive_analysis",
            target_node="final_reporting",
            condition=TransitionCondition.ON_SUCCESS
        ))
        
        # 反馈边：如果初步研究发现不足，回到规划阶段
        workflow.add_edge(WorkflowEdge(
            source_node="preliminary_research",
            target_node="initial_planning",
            condition=TransitionCondition.ON_CONDITION,
            condition_data={"expression": "result.findings_count < 3"},
            weight=0.5
        ))
        
        workflow.start_node = "initial_planning"
        workflow.end_nodes = ["final_reporting"]
        
        return workflow
    
    # 节点处理器实现
    async def _planning_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """规划阶段处理器"""
        session_id = context["session_id"]
        
        # 启动底层编排器的研究
        await self.orchestrator.start_research(
            user_id=context["state"].user_id,
            topic=context["state"].topic,
            objective=context["state"].objective,
            knowledge_bases=context["state"].knowledge_bases,
            mcp_tools=context["state"].mcp_tools,
            strategy="adaptive"
        )
        
        # 等待规划阶段完成
        await asyncio.sleep(2)  # 给编排器一些时间来处理
        
        # 获取规划结果
        session_status = await self.orchestrator.get_session_status(session_id)
        
        return {
            "success": True,
            "phase": "planning",
            "session_status": session_status
        }
    
    async def _research_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """研究阶段处理器"""
        session_id = context["session_id"]
        
        # 等待研究阶段完成
        max_wait_time = 300  # 5分钟超时
        wait_time = 0
        
        while wait_time < max_wait_time:
            session_status = await self.orchestrator.get_session_status(session_id)
            
            if session_status.get("current_phase") in ["analysis", "reporting", "completed"]:
                break
            
            await asyncio.sleep(10)
            wait_time += 10
        
        # 获取研究结果
        research_state = await self.orchestrator.get_research_state(session_id)
        findings_count = len(research_state.findings) if research_state else 0
        
        return {
            "success": True,
            "phase": "research",
            "findings_count": findings_count,
            "findings": research_state.findings if research_state else []
        }
    
    async def _analysis_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """分析阶段处理器"""
        session_id = context["session_id"]
        
        # 等待分析阶段完成
        max_wait_time = 180  # 3分钟超时
        wait_time = 0
        
        while wait_time < max_wait_time:
            session_status = await self.orchestrator.get_session_status(session_id)
            
            if session_status.get("current_phase") in ["reporting", "completed"]:
                break
            
            await asyncio.sleep(5)
            wait_time += 5
        
        return {
            "success": True,
            "phase": "analysis"
        }
    
    async def _reporting_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """报告阶段处理器"""
        session_id = context["session_id"]
        
        # 等待报告阶段完成
        max_wait_time = 120  # 2分钟超时
        wait_time = 0
        
        while wait_time < max_wait_time:
            session_status = await self.orchestrator.get_session_status(session_id)
            
            if session_status.get("current_phase") == "completed":
                break
            
            await asyncio.sleep(5)
            wait_time += 5
        
        # 获取最终结果
        results = await self.orchestrator.get_session_results(session_id)
        
        return {
            "success": True,
            "phase": "reporting",
            "final_report": results.get("final_report"),
            "results": results
        }
    
    # 特殊处理器
    async def _quick_planning_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """快速规划处理器"""
        # 简化的规划逻辑
        return await self._planning_handler(context)
    
    async def _quick_research_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """快速研究处理器"""
        # 并行执行研究和分析
        research_result = await self._research_handler(context)
        analysis_result = await self._analysis_handler(context)
        
        return {
            "success": True,
            "phase": "quick_research",
            "research_result": research_result,
            "analysis_result": analysis_result
        }
    
    async def _quick_reporting_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """快速报告处理器"""
        # 生成简化报告
        return await self._reporting_handler(context)
    
    async def _plan_refinement_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """计划优化处理器"""
        # 基于初步发现优化计划
        return {
            "success": True,
            "phase": "plan_refinement",
            "refined_plan": "优化后的研究计划"
        }
    
    async def _deep_research_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """深度研究处理器"""
        # 更深入的研究逻辑
        return await self._research_handler(context)
    
    async def _comprehensive_analysis_handler(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """综合分析处理器"""
        # 更全面的分析逻辑
        return await self._analysis_handler(context)
    
    async def shutdown(self):
        """关闭工作流引擎"""
        self._running = False
        
        # 取消所有执行中的工作流
        for execution_id in list(self.executions.keys()):
            await self.cancel_execution(execution_id)
        
        await self.orchestrator.shutdown()
        logger.info("Workflow engine shutdown")


class ResearchWorkflow:
    """研究工作流定义"""
    
    def __init__(
        self,
        workflow_id: str,
        name: str,
        description: str,
        version: str = "1.0"
    ):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.version = version
        self.nodes: Dict[str, WorkflowNode] = {}
        self.edges: List[WorkflowEdge] = []
        self.start_node: Optional[str] = None
        self.end_nodes: List[str] = []
        self.config: Optional[WorkflowConfig] = None
        self.metadata: Dict[str, Any] = {}
    
    def add_node(self, node: WorkflowNode):
        """添加节点"""
        self.nodes[node.node_id] = node
    
    def add_edge(self, edge: WorkflowEdge):
        """添加边"""
        self.edges.append(edge)
    
    def validate(self) -> bool:
        """验证工作流定义"""
        # 检查开始节点
        if not self.start_node or self.start_node not in self.nodes:
            return False
        
        # 检查结束节点
        if not self.end_nodes or not all(node in self.nodes for node in self.end_nodes):
            return False
        
        # 检查边的有效性
        for edge in self.edges:
            if (edge.source_node not in self.nodes or 
                edge.target_node not in self.nodes):
                return False
        
        return True
    
    def get_next_nodes(self, node_id: str) -> List[str]:
        """获取下一个节点"""
        return [edge.target_node for edge in self.edges if edge.source_node == node_id]
    
    def get_previous_nodes(self, node_id: str) -> List[str]:
        """获取前一个节点"""
        return [edge.source_node for edge in self.edges if edge.target_node == node_id]