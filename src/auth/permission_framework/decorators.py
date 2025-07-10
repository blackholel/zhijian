"""
通用权限装饰器系统
提供声明式的权限检查接口
"""

from functools import wraps
from typing import Callable, Union, Dict, Any, Optional
from fastapi import Depends, HTTPException, Request
import inspect
from datetime import datetime
import logging

from .core import Permission, ResourceType, ResourceIdentifier, PermissionContext
from .concrete_resources import ResourceFactory
from .engine import PermissionEngine
from src.auth.models.user_models import User

logger = logging.getLogger(__name__)

class ResourceExtractor:
    """资源提取器"""
    
    @staticmethod
    def from_path_param(param_name: str, resource_type: ResourceType, namespace: str = None):
        """从路径参数提取资源"""
        def extractor(request: Request) -> 'Resource':
            resource_id = request.path_params.get(param_name)
            if not resource_id:
                raise HTTPException(400, f"Missing path parameter: {param_name}")
            
            identifier = ResourceIdentifier(resource_type, resource_id, namespace)
            return ResourceFactory.create_resource(identifier)
        return extractor
    
    @staticmethod
    def from_query_param(param_name: str, resource_type: ResourceType, namespace: str = None):
        """从查询参数提取资源"""
        def extractor(request: Request) -> 'Resource':
            resource_id = request.query_params.get(param_name)
            if not resource_id:
                raise HTTPException(400, f"Missing query parameter: {param_name}")
            
            identifier = ResourceIdentifier(resource_type, resource_id, namespace)
            return ResourceFactory.create_resource(identifier)
        return extractor
    
    @staticmethod
    def from_function_param(param_name: str, resource_type: ResourceType, namespace: str = None):
        """从函数参数提取资源"""
        def extractor(bound_args) -> 'Resource':
            resource_id = bound_args.arguments.get(param_name)
            if not resource_id:
                raise HTTPException(400, f"Missing function parameter: {param_name}")
            
            identifier = ResourceIdentifier(resource_type, resource_id, namespace)
            return ResourceFactory.create_resource(identifier)
        return extractor

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
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 提取请求和用户信息
            request = None
            current_user = None
            
            # 从函数参数中提取request和user
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            for param_name, param_value in bound_args.arguments.items():
                if isinstance(param_value, Request):
                    request = param_value
                elif hasattr(param_value, 'id') and hasattr(param_value, 'username'):  # User对象
                    current_user = param_value
            
            if not current_user:
                raise HTTPException(401, "Authentication required")
            
            # 提取资源
            resource = None
            if resource_extractor:
                if request:
                    resource = resource_extractor(request)
                else:
                    resource = resource_extractor(bound_args)
            elif resource_type and resource_id_param:
                # 从参数中提取资源ID
                resource_id = bound_args.arguments.get(resource_id_param)
                if resource_id:
                    identifier = ResourceIdentifier(resource_type, resource_id, namespace)
                    resource = ResourceFactory.create_resource(identifier)
            
            # 转换权限枚举
            perm = permission if isinstance(permission, Permission) else Permission(permission)
            
            # 创建权限上下文 - 优先使用external_user_id（外部JWT用户）
            user_id = getattr(current_user, 'external_user_id', None) or str(current_user.id)
            context = PermissionContext(
                user_id=user_id,
                resource=resource,
                permission=perm,
                request_metadata={
                    "endpoint": func.__name__,
                    "method": getattr(request, 'method', 'UNKNOWN') if request else 'UNKNOWN',
                    "user_agent": getattr(request.headers, 'user-agent', '') if request and hasattr(request, 'headers') else '',
                },
                timestamp=datetime.now(),
                ip_address=getattr(request.client, 'host', None) if request and hasattr(request, 'client') else None
            )
            
            # 自定义权限检查
            if custom_check and not await custom_check(context):
                raise HTTPException(403, "Custom permission check failed")
            
            # 执行权限检查
            engine = PermissionEngine.get_instance()
            result = await engine.check_permission(context)
            
            if not result.allowed:
                logger.warning(f"Permission denied for user {current_user.id} on {resource.uri if resource else 'system'}: {result.reason}")
                raise HTTPException(403, f"Permission denied: {result.reason}")
            
            # 权限检查通过，执行原函数
            logger.debug(f"Permission granted for user {current_user.id} on {resource.uri if resource else 'system'} via {result.strategy_used}")
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# 便捷的装饰器
def require_kb_permission(permission: Union[Permission, str], resource_id_param: str = "db_id", namespace: str = None):
    """知识库权限装饰器"""
    return require_permission(
        permission=permission,
        resource_type=ResourceType.KNOWLEDGE_BASE,
        resource_id_param=resource_id_param,
        namespace=namespace
    )

def require_chat_permission(permission: Union[Permission, str], resource_id_param: str = "session_id", namespace: str = None):
    """对话权限装饰器"""
    return require_permission(
        permission=permission,
        resource_type=ResourceType.CHAT_SESSION,
        resource_id_param=resource_id_param,
        namespace=namespace
    )

def require_mcp_permission(tool_name: str, namespace: str = None):
    """MCP工具权限装饰器"""
    def extractor(request_or_args) -> 'Resource':
        identifier = ResourceIdentifier(ResourceType.MCP_TOOL, tool_name, namespace)
        return ResourceFactory.create_resource(identifier)
    
    return require_permission(
        permission=Permission.EXECUTE,
        resource_extractor=extractor
    )

def require_file_permission(permission: Union[Permission, str], path_param: str = "file_path", namespace: str = None):
    """文件系统权限装饰器"""
    return require_permission(
        permission=permission,
        resource_type=ResourceType.FILE_SYSTEM,
        resource_id_param=path_param,
        namespace=namespace
    )

def require_graph_permission(permission: Union[Permission, str], graph_id_param: str = "graph_id", namespace: str = None):
    """图谱数据权限装饰器"""
    return require_permission(
        permission=permission,
        resource_type=ResourceType.GRAPH_DATA,
        resource_id_param=graph_id_param,
        namespace=namespace
    )

def require_user_profile_permission(permission: Union[Permission, str], user_id_param: str = "user_id", namespace: str = None):
    """用户资料权限装饰器"""
    return require_permission(
        permission=permission,
        resource_type=ResourceType.USER_PROFILE,
        resource_id_param=user_id_param,
        namespace=namespace
    )

def require_system_permission(permission: Union[Permission, str]):
    """系统级权限装饰器（不涉及特定资源）"""
    return require_permission(
        permission=permission,
        resource_extractor=None  # 不提取资源，只检查系统级权限
    )

# 高级装饰器
def require_any_permission(permissions: list, **kwargs):
    """需要任一权限的装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs_inner):
            for perm in permissions:
                try:
                    # 尝试每个权限
                    decorated_func = require_permission(perm, **kwargs)(func)
                    return await decorated_func(*args, **kwargs_inner)
                except HTTPException as e:
                    if e.status_code != 403:
                        raise
                    continue  # 权限不足，尝试下一个
            
            # 所有权限都不满足
            raise HTTPException(403, f"Requires any of these permissions: {[str(p) for p in permissions]}")
        return wrapper
    return decorator

def require_all_permissions(permissions: list, **kwargs):
    """需要所有权限的装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs_inner):
            # 检查所有权限
            for perm in permissions:
                decorated_func = require_permission(perm, **kwargs)(lambda *a, **k: None)
                try:
                    await decorated_func(*args, **kwargs_inner)
                except HTTPException as e:
                    if e.status_code == 403:
                        raise HTTPException(403, f"Missing required permission: {perm}")
                    raise
            
            # 所有权限都满足，执行原函数
            return await func(*args, **kwargs_inner)
        return wrapper
    return decorator