"""
智能体异常定义

参考 Suna 项目的错误处理机制
"""

from typing import Optional, Dict, Any


class AgentError(Exception):
    """Agent 基础异常"""
    
    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code or "AGENT_ERROR"
        self.details = details or {}


class AgentConfigError(AgentError):
    """Agent 配置错误"""
    
    def __init__(self, message: str, config_field: Optional[str] = None):
        super().__init__(message, "AGENT_CONFIG_ERROR")
        self.config_field = config_field


class AgentPermissionError(AgentError):
    """Agent 权限错误"""
    
    def __init__(self, message: str, required_permission: Optional[str] = None):
        super().__init__(message, "AGENT_PERMISSION_ERROR")
        self.required_permission = required_permission


class AgentInitializationError(AgentError):
    """Agent 初始化错误"""
    
    def __init__(self, message: str, initialization_step: Optional[str] = None):
        super().__init__(message, "AGENT_INIT_ERROR")
        self.initialization_step = initialization_step


class AgentExecutionError(AgentError):
    """Agent 执行错误"""
    
    def __init__(self, message: str, task_id: Optional[str] = None):
        super().__init__(message, "AGENT_EXECUTION_ERROR")
        self.task_id = task_id


class AgentRetryError(AgentError):
    """Agent 重试耗尽错误"""
    
    def __init__(self, message: str, max_attempts: int, last_error: Optional[Exception] = None):
        super().__init__(message, "AGENT_RETRY_ERROR")
        self.max_attempts = max_attempts
        self.last_error = last_error


class ToolNotFoundError(AgentError):
    """工具未找到错误"""
    
    def __init__(self, tool_name: str):
        message = f"Tool '{tool_name}' not found or not available"
        super().__init__(message, "TOOL_NOT_FOUND")
        self.tool_name = tool_name


class KnowledgeBaseNotFoundError(AgentError):
    """知识库未找到错误"""
    
    def __init__(self, kb_id: str):
        message = f"Knowledge base '{kb_id}' not found or not accessible"
        super().__init__(message, "KB_NOT_FOUND")
        self.kb_id = kb_id