from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Set, Optional, Callable
import re
import logging

from server.db_manager import db_manager
from server.models.user_model import User
from server.auth.external_jwt_processor import ExternalJWTProcessor, JWTAuthenticationError
from server.utils.redis_manager import get_permission_cache

logger = logging.getLogger(__name__)

# 使用Bearer token认证
security = HTTPBearer(auto_error=False)

# 公开路径列表，无需登录即可访问
PUBLIC_PATHS = [
    r"^/api/auth/token$",            # 登录（保留兼容性）
    r"^/api/auth/check-first-run$",  # 检查是否首次运行
    r"^/api/auth/initialize$",       # 初始化系统
    r"^/api$",                      # Health Check
    r"^/api/login$",                # 登录页面
    r"^/api/info$",                 # 获取系统信息配置
    r"^/api/info/.*$",              # 系统信息配置相关接口
    r"^/docs$",                     # API文档
    r"^/redoc$",                    # API文档
    r"^/openapi.json$",             # OpenAPI schema
]

# 获取数据库会话
def get_db():
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()

class RBACMiddleware:
    """RBAC权限中间件"""
    
    def __init__(self):
        self.permission_cache = get_permission_cache()
    
    async def get_current_user(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        db: Session = Depends(get_db)
    ) -> Optional[User]:
        """获取当前用户"""
        
        # 检查是否为公开路径
        if self.is_public_path(request.url.path):
            return None
        
        # 检查是否有Authorization头
        if not credentials:
            return None
        
        token = credentials.credentials
        if not token:
            return None
        
        try:
            # 使用外部JWT处理器获取用户
            user = ExternalJWTProcessor.get_user_from_token(token, db)
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的用户token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="用户账户已被禁用",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            return user
            
        except JWTAuthenticationError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="认证失败",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    async def get_required_user(
        self,
        current_user: Optional[User] = Depends(lambda: rbac_middleware.get_current_user)
    ) -> User:
        """获取已登录用户（抛出401如果未登录）"""
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请登录后再访问",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return current_user
    
    async def verify_permission(self, user: User, permission: str, db: Session) -> bool:
        """验证用户权限"""
        if not user:
            return False
        
        try:
            # 从缓存获取用户权限
            user_permissions = self.permission_cache.get_user_permissions(str(user.id), db)
            
            # 检查精确权限
            if permission in user_permissions:
                return True
            
            # 检查通配符权限
            resource_type = permission.split(':')[0] if ':' in permission else ''
            wildcard_permission = f"{resource_type}:*"
            if wildcard_permission in user_permissions:
                return True
            
            # 检查超级权限
            if "*:*" in user_permissions:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Permission verification error: {e}")
            return False
    
    def require_permission(self, permission: str):
        """权限依赖注入函数"""
        async def permission_dependency(
            current_user: User = Depends(get_required_user),
            db: Session = Depends(get_db)
        ):
            """检查用户权限的依赖函数"""
            has_permission = await self.verify_permission(current_user, permission, db)
            
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"需要权限: {permission}"
                )
            
            return current_user
        
        return permission_dependency
    
    def require_any_permission(self, permissions: list):
        """需要任一权限装饰器"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # 获取当前用户和数据库会话
                current_user = None
                db = None
                
                for key, value in kwargs.items():
                    if isinstance(value, User):
                        current_user = value
                    elif hasattr(value, 'query'):
                        db = value
                
                if not current_user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="用户未认证"
                    )
                
                if not db:
                    db = db_manager.get_session()
                    try:
                        has_any_permission = any(
                            await self.verify_permission(current_user, perm, db)
                            for perm in permissions
                        )
                    finally:
                        db.close()
                else:
                    has_any_permission = any(
                        await self.verify_permission(current_user, perm, db)
                        for perm in permissions
                    )
                
                if not has_any_permission:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"需要以下权限之一: {', '.join(permissions)}"
                    )
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def is_public_path(self, path: str) -> bool:
        """检查路径是否为公开路径"""
        path = path.rstrip('/')  # 去除尾部斜杠
        for pattern in PUBLIC_PATHS:
            if re.match(pattern, path):
                return True
        return False
    
    def get_user_permissions(self, user: User, db: Session) -> Set[str]:
        """获取用户所有权限"""
        if not user:
            return set()
        
        return self.permission_cache.get_user_permissions(str(user.id), db)
    
    def invalidate_user_cache(self, user_id: str):
        """清除用户权限缓存"""
        self.permission_cache.invalidate_user_permissions(user_id)


# 全局RBAC中间件实例
rbac_middleware = RBACMiddleware()

# 便捷的依赖注入函数
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """获取当前用户"""
    return await rbac_middleware.get_current_user(request, credentials, db)

async def get_required_user(
    current_user: Optional[User] = Depends(get_current_user)
) -> User:
    """获取已登录用户"""
    return await rbac_middleware.get_required_user(current_user)

def require_permission(permission: str):
    """权限依赖注入函数"""
    return rbac_middleware.require_permission(permission)

def require_any_permission(permissions: list):
    """需要任一权限装饰器"""
    return rbac_middleware.require_any_permission(permissions)

# 兼容性函数（保持与旧版本的兼容）
async def get_admin_user(current_user: User = Depends(get_required_user)) -> User:
    """获取管理员用户（兼容性函数）"""
    db = db_manager.get_session()
    try:
        admin_permissions = ["user:create", "user:update", "user:delete", "system:config"]
        has_admin_permission = any(
            await rbac_middleware.verify_permission(current_user, perm, db)
            for perm in admin_permissions
        )
        
        if not has_admin_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限",
            )
        
        return current_user
    finally:
        db.close()

async def get_superadmin_user(current_user: User = Depends(get_required_user)) -> User:
    """获取超级管理员用户（兼容性函数）"""
    db = db_manager.get_session()
    try:
        has_superadmin_permission = await rbac_middleware.verify_permission(
            current_user, "system:restart", db
        )
        
        if not has_superadmin_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要超级管理员权限",
            )
        
        return current_user
    finally:
        db.close()

def is_public_path(path: str) -> bool:
    """检查路径是否为公开路径"""
    return rbac_middleware.is_public_path(path)