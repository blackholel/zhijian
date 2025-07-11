"""
协调器Agent实现
参考DeerFlow的协调器设计，负责任务分解和多Agent协作调度
"""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from enum import Enum

from ..base.agent import BaseAgent, AgentConfig, AgentCapability
from ..base.state import AgentState, TaskState, ResearchPhase
from ..knowledge.kb_manager import KnowledgeBaseManager
from ...mcp_integration.registry import MCPRegistry
from ...core.llm.llm_service import LLMService
from ...auth.services.permission_service import PermissionService

logger = logging.getLogger(__name__)


class CoordinationStrategy(Enum):
    """协调策略"""
    SEQUENTIAL = "sequential"      # 顺序执行
    PARALLEL = "parallel"         # 并行执行
    HYBRID = "hybrid"            # 混合策略
    ADAPTIVE = "adaptive"        # 自适应策略


class TaskPriority(Enum):
    """任务优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class CoordinatorAgent(BaseAgent):
    """协调器Agent
    
    职责：
    1. 研究任务分解
    2. Agent调度和协作
    3. 资源分配管理
    4. 执行状态监控
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.strategy = CoordinationStrategy.ADAPTIVE
        self.task_queue = asyncio.Queue()
        self.active_tasks: Dict[str, Dict] = {}
        self.completed_tasks: List[Dict] = []
        self.llm_service = LLMService()
        
    async def initialize(self):
        """初始化协调器"""
        await super().initialize()
        
        # 初始化协调策略
        self.strategy = CoordinationStrategy(
            self.config.agent_config.get("coordination_strategy", "adaptive")
        )
        
        logger.info(f"Coordinator initialized with strategy: {self.strategy.value}")
        
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行协调任务"""
        task_type = task.get("task_type")
        
        try:
            if task_type == "planning":
                return await self._execute_planning(task)
            elif task_type == "coordination":
                return await self._execute_coordination(task)
            elif task_type == "monitoring":
                return await self._execute_monitoring(task)
            elif task_type == "resource_allocation":
                return await self._execute_resource_allocation(task)
            else:
                raise ValueError(f"Unknown task type: {task_type}")
                
        except Exception as e:
            logger.error(f"Coordinator execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type
            }
    
    async def _execute_planning(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行研究规划"""
        topic = task.get("topic", "")
        objective = task.get("objective", "")
        available_kbs = task.get("available_knowledge_bases", [])
        available_tools = task.get("available_mcp_tools", [])
        
        # 构建规划提示
        planning_prompt = await self._build_planning_prompt(
            topic, objective, available_kbs, available_tools
        )
        
        # 调用LLM进行规划
        response = await self.llm_service.generate_response(
            prompt=planning_prompt,
            config=self.config.llm_config
        )
        
        # 解析规划结果
        plan_result = await self._parse_planning_result(response)
        
        # 验证规划合理性
        validated_plan = await self._validate_plan(plan_result)
        
        return {
            "success": True,
            "plan": validated_plan,
            "tasks": validated_plan.get("tasks", []),
            "required_agents": validated_plan.get("required_agents", []),
            "resource_allocation": validated_plan.get("resource_allocation", {}),
            "estimated_duration": validated_plan.get("estimated_duration", 0)
        }
    
    async def _execute_coordination(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行协调任务"""
        research_tasks = task.get("research_tasks", [])
        available_agents = task.get("available_agents", [])
        
        # 任务分配
        task_assignments = await self._assign_tasks(research_tasks, available_agents)
        
        # 执行协调
        coordination_result = await self._coordinate_execution(task_assignments)
        
        return {
            "success": True,
            "task_assignments": task_assignments,
            "coordination_result": coordination_result
        }
    
    async def _execute_monitoring(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行监控任务"""
        session_id = task.get("session_id", "")
        
        # 获取当前状态
        current_state = await self._get_execution_state(session_id)
        
        # 分析执行情况
        analysis = await self._analyze_execution_status(current_state)
        
        # 生成监控报告
        monitoring_report = await self._generate_monitoring_report(analysis)
        
        return {
            "success": True,
            "current_state": current_state,
            "analysis": analysis,
            "monitoring_report": monitoring_report
        }
    
    async def _execute_resource_allocation(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行资源分配"""
        research_tasks = task.get("research_tasks", [])
        available_resources = task.get("available_resources", {})
        
        # 资源需求分析
        resource_requirements = await self._analyze_resource_requirements(research_tasks)
        
        # 资源分配策略
        allocation_strategy = await self._determine_allocation_strategy(
            resource_requirements, available_resources
        )
        
        # 执行资源分配
        allocation_result = await self._allocate_resources(allocation_strategy)
        
        return {
            "success": True,
            "resource_requirements": resource_requirements,
            "allocation_strategy": allocation_strategy,
            "allocation_result": allocation_result
        }
    
    async def _build_planning_prompt(
        self, 
        topic: str, 
        objective: str, 
        available_kbs: List[str], 
        available_tools: List[str]
    ) -> str:
        """构建规划提示"""
        
        # 获取知识库信息
        kb_info = []
        for kb_id in available_kbs:
            kb_details = await self.knowledge_manager.get_knowledge_base_info(
                kb_id, self.config.user_id
            )
            if kb_details:
                kb_info.append(kb_details)
        
        # 获取工具信息
        tool_info = []
        for tool_name in available_tools:
            tool_details = await self.mcp_registry.get_tool_info(tool_name)
            if tool_details:
                tool_info.append(tool_details)
        
        prompt = f"""
作为研究协调器，请为以下研究任务制定详细的执行计划：

研究主题：{topic}
研究目标：{objective}

可用知识库：
{json.dumps(kb_info, ensure_ascii=False, indent=2)}

可用工具：
{json.dumps(tool_info, ensure_ascii=False, indent=2)}

请制定一个结构化的研究计划，包括：

1. 任务分解：将研究目标分解为具体的子任务
2. 任务优先级：确定任务的执行顺序和优先级
3. 资源分配：为每个任务分配合适的知识库和工具
4. 智能体分工：确定需要哪些类型的智能体参与
5. 时间估算：预估每个任务的执行时间
6. 依赖关系：识别任务之间的依赖关系

请以JSON格式返回计划，格式如下：
{{
    "plan_overview": "研究计划概述",
    "tasks": [
        {{
            "task_id": "任务ID",
            "title": "任务标题",
            "description": "任务描述",
            "agent_type": "负责的智能体类型",
            "priority": "优先级",
            "estimated_duration": "预估时间(分钟)",
            "required_knowledge_bases": ["所需知识库ID"],
            "required_tools": ["所需工具名称"],
            "dependencies": ["依赖的任务ID"],
            "success_criteria": "成功标准"
        }}
    ],
    "required_agents": ["需要的智能体类型"],
    "resource_allocation": {{
        "knowledge_bases": {{"知识库ID": "分配给的任务"}},
        "tools": {{"工具名称": "分配给的任务"}}
    }},
    "estimated_duration": "总预估时间",
    "risk_assessment": "风险评估"
}}
"""
        
        return prompt
    
    async def _parse_planning_result(self, response: str) -> Dict[str, Any]:
        """解析规划结果"""
        try:
            # 尝试解析JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_content = response[json_start:json_end].strip()
            else:
                json_content = response.strip()
            
            plan = json.loads(json_content)
            return plan
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse planning result: {e}")
            # 返回默认计划
            return {
                "plan_overview": "自动生成的基础研究计划",
                "tasks": [
                    {
                        "task_id": "default_research",
                        "title": "基础研究任务",
                        "description": "执行基础研究和信息收集",
                        "agent_type": "researcher",
                        "priority": "medium",
                        "estimated_duration": 30,
                        "required_knowledge_bases": self.config.selected_knowledge_bases,
                        "required_tools": self.config.selected_mcp_tools,
                        "dependencies": [],
                        "success_criteria": "收集相关信息并整理"
                    }
                ],
                "required_agents": ["researcher"],
                "resource_allocation": {},
                "estimated_duration": 30,
                "risk_assessment": "低风险"
            }
    
    async def _validate_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """验证规划合理性"""
        validated_plan = plan.copy()
        
        # 验证任务依赖关系
        tasks = validated_plan.get("tasks", [])
        task_ids = {task["task_id"] for task in tasks}
        
        for task in tasks:
            # 检查依赖任务是否存在
            dependencies = task.get("dependencies", [])
            valid_dependencies = [dep for dep in dependencies if dep in task_ids]
            task["dependencies"] = valid_dependencies
            
            # 验证智能体类型
            agent_type = task.get("agent_type", "researcher")
            if agent_type not in ["coordinator", "researcher", "analyzer", "reporter"]:
                task["agent_type"] = "researcher"
            
            # 验证优先级
            priority = task.get("priority", "medium")
            if priority not in ["low", "medium", "high", "urgent"]:
                task["priority"] = "medium"
            
            # 验证预估时间
            estimated_duration = task.get("estimated_duration", 30)
            if not isinstance(estimated_duration, (int, float)) or estimated_duration <= 0:
                task["estimated_duration"] = 30
        
        # 验证所需智能体
        required_agents = set(task["agent_type"] for task in tasks)
        validated_plan["required_agents"] = list(required_agents)
        
        return validated_plan
    
    async def _assign_tasks(
        self, 
        research_tasks: List[Dict], 
        available_agents: List[str]
    ) -> Dict[str, List[Dict]]:
        """分配任务给智能体"""
        task_assignments = {}
        
        for task in research_tasks:
            agent_type = task.get("agent_type", "researcher")
            
            if agent_type not in task_assignments:
                task_assignments[agent_type] = []
            
            task_assignments[agent_type].append(task)
        
        return task_assignments
    
    async def _coordinate_execution(self, task_assignments: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """协调执行"""
        coordination_result = {
            "strategy": self.strategy.value,
            "execution_plan": [],
            "resource_conflicts": [],
            "optimization_suggestions": []
        }
        
        if self.strategy == CoordinationStrategy.SEQUENTIAL:
            # 顺序执行策略
            execution_plan = self._create_sequential_plan(task_assignments)
        elif self.strategy == CoordinationStrategy.PARALLEL:
            # 并行执行策略
            execution_plan = self._create_parallel_plan(task_assignments)
        elif self.strategy == CoordinationStrategy.HYBRID:
            # 混合策略
            execution_plan = self._create_hybrid_plan(task_assignments)
        else:
            # 自适应策略
            execution_plan = await self._create_adaptive_plan(task_assignments)
        
        coordination_result["execution_plan"] = execution_plan
        
        return coordination_result
    
    def _create_sequential_plan(self, task_assignments: Dict[str, List[Dict]]) -> List[Dict]:
        """创建顺序执行计划"""
        execution_plan = []
        
        # 按优先级排序所有任务
        all_tasks = []
        for agent_type, tasks in task_assignments.items():
            for task in tasks:
                task["assigned_agent"] = agent_type
                all_tasks.append(task)
        
        # 排序：优先级高的先执行
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        all_tasks.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 2))
        
        for i, task in enumerate(all_tasks):
            execution_plan.append({
                "step": i + 1,
                "task_id": task["task_id"],
                "agent_type": task["assigned_agent"],
                "start_after": i * 5,  # 每个任务间隔5分钟
                "estimated_duration": task.get("estimated_duration", 30)
            })
        
        return execution_plan
    
    def _create_parallel_plan(self, task_assignments: Dict[str, List[Dict]]) -> List[Dict]:
        """创建并行执行计划"""
        execution_plan = []
        
        # 所有任务同时开始
        for agent_type, tasks in task_assignments.items():
            for task in tasks:
                execution_plan.append({
                    "step": 1,
                    "task_id": task["task_id"],
                    "agent_type": agent_type,
                    "start_after": 0,
                    "estimated_duration": task.get("estimated_duration", 30)
                })
        
        return execution_plan
    
    def _create_hybrid_plan(self, task_assignments: Dict[str, List[Dict]]) -> List[Dict]:
        """创建混合执行计划"""
        execution_plan = []
        
        # 高优先级任务并行执行，低优先级任务顺序执行
        high_priority_tasks = []
        low_priority_tasks = []
        
        for agent_type, tasks in task_assignments.items():
            for task in tasks:
                task["assigned_agent"] = agent_type
                if task.get("priority") in ["urgent", "high"]:
                    high_priority_tasks.append(task)
                else:
                    low_priority_tasks.append(task)
        
        # 高优先级任务并行开始
        for task in high_priority_tasks:
            execution_plan.append({
                "step": 1,
                "task_id": task["task_id"],
                "agent_type": task["assigned_agent"],
                "start_after": 0,
                "estimated_duration": task.get("estimated_duration", 30)
            })
        
        # 低优先级任务顺序执行
        for i, task in enumerate(low_priority_tasks):
            execution_plan.append({
                "step": i + 2,
                "task_id": task["task_id"],
                "agent_type": task["assigned_agent"],
                "start_after": max([t.get("estimated_duration", 30) for t in high_priority_tasks], default=0) + i * 5,
                "estimated_duration": task.get("estimated_duration", 30)
            })
        
        return execution_plan
    
    async def _create_adaptive_plan(self, task_assignments: Dict[str, List[Dict]]) -> List[Dict]:
        """创建自适应执行计划"""
        # 分析任务依赖和资源需求
        task_analysis = await self._analyze_task_dependencies(task_assignments)
        
        # 根据分析结果选择最佳策略
        if task_analysis["has_complex_dependencies"]:
            return self._create_sequential_plan(task_assignments)
        elif task_analysis["resource_conflicts"]:
            return self._create_hybrid_plan(task_assignments)
        else:
            return self._create_parallel_plan(task_assignments)
    
    async def _analyze_task_dependencies(self, task_assignments: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """分析任务依赖关系"""
        analysis = {
            "has_complex_dependencies": False,
            "resource_conflicts": [],
            "parallelizable_tasks": [],
            "sequential_tasks": []
        }
        
        all_tasks = []
        for agent_type, tasks in task_assignments.items():
            for task in tasks:
                task["assigned_agent"] = agent_type
                all_tasks.append(task)
        
        # 检查依赖关系
        for task in all_tasks:
            dependencies = task.get("dependencies", [])
            if len(dependencies) > 1:
                analysis["has_complex_dependencies"] = True
            
            if dependencies:
                analysis["sequential_tasks"].append(task["task_id"])
            else:
                analysis["parallelizable_tasks"].append(task["task_id"])
        
        # 检查资源冲突
        resource_usage = {}
        for task in all_tasks:
            for kb in task.get("required_knowledge_bases", []):
                if kb not in resource_usage:
                    resource_usage[kb] = []
                resource_usage[kb].append(task["task_id"])
        
        for resource, tasks in resource_usage.items():
            if len(tasks) > 1:
                analysis["resource_conflicts"].append({
                    "resource": resource,
                    "conflicting_tasks": tasks
                })
        
        return analysis
    
    async def _get_execution_state(self, session_id: str) -> Dict[str, Any]:
        """获取执行状态"""
        # 这里应该从数据库或状态管理器获取实际状态
        # 目前返回模拟状态
        return {
            "session_id": session_id,
            "total_tasks": len(self.active_tasks) + len(self.completed_tasks),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": 0,
            "current_phase": "research",
            "progress": len(self.completed_tasks) / max(len(self.active_tasks) + len(self.completed_tasks), 1)
        }
    
    async def _analyze_execution_status(self, current_state: Dict[str, Any]) -> Dict[str, Any]:
        """分析执行状态"""
        analysis = {
            "overall_health": "healthy",
            "performance_metrics": {
                "completion_rate": current_state.get("progress", 0),
                "active_task_count": current_state.get("active_tasks", 0),
                "failed_task_count": current_state.get("failed_tasks", 0)
            },
            "bottlenecks": [],
            "recommendations": []
        }
        
        # 分析性能指标
        completion_rate = analysis["performance_metrics"]["completion_rate"]
        if completion_rate < 0.3:
            analysis["overall_health"] = "concerning"
            analysis["recommendations"].append("考虑增加资源或调整任务优先级")
        elif completion_rate < 0.7:
            analysis["overall_health"] = "moderate"
        
        # 检查瓶颈
        if current_state.get("failed_tasks", 0) > 0:
            analysis["bottlenecks"].append("存在失败任务")
            analysis["recommendations"].append("检查失败任务的原因并重新执行")
        
        return analysis
    
    async def _generate_monitoring_report(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成监控报告"""
        report = {
            "report_time": datetime.now().isoformat(),
            "overall_status": analysis["overall_health"],
            "key_metrics": analysis["performance_metrics"],
            "issues_identified": analysis["bottlenecks"],
            "recommendations": analysis["recommendations"],
            "next_check_time": (datetime.now().timestamp() + 300) * 1000  # 5分钟后
        }
        
        return report
    
    async def _analyze_resource_requirements(self, research_tasks: List[Dict]) -> Dict[str, Any]:
        """分析资源需求"""
        requirements = {
            "knowledge_bases": {},
            "mcp_tools": {},
            "compute_resources": {},
            "storage_requirements": {}
        }
        
        for task in research_tasks:
            # 知识库需求
            for kb in task.get("required_knowledge_bases", []):
                if kb not in requirements["knowledge_bases"]:
                    requirements["knowledge_bases"][kb] = []
                requirements["knowledge_bases"][kb].append(task["task_id"])
            
            # MCP工具需求
            for tool in task.get("required_tools", []):
                if tool not in requirements["mcp_tools"]:
                    requirements["mcp_tools"][tool] = []
                requirements["mcp_tools"][tool].append(task["task_id"])
            
            # 计算资源需求
            duration = task.get("estimated_duration", 30)
            priority = task.get("priority", "medium")
            
            compute_weight = {"low": 1, "medium": 2, "high": 3, "urgent": 4}
            requirements["compute_resources"][task["task_id"]] = {
                "weight": compute_weight.get(priority, 2),
                "duration": duration
            }
        
        return requirements
    
    async def _determine_allocation_strategy(
        self, 
        resource_requirements: Dict[str, Any], 
        available_resources: Dict[str, Any]
    ) -> Dict[str, Any]:
        """确定分配策略"""
        strategy = {
            "allocation_method": "balanced",
            "priority_handling": "weighted",
            "conflict_resolution": "time_sharing",
            "optimization_target": "throughput"
        }
        
        # 分析资源充足性
        kb_conflicts = []
        for kb, tasks in resource_requirements.get("knowledge_bases", {}).items():
            if len(tasks) > 1:
                kb_conflicts.append({"resource": kb, "tasks": tasks})
        
        tool_conflicts = []
        for tool, tasks in resource_requirements.get("mcp_tools", {}).items():
            if len(tasks) > 1:
                tool_conflicts.append({"resource": tool, "tasks": tasks})
        
        if kb_conflicts or tool_conflicts:
            strategy["allocation_method"] = "sequential"
            strategy["conflict_resolution"] = "priority_based"
        
        strategy["conflicts"] = {
            "knowledge_base_conflicts": kb_conflicts,
            "tool_conflicts": tool_conflicts
        }
        
        return strategy
    
    async def _allocate_resources(self, allocation_strategy: Dict[str, Any]) -> Dict[str, Any]:
        """执行资源分配"""
        allocation_result = {
            "success": True,
            "allocations": {},
            "conflicts_resolved": [],
            "pending_allocations": []
        }
        
        # 根据策略分配资源
        method = allocation_strategy.get("allocation_method", "balanced")
        
        if method == "balanced":
            # 平衡分配
            allocation_result["allocations"] = await self._balanced_allocation(allocation_strategy)
        elif method == "sequential":
            # 顺序分配
            allocation_result["allocations"] = await self._sequential_allocation(allocation_strategy)
        else:
            # 默认分配
            allocation_result["allocations"] = await self._default_allocation(allocation_strategy)
        
        return allocation_result
    
    async def _balanced_allocation(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """平衡分配"""
        return {
            "method": "balanced",
            "resource_distribution": "even",
            "load_balancing": "enabled"
        }
    
    async def _sequential_allocation(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """顺序分配"""
        return {
            "method": "sequential",
            "execution_order": "priority_based",
            "resource_sharing": "time_sliced"
        }
    
    async def _default_allocation(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """默认分配"""
        return {
            "method": "default",
            "allocation_strategy": "first_come_first_serve"
        }