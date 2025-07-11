"""
智能体日志记录系统

参考 Suna 的结构化日志设计
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
from contextlib import contextmanager

from src.auth.models.agent_models import AgentLog
from src.database.repositories.base import BaseRepository


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogCategory(str, Enum):
    """日志分类"""
    EXECUTION = "execution"          # 执行日志
    PERMISSION = "permission"        # 权限日志
    ERROR = "error"                 # 错误日志
    STATE_CHANGE = "state_change"   # 状态变更日志
    TOOL_CALL = "tool_call"         # 工具调用日志
    KNOWLEDGE_QUERY = "knowledge_query"  # 知识库查询日志
    MCP_CALL = "mcp_call"           # MCP调用日志
    PERFORMANCE = "performance"     # 性能日志
    SECURITY = "security"           # 安全日志


class AgentLogger:
    """智能体日志记录器"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.logger = logging.getLogger(f"agent.{agent_id}")
        self.log_repo = BaseRepository(AgentLog)
        
        # 配置日志格式
        self._setup_logger()
    
    def _setup_logger(self):
        """设置日志记录器"""
        # 设置日志级别
        self.logger.setLevel(logging.DEBUG)
        
        # 创建格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 如果没有处理器，添加控制台处理器
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    async def log(
        self,
        level: LogLevel,
        message: str,
        category: LogCategory,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
        stack_trace: Optional[str] = None
    ):
        """记录日志"""
        try:
            # 记录到标准日志
            log_method = getattr(self.logger, level.value.lower())
            log_method(f"[{category.value}] {message}")
            
            # 记录到数据库
            if user_id:  # 只有提供用户ID时才记录到数据库
                await self._save_to_database(
                    level=level,
                    message=message,
                    category=category,
                    details=details or {},
                    context=context or {},
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                    stack_trace=stack_trace
                )
                
        except Exception as e:
            # 日志记录失败不应该影响主流程
            self.logger.error(f"记录日志失败: {e}")
    
    async def _save_to_database(
        self,
        level: LogLevel,
        message: str,
        category: LogCategory,
        details: Dict[str, Any],
        context: Dict[str, Any],
        session_id: Optional[str],
        task_id: Optional[str],
        user_id: str,
        stack_trace: Optional[str]
    ):
        """保存日志到数据库"""
        try:
            log_entry = AgentLog(
                agent_id=self.agent_id,
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
                log_level=level.value,
                message=message,
                category=category.value,
                details=details,
                context=context,
                stack_trace=stack_trace,
                timestamp=datetime.now()
            )
            
            await self.log_repo.create(log_entry)
            
        except Exception as e:
            # 数据库记录失败，只记录到标准日志
            self.logger.error(f"保存日志到数据库失败: {e}")
    
    async def debug(
        self,
        message: str,
        category: LogCategory = LogCategory.EXECUTION,
        **kwargs
    ):
        """记录调试日志"""
        await self.log(LogLevel.DEBUG, message, category, **kwargs)
    
    async def info(
        self,
        message: str,
        category: LogCategory = LogCategory.EXECUTION,
        **kwargs
    ):
        """记录信息日志"""
        await self.log(LogLevel.INFO, message, category, **kwargs)
    
    async def warning(
        self,
        message: str,
        category: LogCategory = LogCategory.EXECUTION,
        **kwargs
    ):
        """记录警告日志"""
        await self.log(LogLevel.WARNING, message, category, **kwargs)
    
    async def error(
        self,
        message: str,
        category: LogCategory = LogCategory.ERROR,
        **kwargs
    ):
        """记录错误日志"""
        await self.log(LogLevel.ERROR, message, category, **kwargs)
    
    async def critical(
        self,
        message: str,
        category: LogCategory = LogCategory.ERROR,
        **kwargs
    ):
        """记录严重错误日志"""
        await self.log(LogLevel.CRITICAL, message, category, **kwargs)
    
    async def log_state_change(
        self,
        old_state: str,
        new_state: str,
        user_id: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """记录状态变更"""
        await self.log(
            level=LogLevel.INFO,
            message=f"状态变更: {old_state} -> {new_state}",
            category=LogCategory.STATE_CHANGE,
            details={
                "old_state": old_state,
                "new_state": new_state
            },
            context=context,
            session_id=session_id,
            user_id=user_id
        )
    
    async def log_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        result: Any,
        execution_time: float,
        success: bool,
        user_id: str,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        error: Optional[str] = None
    ):
        """记录工具调用"""
        message = f"工具调用: {tool_name} ({'成功' if success else '失败'})"
        
        await self.log(
            level=LogLevel.INFO if success else LogLevel.ERROR,
            message=message,
            category=LogCategory.TOOL_CALL,
            details={
                "tool_name": tool_name,
                "parameters": parameters,
                "result": str(result)[:1000] if result else None,  # 限制长度
                "execution_time": execution_time,
                "success": success,
                "error": error
            },
            session_id=session_id,
            task_id=task_id,
            user_id=user_id
        )
    
    async def log_knowledge_query(
        self,
        query: str,
        kb_ids: list,
        result_count: int,
        execution_time: float,
        user_id: str,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None
    ):
        """记录知识库查询"""
        await self.log(
            level=LogLevel.INFO,
            message=f"知识库查询: {query[:50]}... (返回 {result_count} 个结果)",
            category=LogCategory.KNOWLEDGE_QUERY,
            details={
                "query": query,
                "kb_ids": kb_ids,
                "result_count": result_count,
                "execution_time": execution_time
            },
            session_id=session_id,
            task_id=task_id,
            user_id=user_id
        )
    
    async def log_mcp_call(
        self,
        tool_name: str,
        method: str,
        parameters: Dict[str, Any],
        result: Any,
        execution_time: float,
        success: bool,
        user_id: str,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        error: Optional[str] = None
    ):
        """记录MCP调用"""
        message = f"MCP调用: {tool_name}.{method} ({'成功' if success else '失败'})"
        
        await self.log(
            level=LogLevel.INFO if success else LogLevel.ERROR,
            message=message,
            category=LogCategory.MCP_CALL,
            details={
                "tool_name": tool_name,
                "method": method,
                "parameters": parameters,
                "result": str(result)[:1000] if result else None,
                "execution_time": execution_time,
                "success": success,
                "error": error
            },
            session_id=session_id,
            task_id=task_id,
            user_id=user_id
        )
    
    async def log_permission_check(
        self,
        permission: str,
        resource: str,
        granted: bool,
        user_id: str,
        session_id: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """记录权限检查"""
        message = f"权限检查: {permission} on {resource} ({'通过' if granted else '拒绝'})"
        
        await self.log(
            level=LogLevel.INFO if granted else LogLevel.WARNING,
            message=message,
            category=LogCategory.PERMISSION,
            details={
                "permission": permission,
                "resource": resource,
                "granted": granted,
                "reason": reason
            },
            session_id=session_id,
            user_id=user_id
        )
    
    async def log_performance(
        self,
        operation: str,
        execution_time: float,
        metrics: Dict[str, Any],
        user_id: str,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None
    ):
        """记录性能指标"""
        await self.log(
            level=LogLevel.INFO,
            message=f"性能指标: {operation} 耗时 {execution_time:.2f}s",
            category=LogCategory.PERFORMANCE,
            details={
                "operation": operation,
                "execution_time": execution_time,
                "metrics": metrics
            },
            session_id=session_id,
            task_id=task_id,
            user_id=user_id
        )
    
    async def log_security_event(
        self,
        event_type: str,
        description: str,
        severity: str,
        user_id: str,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """记录安全事件"""
        level_map = {
            "low": LogLevel.INFO,
            "medium": LogLevel.WARNING,
            "high": LogLevel.ERROR,
            "critical": LogLevel.CRITICAL
        }
        
        await self.log(
            level=level_map.get(severity, LogLevel.WARNING),
            message=f"安全事件: {event_type} - {description}",
            category=LogCategory.SECURITY,
            details={
                "event_type": event_type,
                "severity": severity,
                **(details or {})
            },
            session_id=session_id,
            user_id=user_id
        )
    
    @contextmanager
    def log_execution_context(
        self,
        operation: str,
        user_id: str,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None
    ):
        """执行上下文日志记录"""
        start_time = datetime.now()
        
        try:
            # 记录开始
            self.logger.info(f"开始执行: {operation}")
            yield
            
            # 记录成功完成
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.info(f"执行完成: {operation} (耗时 {execution_time:.2f}s)")
            
            # 异步记录到数据库
            import asyncio
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(self.log_performance(
                    operation=operation,
                    execution_time=execution_time,
                    metrics={"status": "success"},
                    user_id=user_id,
                    session_id=session_id,
                    task_id=task_id
                ))
            
        except Exception as e:
            # 记录执行失败
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"执行失败: {operation} (耗时 {execution_time:.2f}s) - {str(e)}")
            
            # 异步记录到数据库
            import asyncio
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(self.error(
                    message=f"执行失败: {operation}",
                    category=LogCategory.EXECUTION,
                    details={
                        "operation": operation,
                        "execution_time": execution_time,
                        "error": str(e)
                    },
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                    stack_trace=str(e)
                ))
            
            raise
    
    async def get_logs(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        category: Optional[LogCategory] = None,
        level: Optional[LogLevel] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list:
        """获取日志记录"""
        try:
            # 构建查询条件
            filters = {
                "agent_id": self.agent_id,
                "user_id": user_id
            }
            
            if session_id:
                filters["session_id"] = session_id
            if task_id:
                filters["task_id"] = task_id
            if category:
                filters["category"] = category.value
            if level:
                filters["log_level"] = level.value
            
            # 查询日志
            logs = await self.log_repo.list_by_filters(
                filters=filters,
                limit=limit,
                offset=offset,
                order_by="timestamp",
                desc=True
            )
            
            return [
                {
                    "id": str(log.id),
                    "timestamp": log.timestamp.isoformat(),
                    "level": log.log_level,
                    "category": log.category,
                    "message": log.message,
                    "details": log.details,
                    "context": log.context,
                    "session_id": log.session_id,
                    "task_id": log.task_id
                }
                for log in logs
            ]
            
        except Exception as e:
            self.logger.error(f"获取日志记录失败: {e}")
            return []


# 全局日志记录器缓存
_loggers: Dict[str, AgentLogger] = {}


def get_agent_logger(agent_id: str) -> AgentLogger:
    """获取智能体日志记录器"""
    if agent_id not in _loggers:
        _loggers[agent_id] = AgentLogger(agent_id)
    return _loggers[agent_id]


def cleanup_loggers():
    """清理日志记录器缓存"""
    global _loggers
    _loggers.clear()