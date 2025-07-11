"""
智能体基类实现

结合 DeerFlow 的状态图架构和 Suna 的会话管理设计
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union, Callable
import asyncio
import logging
from datetime import datetime

from .state import AgentState, StateType, state_manager
from .tools import ToolInterface, ToolResult, tool_registry
from .exceptions import (
    AgentError, AgentConfigError, AgentPermissionError, 
    AgentInitializationError, AgentExecutionError
)
from ..config.agent_config import AgentConfig, AgentType, AgentCapability

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """智能体基类
    
    结合了两个项目的优秀设计：
    1. DeerFlow 的状态图管理
    2. Suna 的会话和工具管理
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_id = config.agent_id
        self.state: Optional[AgentState] = None
        
        # 工具和资源
        self.knowledge_bases: Dict[str, Any] = {}
        self.mcp_tools: Dict[str, Any] = {}
        self.loaded_tools: Dict[str, ToolInterface] = {}
        
        # 权限和安全
        self.permissions: List[str] = []
        self.user_permissions: Dict[str, List[str]] = {}
        
        # 执行控制
        self._running = False
        self._paused = False
        self._stop_requested = False
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._current_task: Optional[Dict[str, Any]] = None
        
        # 回调函数
        self._state_change_callbacks: List[Callable] = []
        self._task_completion_callbacks: List[Callable] = []
        
        logger.info(f"智能体 {self.agent_id} ({self.config.name}) 创建完成")
    
    async def initialize(self) -> bool:
        """初始化智能体"""
        try:
            # 创建状态
            self.state = await state_manager.create_state(self.agent_id)
            await state_manager.set_state_type(self.agent_id, StateType.INITIALIZING)
            
            # 验证权限
            await self._verify_permissions()
            
            # 加载知识库
            await self._load_knowledge_bases()
            
            # 加载MCP工具
            await self._load_mcp_tools()
            
            # 初始化LLM
            await self._initialize_llm()
            
            # 执行自定义初始化
            await self._custom_initialize()
            
            # 设置为就绪状态
            await state_manager.set_state_type(self.agent_id, StateType.READY)
            
            logger.info(f"智能体 {self.agent_id} 初始化完成")
            return True
            
        except Exception as e:
            error_msg = f"智能体 {self.agent_id} 初始化失败: {str(e)}"
            logger.error(error_msg)
            
            if self.state:
                self.state.set_error(error_msg)
                await state_manager.set_state_type(self.agent_id, StateType.ERROR)
            
            raise AgentInitializationError(error_msg)
    
    async def _verify_permissions(self):
        """验证权限"""
        try:
            from src.auth.services.permission_service import PermissionService
            
            permission_service = PermissionService()
            
            # 验证用户基础权限
            if not await permission_service.has_permission(
                self.config.user_id, "agent:create"
            ):
                raise AgentPermissionError("用户没有创建智能体的权限")
            
            # 验证能力所需权限
            for capability in self.config.capabilities:
                for required_permission in capability.required_permissions:
                    if not await permission_service.has_permission(
                        self.config.user_id, required_permission
                    ):
                        raise AgentPermissionError(
                            f"用户缺少权限: {required_permission}",
                            required_permission
                        )
            
            # 验证知识库权限
            for kb_id in self.config.selected_knowledge_bases:
                if not await permission_service.has_kb_permission(
                    self.config.user_id, kb_id, "read"
                ):
                    raise AgentPermissionError(f"用户没有访问知识库 {kb_id} 的权限")
            
            # 验证MCP工具权限
            for tool_name in self.config.selected_mcp_tools:
                if not await permission_service.has_tool_permission(
                    self.config.user_id, tool_name
                ):
                    raise AgentPermissionError(f"用户没有使用工具 {tool_name} 的权限")
            
            logger.info(f"智能体 {self.agent_id} 权限验证通过")
            
        except Exception as e:
            if isinstance(e, AgentPermissionError):
                raise
            raise AgentPermissionError(f"权限验证失败: {str(e)}")
    
    async def _load_knowledge_bases(self):
        """加载知识库"""
        try:
            from ..knowledge.kb_manager import KnowledgeBaseManager
            
            kb_manager = KnowledgeBaseManager()
            
            for kb_id in self.config.selected_knowledge_bases:
                kb = await kb_manager.load_knowledge_base(kb_id, self.config.user_id)
                if kb:
                    self.knowledge_bases[kb_id] = kb
                    
                    # 注册为工具
                    from .tools import KnowledgeBaseTool
                    kb_tool = KnowledgeBaseTool(f"kb_{kb_id}", kb_id, f"知识库: {kb.name}")
                    await tool_registry.register_tool(kb_tool)
                    self.loaded_tools[f"kb_{kb_id}"] = kb_tool
                    
                    if self.state:
                        self.state.loaded_knowledge_bases.append(kb_id)
                    
                    logger.info(f"知识库 {kb_id} 加载成功")
                else:
                    logger.warning(f"知识库 {kb_id} 加载失败")
            
        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            raise AgentInitializationError(f"知识库加载失败: {str(e)}")
    
    async def _load_mcp_tools(self):
        """加载MCP工具"""
        try:
            from src.mcp_integration.registry import MCPRegistry
            
            registry = MCPRegistry()
            
            for tool_name in self.config.selected_mcp_tools:
                tool = await registry.get_tool(tool_name)
                if tool:
                    self.mcp_tools[tool_name] = tool
                    
                    # 注册为工具
                    from .tools import MCPTool
                    mcp_tool = MCPTool(f"mcp_{tool_name}", tool_name, f"MCP工具: {tool_name}")
                    await tool_registry.register_tool(mcp_tool)
                    self.loaded_tools[f"mcp_{tool_name}"] = mcp_tool
                    
                    if self.state:
                        self.state.loaded_mcp_tools.append(tool_name)
                    
                    logger.info(f"MCP工具 {tool_name} 加载成功")
                else:
                    logger.warning(f"MCP工具 {tool_name} 加载失败")
                    
        except Exception as e:
            logger.error(f"加载MCP工具失败: {e}")
            raise AgentInitializationError(f"MCP工具加载失败: {str(e)}")
    
    async def _initialize_llm(self):
        """初始化LLM"""
        try:
            # TODO: 实现LLM初始化逻辑
            # 根据config.llm_config初始化对应的LLM客户端
            logger.info(f"LLM初始化完成: {self.config.llm_config.provider}")
            
        except Exception as e:
            logger.error(f"LLM初始化失败: {e}")
            raise AgentInitializationError(f"LLM初始化失败: {str(e)}")
    
    @abstractmethod
    async def _custom_initialize(self):
        """自定义初始化逻辑"""
        pass
    
    async def start(self):
        """启动智能体"""
        if self._running:
            logger.warning(f"智能体 {self.agent_id} 已在运行")
            return
        
        try:
            self._running = True
            self._stop_requested = False
            
            await state_manager.set_state_type(self.agent_id, StateType.EXECUTING)
            
            # 启动任务处理循环
            await self._task_processing_loop()
            
        except Exception as e:
            logger.error(f"智能体 {self.agent_id} 启动失败: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止智能体"""
        if not self._running:
            return
        
        logger.info(f"正在停止智能体 {self.agent_id}")
        
        self._stop_requested = True
        self._running = False
        
        # 等待当前任务完成
        if self._current_task:
            logger.info(f"等待当前任务完成: {self._current_task.get('task_id')}")
            # TODO: 实现任务中断逻辑
        
        await state_manager.set_state_type(self.agent_id, StateType.IDLE)
        logger.info(f"智能体 {self.agent_id} 已停止")
    
    async def pause(self):
        """暂停智能体"""
        if not self._running:
            return
        
        self._paused = True
        await state_manager.set_state_type(self.agent_id, StateType.PAUSED)
        logger.info(f"智能体 {self.agent_id} 已暂停")
    
    async def resume(self):
        """恢复智能体"""
        if not self._paused:
            return
        
        self._paused = False
        await state_manager.set_state_type(self.agent_id, StateType.EXECUTING)
        logger.info(f"智能体 {self.agent_id} 已恢复")
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        task_id = task.get("task_id", f"task_{datetime.now().timestamp()}")
        
        try:
            logger.info(f"智能体 {self.agent_id} 开始执行任务: {task_id}")
            
            # 设置当前任务
            self._current_task = task
            if self.state:
                self.state.current_task_id = task_id
                self.state.push_execution_stack(task_id)
            
            # 验证任务权限
            await self._verify_task_permissions(task)
            
            # 执行具体任务
            result = await self._execute_task_impl(task)
            
            # 记录结果
            if self.state:
                self.state.pop_execution_stack()
                self.state.set_variable(f"task_result_{task_id}", result)
            
            logger.info(f"智能体 {self.agent_id} 任务执行完成: {task_id}")
            
            # 触发完成回调
            await self._notify_task_completion(task_id, result)
            
            return result
            
        except Exception as e:
            error_msg = f"任务执行失败: {str(e)}"
            logger.error(f"智能体 {self.agent_id} 任务 {task_id} 失败: {error_msg}")
            
            if self.state:
                self.state.set_error(error_msg)
                self.state.pop_execution_stack()
            
            raise AgentExecutionError(error_msg, task_id)
        
        finally:
            self._current_task = None
            if self.state:
                self.state.current_task_id = None
    
    @abstractmethod
    async def _execute_task_impl(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务的具体实现"""
        pass
    
    async def _verify_task_permissions(self, task: Dict[str, Any]):
        """验证任务权限"""
        # 基础权限验证逻辑
        task_type = task.get("task_type")
        if task_type and not await self._has_task_permission(task_type):
            raise AgentPermissionError(f"没有执行任务类型 {task_type} 的权限")
    
    async def _has_task_permission(self, task_type: str) -> bool:
        """检查任务权限"""
        # TODO: 实现具体的任务权限检查逻辑
        return True
    
    async def _task_processing_loop(self):
        """任务处理循环"""
        while self._running and not self._stop_requested:
            try:
                if self._paused:
                    await asyncio.sleep(0.1)
                    continue
                
                # 等待任务
                try:
                    task = await asyncio.wait_for(
                        self._task_queue.get(), 
                        timeout=1.0
                    )
                    
                    # 执行任务
                    await self.execute_task(task)
                    
                except asyncio.TimeoutError:
                    # 超时正常，继续循环
                    continue
                    
            except Exception as e:
                logger.error(f"任务处理循环错误: {e}")
                await asyncio.sleep(1.0)  # 错误时短暂休眠
    
    async def submit_task(self, task: Dict[str, Any]):
        """提交任务"""
        await self._task_queue.put(task)
    
    async def query_knowledge(self, query: str, kb_ids: Optional[List[str]] = None) -> List[Dict]:
        """查询知识库"""
        results = []
        target_kbs = kb_ids or list(self.knowledge_bases.keys())
        
        for kb_id in target_kbs:
            if kb_id in self.knowledge_bases:
                kb = self.knowledge_bases[kb_id]
                try:
                    kb_results = await kb.query(query)
                    for result in kb_results:
                        result["source_kb"] = kb_id
                    results.extend(kb_results)
                except Exception as e:
                    logger.error(f"查询知识库 {kb_id} 失败: {e}")
        
        return results
    
    async def call_mcp_tool(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """调用MCP工具"""
        full_tool_name = f"mcp_{tool_name}"
        return await tool_registry.execute_tool(full_tool_name, args)
    
    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """调用工具（统一接口）"""
        return await tool_registry.execute_tool(tool_name, args)
    
    def add_state_change_callback(self, callback: Callable):
        """添加状态变更回调"""
        self._state_change_callbacks.append(callback)
    
    def add_task_completion_callback(self, callback: Callable):
        """添加任务完成回调"""
        self._task_completion_callbacks.append(callback)
    
    async def _notify_task_completion(self, task_id: str, result: Dict[str, Any]):
        """通知任务完成"""
        for callback in self._task_completion_callbacks:
            try:
                await callback(self.agent_id, task_id, result)
            except Exception as e:
                logger.error(f"任务完成回调错误: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """获取状态信息"""
        state = await state_manager.get_state(self.agent_id)
        
        return {
            "agent_id": self.agent_id,
            "name": self.config.name,
            "type": self.config.agent_type.value,
            "state": state.state_type.value if state else "unknown",
            "running": self._running,
            "paused": self._paused,
            "current_task": self._current_task.get("task_id") if self._current_task else None,
            "loaded_knowledge_bases": len(self.knowledge_bases),
            "loaded_mcp_tools": len(self.mcp_tools),
            "queue_size": self._task_queue.qsize(),
            "last_activity": state.last_activity_at.isoformat() if state else None
        }
    
    async def cleanup(self):
        """清理资源"""
        try:
            # 停止运行
            await self.stop()
            
            # 清理工具
            for tool_name in list(self.loaded_tools.keys()):
                await tool_registry.unregister_tool(tool_name)
            
            # 清理状态
            await state_manager.remove_state(self.agent_id)
            
            logger.info(f"智能体 {self.agent_id} 清理完成")
            
        except Exception as e:
            logger.error(f"智能体 {self.agent_id} 清理失败: {e}")
    
    def __str__(self):
        return f"Agent({self.agent_id}, {self.config.name}, {self.config.agent_type.value})"
    
    def __repr__(self):
        return self.__str__()