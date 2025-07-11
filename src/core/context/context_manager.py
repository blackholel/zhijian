"""
上下文管理和压缩系统
参考Suna的上下文管理设计，支持智能压缩和token管理
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

from src.utils.logging_config import logger


class CompressionStrategy(str, Enum):
    """压缩策略"""
    NONE = "none"
    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"
    MIDDLE_OUT = "middle_out"
    IMPORTANCE_BASED = "importance_based"


@dataclass
class ContextConfig:
    """上下文配置"""
    max_tokens: int = 4000
    compression_threshold: float = 0.8  # 达到80%时开始压缩
    compression_strategy: CompressionStrategy = CompressionStrategy.MIDDLE_OUT
    preserve_system_messages: bool = True
    preserve_recent_messages: int = 5
    max_history_size: int = 1000


class MessageType(str, Enum):
    """消息类型"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


@dataclass
class ContextMessage:
    """上下文消息"""
    role: str
    content: Union[str, Dict[str, Any]]
    timestamp: str
    message_id: str
    token_count: int = 0
    importance_score: float = 0.5
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "token_count": self.token_count,
            "importance_score": self.importance_score,
            "metadata": self.metadata or {}
        }


class TokenCounter:
    """Token计数器"""
    
    def __init__(self):
        self._cache: Dict[str, int] = {}
    
    def count_tokens(self, text: str, model: str = "gpt-3.5-turbo") -> int:
        """计算token数量"""
        cache_key = f"{model}:{hash(text)}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 简化的token计算，实际应该使用tiktoken
        # 这里使用简单的字符数估算
        estimated_tokens = len(text) // 4  # 大约4个字符=1个token
        
        self._cache[cache_key] = estimated_tokens
        return estimated_tokens
    
    def count_messages_tokens(self, messages: List[ContextMessage], model: str = "gpt-3.5-turbo") -> int:
        """计算消息列表的总token数"""
        total_tokens = 0
        
        for message in messages:
            if isinstance(message.content, str):
                total_tokens += self.count_tokens(message.content, model)
            else:
                total_tokens += self.count_tokens(json.dumps(message.content), model)
        
        return total_tokens


class ContextCompressor:
    """上下文压缩器"""
    
    def __init__(self, token_counter: TokenCounter):
        self.token_counter = token_counter
    
    async def compress_messages(
        self,
        messages: List[ContextMessage],
        max_tokens: int,
        strategy: CompressionStrategy = CompressionStrategy.MIDDLE_OUT,
        preserve_recent: int = 5
    ) -> List[ContextMessage]:
        """压缩消息列表"""
        if strategy == CompressionStrategy.NONE:
            return messages
        
        current_tokens = self.token_counter.count_messages_tokens(messages)
        
        if current_tokens <= max_tokens:
            return messages
        
        if strategy == CompressionStrategy.TRUNCATE:
            return await self._truncate_messages(messages, max_tokens)
        elif strategy == CompressionStrategy.MIDDLE_OUT:
            return await self._middle_out_compression(messages, max_tokens, preserve_recent)
        elif strategy == CompressionStrategy.IMPORTANCE_BASED:
            return await self._importance_based_compression(messages, max_tokens, preserve_recent)
        elif strategy == CompressionStrategy.SUMMARIZE:
            return await self._summarize_messages(messages, max_tokens, preserve_recent)
        
        return messages
    
    async def _truncate_messages(self, messages: List[ContextMessage], max_tokens: int) -> List[ContextMessage]:
        """截断压缩"""
        result = []
        total_tokens = 0
        
        # 从最新的消息开始保留
        for message in reversed(messages):
            message_tokens = self.token_counter.count_tokens(
                message.content if isinstance(message.content, str) else json.dumps(message.content)
            )
            
            if total_tokens + message_tokens <= max_tokens:
                result.insert(0, message)
                total_tokens += message_tokens
            else:
                break
        
        return result
    
    async def _middle_out_compression(
        self,
        messages: List[ContextMessage],
        max_tokens: int,
        preserve_recent: int
    ) -> List[ContextMessage]:
        """中间删除压缩"""
        if len(messages) <= preserve_recent * 2:
            return messages
        
        # 保留系统消息
        system_messages = [msg for msg in messages if msg.role == MessageType.SYSTEM.value]
        conversation_messages = [msg for msg in messages if msg.role != MessageType.SYSTEM.value]
        
        # 保留最近的消息
        recent_messages = conversation_messages[-preserve_recent:]
        early_messages = conversation_messages[:preserve_recent]
        
        # 计算保留消息的token数
        preserved_tokens = (
            self.token_counter.count_messages_tokens(system_messages) +
            self.token_counter.count_messages_tokens(recent_messages) +
            self.token_counter.count_messages_tokens(early_messages)
        )
        
        if preserved_tokens <= max_tokens:
            return system_messages + early_messages + recent_messages
        
        # 如果还是太多，进一步压缩
        available_tokens = max_tokens - self.token_counter.count_messages_tokens(system_messages + recent_messages)
        
        compressed_early = await self._truncate_messages(early_messages, available_tokens)
        
        return system_messages + compressed_early + recent_messages
    
    async def _importance_based_compression(
        self,
        messages: List[ContextMessage],
        max_tokens: int,
        preserve_recent: int
    ) -> List[ContextMessage]:
        """基于重要性的压缩"""
        # 保留系统消息和最近的消息
        system_messages = [msg for msg in messages if msg.role == MessageType.SYSTEM.value]
        recent_messages = messages[-preserve_recent:]
        other_messages = messages[:-preserve_recent]
        
        # 按重要性排序
        other_messages.sort(key=lambda x: x.importance_score, reverse=True)
        
        # 计算基础token数
        base_tokens = (
            self.token_counter.count_messages_tokens(system_messages) +
            self.token_counter.count_messages_tokens(recent_messages)
        )
        
        # 添加重要的消息
        selected_messages = []
        current_tokens = base_tokens
        
        for message in other_messages:
            message_tokens = self.token_counter.count_tokens(
                message.content if isinstance(message.content, str) else json.dumps(message.content)
            )
            
            if current_tokens + message_tokens <= max_tokens:
                selected_messages.append(message)
                current_tokens += message_tokens
            else:
                break
        
        # 按时间戳排序
        selected_messages.sort(key=lambda x: x.timestamp)
        
        return system_messages + selected_messages + recent_messages
    
    async def _summarize_messages(
        self,
        messages: List[ContextMessage],
        max_tokens: int,
        preserve_recent: int
    ) -> List[ContextMessage]:
        """总结压缩"""
        # 这里应该调用LLM来总结消息
        # 暂时使用简单的截断
        return await self._middle_out_compression(messages, max_tokens, preserve_recent)


class ContextManager:
    """上下文管理器"""
    
    def __init__(self, config: ContextConfig):
        self.config = config
        self.token_counter = TokenCounter()
        self.compressor = ContextCompressor(self.token_counter)
        self._contexts: Dict[str, List[ContextMessage]] = {}
        self._lock = asyncio.Lock()
    
    async def create_context(self, session_id: str, system_message: Optional[str] = None) -> str:
        """创建上下文"""
        async with self._lock:
            self._contexts[session_id] = []
            
            if system_message:
                await self.add_message(
                    session_id,
                    MessageType.SYSTEM.value,
                    system_message,
                    importance_score=1.0
                )
            
            return session_id
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: Union[str, Dict[str, Any]],
        importance_score: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """添加消息"""
        async with self._lock:
            if session_id not in self._contexts:
                self._contexts[session_id] = []
            
            message_id = f"{session_id}_{len(self._contexts[session_id])}"
            
            # 计算token数
            content_str = content if isinstance(content, str) else json.dumps(content)
            token_count = self.token_counter.count_tokens(content_str)
            
            message = ContextMessage(
                role=role,
                content=content,
                timestamp=datetime.now().isoformat(),
                message_id=message_id,
                token_count=token_count,
                importance_score=importance_score,
                metadata=metadata
            )
            
            self._contexts[session_id].append(message)
            
            # 检查是否需要压缩
            await self._check_and_compress(session_id)
            
            return message_id
    
    async def get_messages(self, session_id: str) -> List[ContextMessage]:
        """获取消息"""
        return self._contexts.get(session_id, [])
    
    async def get_messages_for_llm(self, session_id: str) -> List[Dict[str, Any]]:
        """获取用于LLM的消息格式"""
        messages = await self.get_messages(session_id)
        return [
            {
                "role": msg.role,
                "content": msg.content
            }
            for msg in messages
        ]
    
    async def clear_context(self, session_id: str):
        """清除上下文"""
        async with self._lock:
            if session_id in self._contexts:
                del self._contexts[session_id]
    
    async def _check_and_compress(self, session_id: str):
        """检查并压缩上下文"""
        messages = self._contexts[session_id]
        current_tokens = self.token_counter.count_messages_tokens(messages)
        
        # 检查是否达到压缩阈值
        if current_tokens >= self.config.max_tokens * self.config.compression_threshold:
            logger.info(f"会话 {session_id} 达到压缩阈值，开始压缩")
            
            compressed_messages = await self.compressor.compress_messages(
                messages,
                self.config.max_tokens,
                self.config.compression_strategy,
                self.config.preserve_recent_messages
            )
            
            self._contexts[session_id] = compressed_messages
            
            new_tokens = self.token_counter.count_messages_tokens(compressed_messages)
            logger.info(f"上下文压缩完成: {current_tokens} -> {new_tokens} tokens")
    
    async def get_context_stats(self, session_id: str) -> Dict[str, Any]:
        """获取上下文统计"""
        messages = self._contexts.get(session_id, [])
        
        if not messages:
            return {"message_count": 0, "token_count": 0}
        
        total_tokens = self.token_counter.count_messages_tokens(messages)
        
        role_counts = {}
        for message in messages:
            role_counts[message.role] = role_counts.get(message.role, 0) + 1
        
        return {
            "message_count": len(messages),
            "token_count": total_tokens,
            "role_distribution": role_counts,
            "compression_ratio": total_tokens / self.config.max_tokens,
            "latest_message": messages[-1].timestamp if messages else None
        }


# 全局上下文管理器
context_manager = ContextManager(ContextConfig())


async def get_context_manager() -> ContextManager:
    """获取上下文管理器"""
    return context_manager