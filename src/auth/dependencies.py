"""
Auth dependencies module

提供认证和权限相关的依赖注入函数
"""

from typing import Optional
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials

from src.database.repositories.user_repository import UserRepository
from src.database.manager import get_user_repository_dependency
from src.auth.models.user_models import User
from src.auth.middleware.rbac_middleware import (
    rbac_middleware,
    security,
    get_current_user as _get_current_user,
    get_required_user as _get_required_user,
    get_admin_user as _get_admin_user,
    get_superadmin_user as _get_superadmin_user,
    require_permission as _require_permission,
    require_any_permission as _require_any_permission,
    is_public_path as _is_public_path,
    get_db as _get_db
)

# 重新导出主要的依赖函数
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    user_repo: UserRepository = Depends(get_user_repository_dependency)
) -> Optional[User]:
    """获取当前用户"""
    return await _get_current_user(request, credentials, user_repo)

async def get_required_user(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """获取已登录用户"""
    return await _get_required_user(current_user)

async def get_admin_user(
    current_user: User = Depends(get_required_user)
) -> User:
    """获取管理员用户"""
    return await _get_admin_user(current_user)

async def get_superadmin_user(
    current_user: User = Depends(get_required_user)
) -> User:
    """获取超级管理员用户"""
    return await _get_superadmin_user(current_user)

def require_permission(permission: str):
    """权限依赖注入函数"""
    return _require_permission(permission)

def require_any_permission(permissions: list):
    """需要任一权限装饰器"""
    return _require_any_permission(permissions)

def is_public_path(path: str) -> bool:
    """检查路径是否为公开路径"""
    return _is_public_path(path)

# 获取数据库会话
async def get_db():
    """获取数据库会话"""
    async for db in _get_db():
        yield db

# 权限验证函数
async def verify_permission(user: User, permission: str, user_repo: UserRepository = None) -> bool:
    """验证用户权限"""
    return await rbac_middleware.verify_permission(user, permission, user_repo)

async def get_user_permissions(user: User):
    """获取用户权限"""
    return await rbac_middleware.get_user_permissions(user)

async def invalidate_user_cache(user_id: str):
    """清除用户权限缓存"""
    return await rbac_middleware.invalidate_user_cache(user_id)

# 导出所有主要函数
__all__ = [
    "get_current_user",
    "get_required_user", 
    "get_admin_user",
    "get_superadmin_user",
    "require_permission",
    "require_any_permission",
    "is_public_path",
    "get_db",
    "verify_permission",
    "get_user_permissions",
    "invalidate_user_cache",
]