"""
权限框架核心定义
包含资源类型、权限类型、上下文等核心概念
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import uuid

class ResourceType(Enum):
    """资源类型枚举"""
    KNOWLEDGE_BASE = "knowledge_base"
    CHAT_SESSION = "chat_session"
    GRAPH_DATA = "graph_data"
    MCP_TOOL = "mcp_tool"
    FILE_SYSTEM = "file_system"
    API_ENDPOINT = "api_endpoint"
    USER_PROFILE = "user_profile"
    SYSTEM_CONFIG = "system_config"

class Permission(Enum):
    """通用权限枚举"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    EXECUTE = "execute"
    SHARE = "share"
    CREATE = "create"
    UPDATE = "update"

@dataclass
class ResourceIdentifier:
    """统一资源标识符"""
    resource_type: ResourceType
    resource_id: str
    namespace: Optional[str] = None  # 支持命名空间隔离
    
    def __str__(self) -> str:
        if self.namespace:
            return f"{self.namespace}:{self.resource_type.value}:{self.resource_id}"
        return f"{self.resource_type.value}:{self.resource_id}"
    
    @classmethod
    def parse(cls, resource_uri: str) -> 'ResourceIdentifier':
        """从URI字符串解析资源标识符"""
        parts = resource_uri.split(':')
        if len(parts) == 3:
            return cls(ResourceType(parts[1]), parts[2], parts[0])
        elif len(parts) == 2:
            return cls(ResourceType(parts[0]), parts[1])
        else:
            raise ValueError(f"Invalid resource URI: {resource_uri}")

@dataclass
class PermissionContext:
    """权限检查上下文"""
    user_id: str
    resource: 'Resource'
    permission: Permission
    request_metadata: Dict[str, Any]
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now()

class PermissionResult:
    """权限检查结果"""
    def __init__(self, allowed: bool, reason: str = "", strategy_used: str = "", metadata: Dict[str, Any] = None):
        self.allowed = allowed
        self.reason = reason
        self.strategy_used = strategy_used
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
    
    def __bool__(self) -> bool:
        return self.allowed