"""
事件管理和流式响应系统
支持实时事件推送和流式数据传输
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator, Callable
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
from collections import defaultdict
import uuid

from src.utils.logging_config import logger


class EventType(str, Enum):
    """事件类型"""
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERROR = "agent_error"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_ERROR = "task_error"
    PROGRESS_UPDATE = "progress_update"
    RESEARCH_PHASE_CHANGED = "research_phase_changed"
    KNOWLEDGE_QUERY = "knowledge_query"
    MCP_TOOL_CALL = "mcp_tool_call"
    STREAM_DATA = "stream_data"
    SYSTEM_MESSAGE = "system_message"


@dataclass
class StreamEvent:
    """流式事件"""
    event_id: str
    event_type: EventType
    timestamp: str
    session_id: str
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_sse_format(self) -> str:
        """转换为SSE格式"""
        return f"data: {json.dumps(self.to_dict())}\n\n"


class EventManager:
    """事件管理器"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._session_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_history: Dict[str, List[StreamEvent]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._max_history_size = 1000
    
    async def subscribe(self, event_type: EventType, callback: Callable):
        """订阅事件类型"""
        async with self._lock:
            self._subscribers[event_type.value].append(callback)
    
    async def subscribe_session(self, session_id: str, callback: Callable):
        """订阅会话事件"""
        async with self._lock:
            self._session_subscribers[session_id].append(callback)
    
    async def unsubscribe(self, event_type: EventType, callback: Callable):
        """取消订阅事件类型"""
        async with self._lock:
            if callback in self._subscribers[event_type.value]:
                self._subscribers[event_type.value].remove(callback)
    
    async def unsubscribe_session(self, session_id: str, callback: Callable):
        """取消订阅会话事件"""
        async with self._lock:
            if callback in self._session_subscribers[session_id]:
                self._session_subscribers[session_id].remove(callback)
    
    async def publish(self, event: StreamEvent):
        """发布事件"""
        async with self._lock:
            # 记录事件历史
            self._event_history[event.session_id].append(event)
            
            # 限制历史记录大小
            if len(self._event_history[event.session_id]) > self._max_history_size:
                self._event_history[event.session_id] = self._event_history[event.session_id][-self._max_history_size:]
            
            # 通知事件类型订阅者
            for callback in self._subscribers[event.event_type.value]:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(f"事件回调执行失败: {e}")
            
            # 通知会话订阅者
            for callback in self._session_subscribers[event.session_id]:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(f"会话事件回调执行失败: {e}")
    
    async def create_event(
        self,
        event_type: EventType,
        session_id: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> StreamEvent:
        """创建事件"""
        event = StreamEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            data=data,
            metadata=metadata or {}
        )
        
        await self.publish(event)
        return event
    
    async def get_session_events(self, session_id: str) -> List[StreamEvent]:
        """获取会话事件历史"""
        return self._event_history.get(session_id, [])
    
    async def clear_session_events(self, session_id: str):
        """清除会话事件历史"""
        async with self._lock:
            if session_id in self._event_history:
                del self._event_history[session_id]
            
            if session_id in self._session_subscribers:
                del self._session_subscribers[session_id]


class StreamingManager:
    """流式管理器"""
    
    def __init__(self, event_manager: EventManager):
        self.event_manager = event_manager
        self._active_streams: Dict[str, asyncio.Queue] = {}
        self._stream_locks: Dict[str, asyncio.Lock] = {}
    
    async def create_stream(self, session_id: str) -> AsyncGenerator[str, None]:
        """创建流式连接"""
        stream_queue = asyncio.Queue()
        stream_lock = asyncio.Lock()
        
        self._active_streams[session_id] = stream_queue
        self._stream_locks[session_id] = stream_lock
        
        # 订阅会话事件
        async def stream_callback(event: StreamEvent):
            await stream_queue.put(event.to_sse_format())
        
        await self.event_manager.subscribe_session(session_id, stream_callback)
        
        try:
            # 发送连接建立事件
            await self.event_manager.create_event(
                EventType.SYSTEM_MESSAGE,
                session_id,
                {"message": "Stream connection established"}
            )
            
            # 持续发送事件
            while True:
                try:
                    # 等待事件数据
                    event_data = await asyncio.wait_for(stream_queue.get(), timeout=30.0)
                    yield event_data
                    
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield "data: {\"type\": \"heartbeat\", \"timestamp\": \"" + datetime.now().isoformat() + "\"}\n\n"
                    
                except Exception as e:
                    logger.error(f"流式传输错误: {e}")
                    break
                    
        finally:
            # 清理资源
            await self._cleanup_stream(session_id)
    
    async def send_to_stream(self, session_id: str, data: Dict[str, Any]):
        """发送数据到流"""
        if session_id in self._active_streams:
            event = StreamEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.STREAM_DATA,
                timestamp=datetime.now().isoformat(),
                session_id=session_id,
                data=data
            )
            
            await self._active_streams[session_id].put(event.to_sse_format())
    
    async def _cleanup_stream(self, session_id: str):
        """清理流资源"""
        if session_id in self._active_streams:
            del self._active_streams[session_id]
        
        if session_id in self._stream_locks:
            del self._stream_locks[session_id]
    
    async def close_stream(self, session_id: str):
        """关闭流连接"""
        await self._cleanup_stream(session_id)
        
        # 发送关闭事件
        await self.event_manager.create_event(
            EventType.SYSTEM_MESSAGE,
            session_id,
            {"message": "Stream connection closed"}
        )


class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, event_manager: EventManager):
        self.event_manager = event_manager
        self._progress_data: Dict[str, Dict[str, Any]] = {}
    
    async def init_progress(self, session_id: str, total_steps: int, description: str = ""):
        """初始化进度"""
        self._progress_data[session_id] = {
            "total_steps": total_steps,
            "current_step": 0,
            "description": description,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "percentage": 0.0
        }
        
        await self.event_manager.create_event(
            EventType.PROGRESS_UPDATE,
            session_id,
            self._progress_data[session_id]
        )
    
    async def update_progress(self, session_id: str, step: int, description: str = ""):
        """更新进度"""
        if session_id not in self._progress_data:
            return
        
        progress = self._progress_data[session_id]
        progress["current_step"] = step
        progress["description"] = description
        progress["percentage"] = (step / progress["total_steps"]) * 100
        
        if step >= progress["total_steps"]:
            progress["completed_at"] = datetime.now().isoformat()
        
        await self.event_manager.create_event(
            EventType.PROGRESS_UPDATE,
            session_id,
            progress
        )
    
    async def get_progress(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取进度"""
        return self._progress_data.get(session_id)


# 全局实例
event_manager = EventManager()
streaming_manager = StreamingManager(event_manager)
progress_tracker = ProgressTracker(event_manager)


async def get_event_manager() -> EventManager:
    """获取事件管理器"""
    return event_manager


async def get_streaming_manager() -> StreamingManager:
    """获取流式管理器"""
    return streaming_manager


async def get_progress_tracker() -> ProgressTracker:
    """获取进度跟踪器"""
    return progress_tracker