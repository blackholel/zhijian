"""
智能体状态管理

结合 DeerFlow 的状态图架构和 Suna 的会话管理
"""

from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import asyncio
import json
from contextlib import asynccontextmanager


class StateType(str, Enum):
    """状态类型"""
    IDLE = "idle"                    # 空闲
    INITIALIZING = "initializing"    # 初始化中
    READY = "ready"                  # 就绪
    EXECUTING = "executing"          # 执行中
    WAITING = "waiting"              # 等待中
    PAUSED = "paused"               # 暂停
    ERROR = "error"                 # 错误
    COMPLETED = "completed"         # 完成
    TERMINATED = "terminated"       # 终止


class TaskState(str, Enum):
    """任务状态"""
    PENDING = "pending"             # 待处理
    ASSIGNED = "assigned"           # 已分配
    RUNNING = "running"             # 运行中
    PAUSED = "paused"              # 已暂停
    COMPLETED = "completed"        # 已完成
    FAILED = "failed"              # 失败
    CANCELLED = "cancelled"        # 已取消


class ResearchPhase(str, Enum):
    """研究阶段"""
    PLANNING = "planning"           # 规划阶段
    RESEARCH = "research"           # 研究阶段
    ANALYSIS = "analysis"           # 分析阶段
    REPORTING = "reporting"         # 报告阶段
    REVIEW = "review"              # 审查阶段
    COMPLETED = "completed"        # 完成


class AgentState(BaseModel):
    """智能体状态"""
    
    # 基础状态
    agent_id: str = Field(..., description="智能体ID")
    state_type: StateType = Field(default=StateType.IDLE, description="状态类型")
    
    # 执行状态
    current_task_id: Optional[str] = Field(default=None, description="当前任务ID")
    execution_stack: List[str] = Field(default_factory=list, description="执行栈")
    
    # 数据状态
    context: Dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    variables: Dict[str, Any] = Field(default_factory=dict, description="变量")
    memory: Dict[str, Any] = Field(default_factory=dict, description="记忆存储")
    
    # 消息状态 (参考 Suna 的消息管理)
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="消息历史")
    
    # 工具和资源状态
    loaded_knowledge_bases: List[str] = Field(default_factory=list, description="已加载的知识库")
    loaded_mcp_tools: List[str] = Field(default_factory=list, description="已加载的MCP工具")
    active_tools: Dict[str, Any] = Field(default_factory=dict, description="活跃工具")
    
    # 错误状态
    last_error: Optional[str] = Field(default=None, description="最后错误")
    error_count: int = Field(default=0, description="错误计数")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    last_activity_at: datetime = Field(default_factory=datetime.now, description="最后活跃时间")
    
    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now()
        self.last_activity_at = datetime.now()
    
    def set_state(self, state_type: StateType, context: Optional[Dict[str, Any]] = None):
        """设置状态"""
        self.state_type = state_type
        if context:
            self.context.update(context)
        self.update_timestamp()
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """添加消息"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(message)
        self.update_timestamp()
    
    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的消息"""
        return self.messages[-limit:] if limit > 0 else self.messages
    
    def clear_messages(self):
        """清除消息"""
        self.messages.clear()
        self.update_timestamp()
    
    def set_variable(self, key: str, value: Any):
        """设置变量"""
        self.variables[key] = value
        self.update_timestamp()
    
    def get_variable(self, key: str, default: Any = None) -> Any:
        """获取变量"""
        return self.variables.get(key, default)
    
    def remove_variable(self, key: str):
        """移除变量"""
        self.variables.pop(key, None)
        self.update_timestamp()
    
    def set_memory(self, key: str, value: Any):
        """设置记忆"""
        self.memory[key] = value
        self.update_timestamp()
    
    def get_memory(self, key: str, default: Any = None) -> Any:
        """获取记忆"""
        return self.memory.get(key, default)
    
    def clear_memory(self):
        """清除记忆"""
        self.memory.clear()
        self.update_timestamp()
    
    def push_execution_stack(self, task_id: str):
        """推入执行栈"""
        self.execution_stack.append(task_id)
        self.update_timestamp()
    
    def pop_execution_stack(self) -> Optional[str]:
        """弹出执行栈"""
        if self.execution_stack:
            task_id = self.execution_stack.pop()
            self.update_timestamp()
            return task_id
        return None
    
    def set_error(self, error_message: str):
        """设置错误"""
        self.last_error = error_message
        self.error_count += 1
        self.state_type = StateType.ERROR
        self.update_timestamp()
    
    def clear_error(self):
        """清除错误"""
        self.last_error = None
        self.update_timestamp()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.dict()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        """从字典创建"""
        return cls(**data)
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentStateManager:
    """智能体状态管理器"""
    
    def __init__(self):
        self._states: Dict[str, AgentState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._state_change_callbacks: List[callable] = []
    
    async def get_state(self, agent_id: str) -> Optional[AgentState]:
        """获取状态"""
        return self._states.get(agent_id)
    
    async def create_state(self, agent_id: str) -> AgentState:
        """创建状态"""
        if agent_id in self._states:
            raise ValueError(f"状态已存在: {agent_id}")
        
        state = AgentState(agent_id=agent_id)
        self._states[agent_id] = state
        self._locks[agent_id] = asyncio.Lock()
        
        await self._notify_state_change(agent_id, state.state_type, None)
        return state
    
    async def update_state(self, agent_id: str, **updates) -> AgentState:
        """更新状态"""
        async with self._get_lock(agent_id):
            state = self._states.get(agent_id)
            if not state:
                raise ValueError(f"状态不存在: {agent_id}")
            
            old_state_type = state.state_type
            
            for key, value in updates.items():
                if hasattr(state, key):
                    setattr(state, key, value)
            
            state.update_timestamp()
            
            if state.state_type != old_state_type:
                await self._notify_state_change(agent_id, state.state_type, old_state_type)
            
            return state
    
    async def set_state_type(self, agent_id: str, state_type: StateType, context: Optional[Dict[str, Any]] = None):
        """设置状态类型"""
        async with self._get_lock(agent_id):
            state = self._states.get(agent_id)
            if not state:
                raise ValueError(f"状态不存在: {agent_id}")
            
            old_state_type = state.state_type
            state.set_state(state_type, context)
            
            await self._notify_state_change(agent_id, state_type, old_state_type)
    
    async def remove_state(self, agent_id: str):
        """移除状态"""
        if agent_id in self._states:
            del self._states[agent_id]
        if agent_id in self._locks:
            del self._locks[agent_id]
    
    def _get_lock(self, agent_id: str) -> asyncio.Lock:
        """获取锁"""
        if agent_id not in self._locks:
            self._locks[agent_id] = asyncio.Lock()
        return self._locks[agent_id]
    
    @asynccontextmanager
    async def state_context(self, agent_id: str):
        """状态上下文管理器"""
        async with self._get_lock(agent_id):
            state = self._states.get(agent_id)
            if not state:
                raise ValueError(f"状态不存在: {agent_id}")
            yield state
            state.update_timestamp()
    
    def add_state_change_callback(self, callback: callable):
        """添加状态变更回调"""
        self._state_change_callbacks.append(callback)
    
    def remove_state_change_callback(self, callback: callable):
        """移除状态变更回调"""
        if callback in self._state_change_callbacks:
            self._state_change_callbacks.remove(callback)
    
    async def _notify_state_change(self, agent_id: str, new_state: StateType, old_state: Optional[StateType]):
        """通知状态变更"""
        for callback in self._state_change_callbacks:
            try:
                await callback(agent_id, new_state, old_state)
            except Exception as e:
                # 记录错误但不中断
                print(f"状态变更回调错误: {e}")
    
    async def get_all_states(self) -> Dict[str, AgentState]:
        """获取所有状态"""
        return self._states.copy()
    
    async def get_states_by_type(self, state_type: StateType) -> Dict[str, AgentState]:
        """根据状态类型获取状态"""
        return {
            agent_id: state 
            for agent_id, state in self._states.items() 
            if state.state_type == state_type
        }
    
    async def export_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """导出状态"""
        state = self._states.get(agent_id)
        return state.to_dict() if state else None
    
    async def import_state(self, agent_id: str, state_data: Dict[str, Any]) -> AgentState:
        """导入状态"""
        state = AgentState.from_dict(state_data)
        state.agent_id = agent_id  # 确保ID正确
        self._states[agent_id] = state
        self._locks[agent_id] = asyncio.Lock()
        return state


# 全局状态管理器实例
state_manager = AgentStateManager()