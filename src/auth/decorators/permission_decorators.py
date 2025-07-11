"""
权限装饰器模块

重新导出权限框架中的装饰器，提供统一的权限检查接口
"""

from typing import Union, List, Callable
from src.auth.permission_framework.core import Permission, ResourceType
from src.auth.permission_framework.decorators import (
    require_permission as _require_permission,
    require_kb_permission as _require_kb_permission,
    require_chat_permission as _require_chat_permission,
    require_mcp_permission as _require_mcp_permission,
    require_file_permission as _require_file_permission,
    require_graph_permission as _require_graph_permission,
    require_user_profile_permission as _require_user_profile_permission,
    require_system_permission as _require_system_permission,
    require_any_permission as _require_any_permission,
    require_all_permissions as _require_all_permissions,
    ResourceExtractor
)

# 重新导出主要的权限装饰器
def require_permission(
    permission: Union[Permission, str],
    resource_extractor: Callable = None,
    resource_type: ResourceType = None,
    resource_id_param: str = None,
    allow_owner: bool = True,
    custom_check: Callable = None,
    namespace: str = None
):
    """通用权限检查装饰器"""
    return _require_permission(
        permission=permission,
        resource_extractor=resource_extractor,
        resource_type=resource_type,
        resource_id_param=resource_id_param,
        allow_owner=allow_owner,
        custom_check=custom_check,
        namespace=namespace
    )

def require_kb_permission(permission: Union[Permission, str], resource_id_param: str = "db_id", namespace: str = None):
    """知识库权限装饰器"""
    return _require_kb_permission(permission, resource_id_param, namespace)

def require_chat_permission(permission: Union[Permission, str], resource_id_param: str = "session_id", namespace: str = None):
    """对话权限装饰器"""
    return _require_chat_permission(permission, resource_id_param, namespace)

def require_mcp_permission(tool_name: str, namespace: str = None):
    """MCP工具权限装饰器"""
    return _require_mcp_permission(tool_name, namespace)

def require_file_permission(permission: Union[Permission, str], path_param: str = "file_path", namespace: str = None):
    """文件系统权限装饰器"""
    return _require_file_permission(permission, path_param, namespace)

def require_graph_permission(permission: Union[Permission, str], graph_id_param: str = "graph_id", namespace: str = None):
    """图谱数据权限装饰器"""
    return _require_graph_permission(permission, graph_id_param, namespace)

def require_user_profile_permission(permission: Union[Permission, str], user_id_param: str = "user_id", namespace: str = None):
    """用户资料权限装饰器"""
    return _require_user_profile_permission(permission, user_id_param, namespace)

def require_system_permission(permission: Union[Permission, str]):
    """系统级权限装饰器（不涉及特定资源）"""
    return _require_system_permission(permission)

def require_any_permission(permissions: List[Union[Permission, str]], **kwargs):
    """需要任一权限的装饰器"""
    return _require_any_permission(permissions, **kwargs)

def require_all_permissions(permissions: List[Union[Permission, str]], **kwargs):
    """需要所有权限的装饰器"""
    return _require_all_permissions(permissions, **kwargs)

# 导出资源提取器
class ResourceExtractors:
    """资源提取器集合"""
    
    @staticmethod
    def from_path_param(param_name: str, resource_type: ResourceType, namespace: str = None):
        """从路径参数提取资源"""
        return ResourceExtractor.from_path_param(param_name, resource_type, namespace)
    
    @staticmethod
    def from_query_param(param_name: str, resource_type: ResourceType, namespace: str = None):
        """从查询参数提取资源"""
        return ResourceExtractor.from_query_param(param_name, resource_type, namespace)
    
    @staticmethod
    def from_function_param(param_name: str, resource_type: ResourceType, namespace: str = None):
        """从函数参数提取资源"""
        return ResourceExtractor.from_function_param(param_name, resource_type, namespace)

# 便捷权限常量
class PermissionActions:
    """权限动作常量"""
    READ = Permission.READ
    WRITE = Permission.WRITE
    CREATE = Permission.CREATE
    DELETE = Permission.DELETE
    EXECUTE = Permission.EXECUTE
    UPDATE = Permission.UPDATE
    SHARE = Permission.SHARE
    ADMIN = Permission.ADMIN

# 导出所有主要函数和类
__all__ = [
    "require_permission",
    "require_kb_permission",
    "require_chat_permission",
    "require_mcp_permission",
    "require_file_permission",
    "require_graph_permission",
    "require_user_profile_permission",
    "require_system_permission",
    "require_any_permission",
    "require_all_permissions",
    "ResourceExtractors",
    "PermissionActions",
    "Permission",
    "ResourceType",
]