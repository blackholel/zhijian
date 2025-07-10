from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Set, Optional, Callable
import re
import logging

from src.database.manager import get_database_manager_dependency, get_user_repository_dependency
from src.database.repositories.user_repository import UserRepository, UserInfo
from src.auth.models.user_models import User
from src.auth.utils.external_jwt_processor import ExternalJWTProcessor, JWTAuthenticationError

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

# 获取数据库会话（保持兼容性）
async def get_db():
    """获取数据库会话（兼容性函数）"""
    db_manager = await get_database_manager_dependency()
    async with await db_manager.get_postgresql_adapter('server_db').get_session_context() as session:
        yield session

class RBACMiddleware:
    """RBAC权限中间件"""
    
    def __init__(self):
        self.db_manager = None  # 将在需要时初始化
        self.redis_adapter = None
    
    async def get_current_user(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        user_repo: UserRepository = Depends(get_user_repository_dependency)
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
            logger.debug(f"Processing JWT token for authentication")
            user = await ExternalJWTProcessor.get_user_from_token(token, user_repo)
            
            if not user:
                logger.warning(f"JWT token processing returned no user")
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
        current_user: Optional[User] = Depends(lambda request, credentials, user_repo: rbac_middleware.get_current_user(request, credentials, user_repo))
    ) -> User:
        """获取已登录用户（抛出401如果未登录）"""
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请登录后再访问",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return current_user
    
    async def verify_permission(self, user: User, permission: str, user_repo: UserRepository = None) -> bool:
        """验证用户权限"""
        if not user:
            return False
        
        try:
            # 初始化数据库管理器
            if not self.db_manager:
                from src.database.manager import get_database_manager
                self.db_manager = get_database_manager()
                await self.db_manager.initialize()
            
            # 获取Redis适配器用于缓存
            if not self.redis_adapter:
                self.redis_adapter = await self.db_manager.get_redis_adapter()
            
            # 从缓存获取用户权限
            cache_key = f"user_perms:{user.id}"
            cached_permissions = None
            if self.redis_adapter and self.redis_adapter.is_available:
                cached_permissions = await self.redis_adapter.get(cache_key)
            
            if cached_permissions:
                import json
                # 检查cached_permissions的类型
                if isinstance(cached_permissions, list):
                    user_permissions = set(cached_permissions)
                elif isinstance(cached_permissions, str):
                    user_permissions = set(json.loads(cached_permissions))
                else:
                    logger.warning(f"Unexpected cached permissions type: {type(cached_permissions)}")
                    user_permissions = set()
                logger.debug(f"User {user.id} permissions loaded from cache")
            else:
                # 从数据库查询权限
                user_permissions = await self._query_user_permissions(str(user.id))
                
                # 缓存权限
                if self.redis_adapter and self.redis_adapter.is_available:
                    import json
                    await self.redis_adapter.set(cache_key, json.dumps(list(user_permissions)), 3600)
                
                logger.debug(f"User {user.id} permissions loaded from database and cached")
            
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
    
    async def _query_user_permissions(self, user_id: str) -> Set[str]:
        """从数据库查询用户权限"""
        try:
            postgres_adapter = await self.db_manager.get_postgresql_adapter('server_db')
            
            # 使用原生SQL查询以提高性能 - 支持external_user_id
            query = """
                SELECT DISTINCT p.name
                FROM permissions p
                JOIN role_permissions rp ON p.id = rp.permission_id
                JOIN roles r ON rp.role_id = r.id
                JOIN user_roles ur ON r.id = ur.role_id
                JOIN users u ON ur.user_id = u.user_id
                WHERE (u.external_user_id = :user_id OR u.user_id::text = :user_id OR u.username = :user_id)
                AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
            """
            
            result = await postgres_adapter.execute_query(query, {"user_id": user_id})
            permissions = {row[0] for row in result} if result else set()
            
            logger.debug(f"Found {len(permissions)} permissions for user {user_id}")
            return permissions
            
        except Exception as e:
            logger.error(f"Error querying user permissions: {e}")
            return set()
    
    def require_permission(self, permission: str):
        """权限依赖注入函数"""
        async def permission_dependency(
            current_user: User = Depends(get_required_user),
            user_repo: UserRepository = Depends(get_user_repository_dependency)
        ):
            """检查用户权限的依赖函数"""
            has_permission = await self.verify_permission(current_user, permission, user_repo)
            
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
                
                # 检查任一权限
                has_any_permission = any(
                    await self.verify_permission(current_user, perm)
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
    
    async def get_user_permissions(self, user: User) -> Set[str]:
        """获取用户所有权限"""
        if not user:
            return set()
        
        # 初始化数据库管理器
        if not self.db_manager:
            from src.database.manager import get_database_manager
            self.db_manager = get_database_manager()
            await self.db_manager.initialize()
        
        # 获取Redis适配器用于缓存
        if not self.redis_adapter:
            self.redis_adapter = await self.db_manager.get_redis_adapter()
        
        # 从缓存获取用户权限
        cache_key = f"user_perms:{user.id}"
        cached_permissions = None
        if self.redis_adapter and self.redis_adapter.is_available:
            cached_permissions = await self.redis_adapter.get(cache_key)
        
        if cached_permissions:
            import json
            # 检查cached_permissions的类型
            if isinstance(cached_permissions, list):
                return set(cached_permissions)
            elif isinstance(cached_permissions, str):
                return set(json.loads(cached_permissions))
            else:
                logger.warning(f"Unexpected cached permissions type: {type(cached_permissions)}")
                return set()
        else:
            # 从数据库查询权限
            user_permissions = await self._query_user_permissions(str(user.id))
            
            # 缓存权限
            if self.redis_adapter and self.redis_adapter.is_available:
                import json
                await self.redis_adapter.set(cache_key, json.dumps(list(user_permissions)), 3600)
            
            return user_permissions
    
    async def invalidate_user_cache(self, user_id: str):
        """清除用户权限缓存"""
        # 初始化Redis适配器
        if not self.redis_adapter:
            if not self.db_manager:
                from src.database.manager import get_database_manager
                self.db_manager = get_database_manager()
                await self.db_manager.initialize()
            self.redis_adapter = await self.db_manager.get_redis_adapter()
        
        if self.redis_adapter and self.redis_adapter.is_available:
            cache_key = f"user_perms:{user_id}"
            await self.redis_adapter.delete(cache_key)
            logger.debug(f"Invalidated permissions cache for user {user_id}")


# 全局RBAC中间件实例
rbac_middleware = RBACMiddleware()

# 便捷的依赖注入函数
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    user_repo: UserRepository = Depends(get_user_repository_dependency)
) -> Optional[User]:
    """获取当前用户"""
    return await rbac_middleware.get_current_user(request, credentials, user_repo)

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
    admin_permissions = ["user:create", "user:update", "user:delete", "system:config"]
    has_admin_permission = any(
        await rbac_middleware.verify_permission(current_user, perm)
        for perm in admin_permissions
    )
    
    if not has_admin_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    
    return current_user

async def get_superadmin_user(current_user: User = Depends(get_required_user)) -> User:
    """获取超级管理员用户（兼容性函数）"""
    has_superadmin_permission = await rbac_middleware.verify_permission(
        current_user, "system:restart"
    )
    
    if not has_superadmin_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    
    return current_user

def is_public_path(path: str) -> bool:
    """检查路径是否为公开路径"""
    return rbac_middleware.is_public_path(path)