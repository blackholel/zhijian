"""
通用权限管理框架
支持可扩展的资源级权限控制
"""

from .core import ResourceType, Permission, ResourceIdentifier, PermissionContext, PermissionResult
from .resources import Resource
from .engine import PermissionEngine
from .decorators import (
    require_permission, require_kb_permission, require_chat_permission,
    require_mcp_permission, require_file_permission, require_graph_permission,
    require_user_profile_permission, require_system_permission
)
from .concrete_resources import (
    KnowledgeBaseResource, ChatSessionResource, MCPToolResource,
    GraphDataResource, FileSystemResource, UserProfileResource, ResourceFactory
)
from .manager import get_permission_framework, initialize_permission_framework, shutdown_permission_framework

__all__ = [
    # 核心组件
    'ResourceType', 'Permission', 'ResourceIdentifier', 'PermissionContext', 'PermissionResult',
    'Resource', 'PermissionEngine',
    
    # 装饰器
    'require_permission', 'require_kb_permission', 'require_chat_permission',
    'require_mcp_permission', 'require_file_permission', 'require_graph_permission',
    'require_user_profile_permission', 'require_system_permission',
    
    # 资源类型
    'KnowledgeBaseResource', 'ChatSessionResource', 'MCPToolResource',
    'GraphDataResource', 'FileSystemResource', 'UserProfileResource', 'ResourceFactory',
    
    # 管理器
    'get_permission_framework', 'initialize_permission_framework', 'shutdown_permission_framework'
]