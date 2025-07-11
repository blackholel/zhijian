"""
多Agent协作编排器
参考DeerFlow的工作流编排设计，实现智能体间的协调和调度
"""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field

from .manager import AgentManager
from .base.agent import BaseAgent, AgentConfig, AgentType
from .core.coordinator import CoordinatorAgent
from .core.researcher import ResearcherAgent
from .core.analyzer import AnalyzerAgent
from .core.reporter import ReporterAgent
from ..research.state import ResearchState, ResearchPhase, ResearchTask
from ..core.llm.llm_service import LLMService
from ..auth.services.permission_service import PermissionService

logger = logging.getLogger(__name__)


class OrchestrationStrategy(Enum):
    """编排策略"""
    SEQUENTIAL = "sequential"      # 顺序执行
    PARALLEL = "parallel"         # 并行执行
    PIPELINE = "pipeline"         # 流水线执行
    ADAPTIVE = "adaptive"         # 自适应执行
    EVENT_DRIVEN = "event_driven" # 事件驱动


class ExecutionState(Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentExecutionContext:
    """Agent执行上下文"""
    agent_id: str
    agent_type: AgentType
    task_id: str
    input_data: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: ExecutionState = ExecutionState.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class OrchestrationSession:
    """编排会话"""
    session_id: str
    user_id: str
    topic: str
    objective: str
    strategy: OrchestrationStrategy
    knowledge_bases: List[str]
    mcp_tools: List[str]
    agents: Dict[str, BaseAgent] = field(default_factory=dict)
    execution_contexts: List[AgentExecutionContext] = field(default_factory=list)
    state: ResearchState = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    status: ExecutionState = ExecutionState.PENDING


class ResearchOrchestrator:
    """研究编排器
    
    负责多Agent协作的整体调度和管理：
    1. 会话管理
    2. Agent生命周期管理
    3. 任务调度和依赖管理
    4. 执行监控和错误处理
    5. 结果聚合和流转
    """
    
    def __init__(self):
        self.agent_manager = AgentManager()
        self.llm_service = LLMService()
        # TODO: 正确初始化权限服务，暂时设为None
        self.permission_service = None  # PermissionService()
        self.active_sessions: Dict[str, OrchestrationSession] = {}
        self.execution_queue = asyncio.Queue()
        self.event_bus = asyncio.Queue()
        self._running = False
        
    async def initialize(self):
        """初始化编排器"""
        # 启动后台执行器
        await self._start_background_executor()
        
        # 启动事件处理器
        await self._start_event_processor()
        
        logger.info("Research orchestrator initialized")
    
    async def start_research(
        self,
        user_id: str,
        topic: str,
        objective: str,
        knowledge_bases: List[str],
        mcp_tools: List[str],
        strategy: str = "adaptive"
    ) -> str:
        """启动研究"""
        
        # 创建会话
        session = await self._create_session(
            user_id, topic, objective, knowledge_bases, mcp_tools, strategy
        )
        
        # 创建协调器Agent
        coordinator = await self._create_coordinator_agent(session)
        session.agents["coordinator"] = coordinator
        
        # 开始编排流程
        await self._start_orchestration(session)
        
        return session.session_id
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """获取会话状态"""
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # 计算进度
        total_contexts = len(session.execution_contexts)
        completed_contexts = len([
            ctx for ctx in session.execution_contexts 
            if ctx.status == ExecutionState.COMPLETED
        ])
        progress = completed_contexts / max(total_contexts, 1)
        
        return {
            "session_id": session_id,
            "status": session.status.value,
            "topic": session.topic,
            "objective": session.objective,
            "progress": progress,
            "total_tasks": total_contexts,
            "completed_tasks": completed_contexts,
            "current_phase": session.state.current_phase.value if session.state else "unknown",
            "agents_count": len(session.agents),
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        }
    
    async def pause_session(self, session_id: str) -> bool:
        """暂停会话"""
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        
        session.status = ExecutionState.PAUSED
        session.updated_at = datetime.now()
        
        # 暂停所有运行中的任务
        for context in session.execution_contexts:
            if context.status == ExecutionState.RUNNING:
                context.status = ExecutionState.PAUSED
        
        await self._emit_event({
            "type": "session_paused",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        })
        
        return True
    
    async def resume_session(self, session_id: str) -> bool:
        """恢复会话"""
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        
        session.status = ExecutionState.RUNNING
        session.updated_at = datetime.now()
        
        # 恢复暂停的任务
        for context in session.execution_contexts:
            if context.status == ExecutionState.PAUSED:
                context.status = ExecutionState.PENDING
                await self.execution_queue.put(context)
        
        await self._emit_event({
            "type": "session_resumed",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        })
        
        return True
    
    async def cancel_session(self, session_id: str) -> bool:
        """取消会话"""
        session = self.active_sessions.get(session_id)
        if not session:
            return False
        
        session.status = ExecutionState.CANCELLED
        session.updated_at = datetime.now()
        
        # 取消所有任务
        for context in session.execution_contexts:
            if context.status in [ExecutionState.PENDING, ExecutionState.RUNNING, ExecutionState.PAUSED]:
                context.status = ExecutionState.CANCELLED
        
        await self._emit_event({
            "type": "session_cancelled",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        })
        
        return True
    
    async def get_research_state(self, session_id: str) -> Optional[ResearchState]:
        """获取研究状态"""
        session = self.active_sessions.get(session_id)
        return session.state if session else None
    
    async def get_session_results(self, session_id: str) -> Dict[str, Any]:
        """获取会话结果"""
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # 收集所有执行结果
        results = {
            "session_info": {
                "session_id": session_id,
                "topic": session.topic,
                "objective": session.objective,
                "status": session.status.value
            },
            "execution_results": [],
            "research_state": session.state.__dict__ if session.state else None,
            "final_report": None
        }
        
        for context in session.execution_contexts:
            if context.result:
                results["execution_results"].append({
                    "agent_type": context.agent_type.value,
                    "task_id": context.task_id,
                    "status": context.status.value,
                    "result": context.result,
                    "execution_time": (
                        (context.end_time - context.start_time).total_seconds()
                        if context.start_time and context.end_time else None
                    )
                })
        
        # 查找最终报告
        reporter_results = [
            r for r in results["execution_results"] 
            if r["agent_type"] == "reporter"
        ]
        if reporter_results:
            results["final_report"] = reporter_results[-1]["result"]
        
        return results
    
    async def _create_session(
        self,
        user_id: str,
        topic: str,
        objective: str,
        knowledge_bases: List[str],
        mcp_tools: List[str],
        strategy: str
    ) -> OrchestrationSession:
        """创建编排会话"""
        
        session_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id}"
        
        # 创建研究状态
        research_state = ResearchState(
            session_id=session_id,
            user_id=user_id,
            topic=topic,
            objective=objective,
            current_phase=ResearchPhase.PLANNING,
            agents=[],
            knowledge_bases=knowledge_bases,
            mcp_tools=mcp_tools,
            tasks=[],
            findings=[],
            final_report=None,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        session = OrchestrationSession(
            session_id=session_id,
            user_id=user_id,
            topic=topic,
            objective=objective,
            strategy=OrchestrationStrategy(strategy),
            knowledge_bases=knowledge_bases,
            mcp_tools=mcp_tools,
            state=research_state
        )
        
        self.active_sessions[session_id] = session
        
        await self._emit_event({
            "type": "session_created",
            "session_id": session_id,
            "user_id": user_id,
            "topic": topic,
            "timestamp": datetime.now().isoformat()
        })
        
        return session
    
    async def _create_coordinator_agent(self, session: OrchestrationSession) -> CoordinatorAgent:
        """创建协调器Agent"""
        
        config = AgentConfig(
            agent_id=f"coordinator_{session.session_id}",
            agent_type=AgentType.COORDINATOR,
            name="研究协调器",
            description="负责研究任务的分解和协调",
            capabilities=[],
            selected_knowledge_bases=session.knowledge_bases,
            selected_mcp_tools=session.mcp_tools,
            llm_config={},
            prompt_templates={},
            user_id=session.user_id,
            organization_id="",
            agent_config={
                "coordination_strategy": session.strategy.value
            }
        )
        
        coordinator = await self.agent_manager.create_agent(config)
        session.state.agents.append(config.agent_id)
        
        return coordinator
    
    async def _start_orchestration(self, session: OrchestrationSession):
        """开始编排流程"""
        
        session.status = ExecutionState.RUNNING
        
        try:
            # 第一阶段：规划
            await self._execute_planning_phase(session)
            
            # 第二阶段：研究
            await self._execute_research_phase(session)
            
            # 第三阶段：分析
            await self._execute_analysis_phase(session)
            
            # 第四阶段：报告
            await self._execute_reporting_phase(session)
            
            session.status = ExecutionState.COMPLETED
            session.state.current_phase = ResearchPhase.COMPLETED
            
        except Exception as e:
            logger.error(f"Orchestration failed for session {session.session_id}: {e}")
            session.status = ExecutionState.FAILED
            
            await self._emit_event({
                "type": "session_failed",
                "session_id": session.session_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        
        finally:
            session.updated_at = datetime.now()
    
    async def _execute_planning_phase(self, session: OrchestrationSession):
        """执行规划阶段"""
        
        session.state.current_phase = ResearchPhase.PLANNING
        
        coordinator = session.agents["coordinator"]
        
        # 创建规划任务上下文
        planning_context = AgentExecutionContext(
            agent_id=coordinator.config.agent_id,
            agent_type=AgentType.COORDINATOR,
            task_id="planning_task",
            input_data={
                "task_type": "planning",
                "topic": session.topic,
                "objective": session.objective,
                "available_knowledge_bases": session.knowledge_bases,
                "available_mcp_tools": session.mcp_tools
            }
        )
        
        session.execution_contexts.append(planning_context)
        
        # 执行规划任务
        result = await self._execute_agent_task(coordinator, planning_context)
        
        if result and result.get("success"):
            # 解析规划结果，创建研究任务
            plan = result.get("plan", {})
            tasks = result.get("tasks", [])
            required_agents = result.get("required_agents", [])
            
            # 创建研究任务
            for task_data in tasks:
                research_task = ResearchTask(
                    task_id=task_data.get("task_id", ""),
                    title=task_data.get("title", ""),
                    description=task_data.get("description", ""),
                    assigned_agent=task_data.get("agent_type", "researcher"),
                    status="pending",
                    input_data=task_data,
                    output_data=None,
                    dependencies=task_data.get("dependencies", []),
                    created_at=datetime.now().isoformat()
                )
                session.state.tasks.append(research_task)
            
            # 创建所需的Agent
            await self._create_required_agents(session, required_agents)
            
            await self._emit_event({
                "type": "planning_completed",
                "session_id": session.session_id,
                "tasks_created": len(tasks),
                "agents_required": len(required_agents),
                "timestamp": datetime.now().isoformat()
            })
        else:
            raise Exception("Planning phase failed")
    
    async def _execute_research_phase(self, session: OrchestrationSession):
        """执行研究阶段"""
        
        session.state.current_phase = ResearchPhase.RESEARCH
        
        # 创建研究任务的执行上下文
        research_contexts = []
        
        for task in session.state.tasks:
            agent_type = AgentType(task.assigned_agent)
            agent = await self._get_or_create_agent(session, agent_type)
            
            context = AgentExecutionContext(
                agent_id=agent.config.agent_id,
                agent_type=agent_type,
                task_id=task.task_id,
                input_data=task.input_data,
                dependencies=task.dependencies
            )
            
            research_contexts.append(context)
            session.execution_contexts.append(context)
        
        # 根据策略执行研究任务
        if session.strategy == OrchestrationStrategy.SEQUENTIAL:
            await self._execute_sequential(session, research_contexts)
        elif session.strategy == OrchestrationStrategy.PARALLEL:
            await self._execute_parallel(session, research_contexts)
        elif session.strategy == OrchestrationStrategy.PIPELINE:
            await self._execute_pipeline(session, research_contexts)
        else:
            await self._execute_adaptive(session, research_contexts)
        
        # 更新任务状态
        for context in research_contexts:
            for task in session.state.tasks:
                if task.task_id == context.task_id:
                    task.status = context.status.value.lower()
                    task.output_data = context.result
                    if context.end_time:
                        task.completed_at = context.end_time.isoformat()
                    break
        
        # 收集研究发现
        for context in research_contexts:
            if context.result and context.result.get("success"):
                findings = context.result.get("findings", [])
                session.state.findings.extend(findings)
        
        await self._emit_event({
            "type": "research_completed",
            "session_id": session.session_id,
            "findings_collected": len(session.state.findings),
            "timestamp": datetime.now().isoformat()
        })
    
    async def _execute_analysis_phase(self, session: OrchestrationSession):
        """执行分析阶段"""
        
        session.state.current_phase = ResearchPhase.ANALYSIS
        
        # 创建或获取分析员Agent
        analyzer = await self._get_or_create_agent(session, AgentType.ANALYZER)
        
        # 创建分析任务上下文
        analysis_context = AgentExecutionContext(
            agent_id=analyzer.config.agent_id,
            agent_type=AgentType.ANALYZER,
            task_id="analysis_task",
            input_data={
                "task_type": "analysis",
                "findings": session.state.findings,
                "research_tasks": [task.__dict__ for task in session.state.tasks],
                "objectives": [session.objective]
            }
        )
        
        session.execution_contexts.append(analysis_context)
        
        # 执行分析任务
        result = await self._execute_agent_task(analyzer, analysis_context)
        
        if result and result.get("success"):
            # 添加分析洞察到发现中
            insights = result.get("insights", [])
            session.state.findings.extend(insights)
            
            await self._emit_event({
                "type": "analysis_completed",
                "session_id": session.session_id,
                "insights_generated": len(insights),
                "timestamp": datetime.now().isoformat()
            })
        else:
            logger.warning(f"Analysis phase failed for session {session.session_id}")
    
    async def _execute_reporting_phase(self, session: OrchestrationSession):
        """执行报告阶段"""
        
        session.state.current_phase = ResearchPhase.REPORTING
        
        # 创建或获取报告员Agent
        reporter = await self._get_or_create_agent(session, AgentType.REPORTER)
        
        # 创建报告任务上下文
        reporting_context = AgentExecutionContext(
            agent_id=reporter.config.agent_id,
            agent_type=AgentType.REPORTER,
            task_id="reporting_task",
            input_data={
                "task_type": "reporting",
                "topic": session.topic,
                "objective": session.objective,
                "findings": session.state.findings,
                "research_tasks": [task.__dict__ for task in session.state.tasks]
            }
        )
        
        session.execution_contexts.append(reporting_context)
        
        # 执行报告任务
        result = await self._execute_agent_task(reporter, reporting_context)
        
        if result and result.get("success"):
            # 保存最终报告
            report = result.get("report", {})
            session.state.final_report = json.dumps(report, ensure_ascii=False)
            
            await self._emit_event({
                "type": "reporting_completed",
                "session_id": session.session_id,
                "report_generated": True,
                "timestamp": datetime.now().isoformat()
            })
        else:
            logger.warning(f"Reporting phase failed for session {session.session_id}")
    
    async def _create_required_agents(self, session: OrchestrationSession, required_agents: List[str]):
        """创建所需的Agent"""
        
        for agent_type_str in required_agents:
            try:
                agent_type = AgentType(agent_type_str)
                if agent_type_str not in session.agents:
                    agent = await self._get_or_create_agent(session, agent_type)
                    session.agents[agent_type_str] = agent
                    session.state.agents.append(agent.config.agent_id)
            except ValueError:
                logger.warning(f"Unknown agent type: {agent_type_str}")
    
    async def _get_or_create_agent(self, session: OrchestrationSession, agent_type: AgentType) -> BaseAgent:
        """获取或创建Agent"""
        
        agent_key = agent_type.value
        
        if agent_key in session.agents:
            return session.agents[agent_key]
        
        # 创建新Agent
        config = AgentConfig(
            agent_id=f"{agent_key}_{session.session_id}",
            agent_type=agent_type,
            name=f"{agent_type.value.title()} Agent",
            description=f"研究{agent_type.value}智能体",
            capabilities=[],
            selected_knowledge_bases=session.knowledge_bases,
            selected_mcp_tools=session.mcp_tools,
            llm_config={},
            prompt_templates={},
            user_id=session.user_id,
            organization_id=""
        )
        
        agent = await self.agent_manager.create_agent(config)
        session.agents[agent_key] = agent
        session.state.agents.append(agent.config.agent_id)
        
        return agent
    
    async def _execute_sequential(self, session: OrchestrationSession, contexts: List[AgentExecutionContext]):
        """顺序执行"""
        
        # 按依赖关系排序
        sorted_contexts = await self._sort_by_dependencies(contexts)
        
        for context in sorted_contexts:
            if session.status != ExecutionState.RUNNING:
                break
            
            agent = session.agents.get(context.agent_type.value)
            if agent:
                await self._execute_agent_task(agent, context)
    
    async def _execute_parallel(self, session: OrchestrationSession, contexts: List[AgentExecutionContext]):
        """并行执行"""
        
        # 创建任务列表
        tasks = []
        
        for context in contexts:
            agent = session.agents.get(context.agent_type.value)
            if agent:
                task = asyncio.create_task(self._execute_agent_task(agent, context))
                tasks.append(task)
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_pipeline(self, session: OrchestrationSession, contexts: List[AgentExecutionContext]):
        """流水线执行"""
        
        # 按阶段分组
        stages = await self._group_by_stages(contexts)
        
        for stage_contexts in stages:
            if session.status != ExecutionState.RUNNING:
                break
            
            # 并行执行同一阶段的任务
            tasks = []
            for context in stage_contexts:
                agent = session.agents.get(context.agent_type.value)
                if agent:
                    task = asyncio.create_task(self._execute_agent_task(agent, context))
                    tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_adaptive(self, session: OrchestrationSession, contexts: List[AgentExecutionContext]):
        """自适应执行"""
        
        # 分析任务特征，选择最佳策略
        if len(contexts) <= 3:
            await self._execute_sequential(session, contexts)
        elif await self._has_complex_dependencies(contexts):
            await self._execute_pipeline(session, contexts)
        else:
            await self._execute_parallel(session, contexts)
    
    async def _execute_agent_task(self, agent: BaseAgent, context: AgentExecutionContext) -> Optional[Dict[str, Any]]:
        """执行Agent任务"""
        
        context.status = ExecutionState.RUNNING
        context.start_time = datetime.now()
        
        try:
            # 检查依赖
            if not await self._check_dependencies(context):
                context.status = ExecutionState.PENDING
                return None
            
            # 执行任务
            result = await agent.execute(context.input_data)
            
            context.end_time = datetime.now()
            context.result = result
            
            if result and result.get("success"):
                context.status = ExecutionState.COMPLETED
            else:
                context.status = ExecutionState.FAILED
                context.error = result.get("error", "Unknown error") if result else "No result"
            
            await self._emit_event({
                "type": "task_completed",
                "agent_type": context.agent_type.value,
                "task_id": context.task_id,
                "status": context.status.value,
                "execution_time": (context.end_time - context.start_time).total_seconds(),
                "timestamp": datetime.now().isoformat()
            })
            
            return result
            
        except Exception as e:
            context.end_time = datetime.now()
            context.status = ExecutionState.FAILED
            context.error = str(e)
            
            logger.error(f"Agent task execution failed: {e}")
            
            # 重试机制
            if context.retry_count < context.max_retries:
                context.retry_count += 1
                context.status = ExecutionState.PENDING
                await asyncio.sleep(2 ** context.retry_count)  # 指数退避
                return await self._execute_agent_task(agent, context)
            
            await self._emit_event({
                "type": "task_failed",
                "agent_type": context.agent_type.value,
                "task_id": context.task_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
            
            return None
    
    async def _check_dependencies(self, context: AgentExecutionContext) -> bool:
        """检查任务依赖"""
        
        if not context.dependencies:
            return True
        
        # 检查依赖任务是否完成
        session = None
        for sess in self.active_sessions.values():
            for ctx in sess.execution_contexts:
                if ctx.task_id == context.task_id:
                    session = sess
                    break
            if session:
                break
        
        if not session:
            return True
        
        for dep_task_id in context.dependencies:
            dep_context = None
            for ctx in session.execution_contexts:
                if ctx.task_id == dep_task_id:
                    dep_context = ctx
                    break
            
            if not dep_context or dep_context.status != ExecutionState.COMPLETED:
                return False
        
        return True
    
    async def _sort_by_dependencies(self, contexts: List[AgentExecutionContext]) -> List[AgentExecutionContext]:
        """按依赖关系排序"""
        
        # 简单的拓扑排序
        sorted_contexts = []
        remaining = contexts.copy()
        
        while remaining:
            # 找到没有依赖或依赖已满足的任务
            ready = []
            for context in remaining:
                if not context.dependencies or all(
                    any(ctx.task_id == dep_id and ctx in sorted_contexts for ctx in contexts)
                    for dep_id in context.dependencies
                ):
                    ready.append(context)
            
            if not ready:
                # 如果没有ready的任务，可能存在循环依赖，强制选择一个
                ready = [remaining[0]]
            
            sorted_contexts.extend(ready)
            for ctx in ready:
                remaining.remove(ctx)
        
        return sorted_contexts
    
    async def _group_by_stages(self, contexts: List[AgentExecutionContext]) -> List[List[AgentExecutionContext]]:
        """按阶段分组"""
        
        stages = []
        remaining = contexts.copy()
        
        while remaining:
            # 当前阶段：没有依赖或依赖已在前面阶段的任务
            current_stage = []
            completed_task_ids = set()
            
            # 收集前面阶段的任务ID
            for stage in stages:
                for ctx in stage:
                    completed_task_ids.add(ctx.task_id)
            
            for context in remaining[:]:
                if not context.dependencies or all(
                    dep_id in completed_task_ids for dep_id in context.dependencies
                ):
                    current_stage.append(context)
                    remaining.remove(context)
            
            if current_stage:
                stages.append(current_stage)
            elif remaining:
                # 如果还有剩余但无法分组，强制添加到新阶段
                stages.append([remaining.pop(0)])
        
        return stages
    
    async def _has_complex_dependencies(self, contexts: List[AgentExecutionContext]) -> bool:
        """检查是否有复杂依赖关系"""
        
        total_dependencies = sum(len(ctx.dependencies) for ctx in contexts)
        return total_dependencies > len(contexts) * 0.5
    
    async def _start_background_executor(self):
        """启动后台执行器"""
        
        async def executor():
            while self._running:
                try:
                    # 从队列获取执行上下文
                    context = await asyncio.wait_for(self.execution_queue.get(), timeout=1.0)
                    
                    # 找到对应的会话和Agent
                    session = None
                    agent = None
                    
                    for sess in self.active_sessions.values():
                        if context in sess.execution_contexts:
                            session = sess
                            agent = sess.agents.get(context.agent_type.value)
                            break
                    
                    if session and agent and session.status == ExecutionState.RUNNING:
                        await self._execute_agent_task(agent, context)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Background executor error: {e}")
        
        self._running = True
        asyncio.create_task(executor())
    
    async def _start_event_processor(self):
        """启动事件处理器"""
        
        async def processor():
            while self._running:
                try:
                    # 从事件总线获取事件
                    event = await asyncio.wait_for(self.event_bus.get(), timeout=1.0)
                    
                    # 处理事件
                    await self._process_event(event)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Event processor error: {e}")
        
        asyncio.create_task(processor())
    
    async def _emit_event(self, event: Dict[str, Any]):
        """发出事件"""
        await self.event_bus.put(event)
    
    async def _process_event(self, event: Dict[str, Any]):
        """处理事件"""
        event_type = event.get("type")
        
        if event_type == "task_completed":
            # 处理任务完成事件
            await self._handle_task_completed_event(event)
        elif event_type == "task_failed":
            # 处理任务失败事件
            await self._handle_task_failed_event(event)
        elif event_type in ["session_created", "session_paused", "session_resumed", "session_cancelled"]:
            # 记录会话状态变化
            logger.info(f"Session event: {event}")
        
        # 可以在这里添加更多事件处理逻辑，比如通知外部系统、记录日志等
    
    async def _handle_task_completed_event(self, event: Dict[str, Any]):
        """处理任务完成事件"""
        # 可以触发依赖任务的执行
        task_id = event.get("task_id")
        
        for session in self.active_sessions.values():
            for context in session.execution_contexts:
                if (context.status == ExecutionState.PENDING and 
                    task_id in context.dependencies):
                    # 重新检查依赖
                    if await self._check_dependencies(context):
                        await self.execution_queue.put(context)
    
    async def _handle_task_failed_event(self, event: Dict[str, Any]):
        """处理任务失败事件"""
        # 可以决定是否需要失败转移或重新规划
        logger.warning(f"Task failed: {event}")
    
    async def shutdown(self):
        """关闭编排器"""
        self._running = False
        
        # 取消所有活跃会话
        for session_id in list(self.active_sessions.keys()):
            await self.cancel_session(session_id)
        
        logger.info("Research orchestrator shutdown")