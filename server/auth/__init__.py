"""Auth module - 统一认证授权模块"""

# 导入模型
from .models import (
    User, Role, Permission, UserRole, RolePermission, 
    UserPermissionCache, OperationLog
)

# 导入路由
from .routers import rbac_router, permission_router

# 导入中间件
from .middleware import get_required_user, require_permission, rbac_middleware

# 导入服务
from .services import UserService, RoleService, PermissionService

__all__ = [
    # Models
    "User", "Role", "Permission", "UserRole", "RolePermission", 
    "UserPermissionCache", "OperationLog",
    
    # Routers
    "rbac_router", "permission_router",
    
    # Middleware
    "get_required_user", "require_permission", "rbac_middleware",
    
    # Services
    "UserService", "RoleService", "PermissionService"
]