"""
智能体权限装饰器

提供智能体相关的权限控制装饰器
"""

from functools import wraps
from typing import List, Optional, Callable, Any
from fastapi import HTTPException, Depends
import logging

from ..dependencies import get_current_user
from ..models.user_models import User
from ..decorators.permission_decorators import require_permission, require_any_permission, require_all_permissions

logger = logging.getLogger(__name__)


def require_agent_permissions(
    min_role: Optional[str] = None,
    required_permissions: Optional[List[str]] = None,
    require_all: bool = False
):
    """
    智能体权限装饰器
    
    Args:
        min_role: 最小角色要求 (user, power_user, admin, superadmin)
        required_permissions: 所需权限列表
        require_all: 是否需要所有权限 (True: 需要所有权限, False: 需要任意权限)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取当前用户
            current_user = None
            
            # 尝试从kwargs中获取current_user
            if 'current_user' in kwargs:
                current_user = kwargs['current_user']
            
            # 如果没有找到，尝试从依赖注入中获取
            if current_user is None:
                try:
                    current_user = await get_current_user()  # 这里可能需要传递请求对象
                except Exception:
                    raise HTTPException(
                        status_code=401,
                        detail="用户未认证"
                    )
            
            # 检查最小角色要求
            if min_role and not await _check_min_role(current_user, min_role):
                raise HTTPException(
                    status_code=403,
                    detail=f"需要 {min_role} 或更高权限"
                )
            
            # 检查权限要求
            if required_permissions:
                if require_all:
                    # 需要所有权限
                    if not await _check_all_permissions(current_user, required_permissions):
                        raise HTTPException(
                            status_code=403,
                            detail=f"需要所有权限: {', '.join(required_permissions)}"
                        )
                else:
                    # 需要任意权限
                    if not await _check_any_permission(current_user, required_permissions):
                        raise HTTPException(
                            status_code=403,
                            detail=f"需要以下权限之一: {', '.join(required_permissions)}"
                        )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_agent_creation_permission(func: Callable) -> Callable:
    """智能体创建权限装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 检查智能体创建权限
        return await require_permission("agent:create")(func)(*args, **kwargs)
    return wrapper


def require_agent_management_permission(func: Callable) -> Callable:
    """智能体管理权限装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 检查智能体管理权限
        return await require_any_permission([
            "agent:manage", 
            "agent:admin", 
            "system:admin"
        ])(func)(*args, **kwargs)
    return wrapper


def require_research_permission(func: Callable) -> Callable:
    """研究功能权限装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # 检查研究功能权限
        return await require_any_permission([
            "research:execute",
            "research:manage",
            "agent:research"
        ])(func)(*args, **kwargs)
    return wrapper


def require_knowledge_base_access(kb_ids: Optional[List[str]] = None):
    """
    知识库访问权限装饰器
    
    Args:
        kb_ids: 需要访问的知识库ID列表
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail="用户未认证"
                )
            
            # 如果指定了知识库ID，检查访问权限
            if kb_ids:
                for kb_id in kb_ids:
                    if not await _check_knowledge_base_access(current_user, kb_id):
                        raise HTTPException(
                            status_code=403,
                            detail=f"没有访问知识库 {kb_id} 的权限"
                        )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_mcp_tool_access(tool_names: Optional[List[str]] = None):
    """
    MCP工具访问权限装饰器
    
    Args:
        tool_names: 需要访问的工具名称列表
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail="用户未认证"
                )
            
            # 如果指定了工具名称，检查访问权限
            if tool_names:
                for tool_name in tool_names:
                    if not await _check_mcp_tool_access(current_user, tool_name):
                        raise HTTPException(
                            status_code=403,
                            detail=f"没有访问工具 {tool_name} 的权限"
                        )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_agent_ownership(func: Callable) -> Callable:
    """智能体所有权装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="用户未认证"
            )
        
        # 尝试从参数中获取agent_id
        agent_id = kwargs.get('agent_id')
        if not agent_id:
            # 从路径参数中获取
            for arg in args:
                if isinstance(arg, str) and arg.startswith('agent_'):
                    agent_id = arg
                    break
        
        if agent_id:
            # 检查智能体所有权
            if not await _check_agent_ownership(current_user, agent_id):
                raise HTTPException(
                    status_code=403,
                    detail="没有访问此智能体的权限"
                )
        
        return await func(*args, **kwargs)
    return wrapper


# 辅助函数

async def _check_min_role(user: User, min_role: str) -> bool:
    """检查最小角色要求"""
    role_hierarchy = {
        "user": 0,
        "power_user": 1,
        "admin": 2,
        "superadmin": 3
    }
    
    try:
        # 获取用户角色
        user_roles = [role.name for role in user.roles]
        
        # 检查用户是否有足够的角色权限
        min_level = role_hierarchy.get(min_role, 0)
        
        for role_name in user_roles:
            user_level = role_hierarchy.get(role_name, 0)
            if user_level >= min_level:
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"检查角色权限失败: {e}")
        return False


async def _check_any_permission(user: User, permissions: List[str]) -> bool:
    """检查是否有任意权限"""
    try:
        from ..services.permission_service import PermissionService
        
        permission_service = PermissionService()
        
        for permission in permissions:
            if await permission_service.has_permission(user, permission):
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"检查权限失败: {e}")
        return False


async def _check_all_permissions(user: User, permissions: List[str]) -> bool:
    """检查是否有所有权限"""
    try:
        from ..services.permission_service import PermissionService
        
        permission_service = PermissionService()
        
        for permission in permissions:
            if not await permission_service.has_permission(user, permission):
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"检查权限失败: {e}")
        return False


async def _check_knowledge_base_access(user: User, kb_id: str) -> bool:
    """检查知识库访问权限"""
    try:
        from ..services.permission_service import PermissionService
        
        permission_service = PermissionService()
        
        # 检查通用知识库权限
        if await permission_service.has_permission(user, "kb:read"):
            return True
        
        # 检查特定知识库权限
        specific_permission = f"kb:read:{kb_id}"
        if await permission_service.has_permission(user, specific_permission):
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"检查知识库访问权限失败: {e}")
        return False


async def _check_mcp_tool_access(user: User, tool_name: str) -> bool:
    """检查MCP工具访问权限"""
    try:
        from ..services.permission_service import PermissionService
        
        permission_service = PermissionService()
        
        # 检查通用工具权限
        if await permission_service.has_permission(user, "tool:use"):
            return True
        
        # 检查特定工具权限
        specific_permission = f"tool:use:{tool_name}"
        if await permission_service.has_permission(user, specific_permission):
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"检查工具访问权限失败: {e}")
        return False


async def _check_agent_ownership(user: User, agent_id: str) -> bool:
    """检查智能体所有权"""
    try:
        from src.agents.manager import agent_manager
        
        agent = await agent_manager.get_agent(agent_id)
        if not agent:
            return False
        
        # 检查是否是智能体的所有者
        if agent.config.user_id == str(user.id):
            return True
        
        # 检查是否有管理权限
        from ..services.permission_service import PermissionService
        permission_service = PermissionService()
        
        if await permission_service.has_permission(user, "agent:admin"):
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"检查智能体所有权失败: {e}")
        return False


# 预定义的权限组合装饰器

def require_basic_agent_access(func: Callable) -> Callable:
    """基础智能体访问权限"""
    return require_agent_permissions(
        min_role="user",
        required_permissions=["agent:use"]
    )(func)


def require_advanced_agent_access(func: Callable) -> Callable:
    """高级智能体访问权限"""
    return require_agent_permissions(
        min_role="power_user",
        required_permissions=["agent:create", "agent:manage"]
    )(func)


def require_system_agent_access(func: Callable) -> Callable:
    """系统智能体访问权限"""
    return require_agent_permissions(
        min_role="admin",
        required_permissions=["system:admin", "agent:admin"]
    )(func)