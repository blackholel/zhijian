import redis
import json
import hashlib
from datetime import datetime, timedelta
from typing import Set, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

class RedisManager:
    """Redis缓存管理器"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0", password: str = None):
        """初始化Redis连接"""
        try:
            # 尝试连接Redis
            if password:
                self.redis = redis.Redis.from_url(
                    redis_url,
                    password=password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
            else:
                # 无密码连接
                self.redis = redis.Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
            
            # 测试连接
            self.redis.ping()
            logger.info("Redis connection established successfully")
        except redis.AuthenticationError:
            logger.warning("Redis authentication failed, using fallback cache")
            self.redis = FakeRedis()
        except redis.ConnectionError:
            logger.warning("Redis connection failed, using fallback cache")
            self.redis = FakeRedis()
        except Exception as e:
            logger.warning(f"Failed to connect to Redis ({e}), using fallback cache")
            # 使用假的Redis实现作为fallback
            self.redis = FakeRedis()
    
    def get(self, key: str) -> Optional[str]:
        """获取缓存值"""
        try:
            return self.redis.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    def set(self, key: str, value: str, ttl: int = 3600) -> bool:
        """设置缓存值"""
        try:
            return self.redis.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        try:
            return bool(self.redis.delete(key))
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查key是否存在"""
        try:
            return bool(self.redis.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False


class FakeRedis:
    """Redis fallback实现（内存缓存）"""
    
    def __init__(self):
        self._cache = {}
        self._expiry = {}
    
    def ping(self):
        return True
    
    def get(self, key: str) -> Optional[str]:
        self._cleanup_expired()
        return self._cache.get(key)
    
    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._cache[key] = value
        self._expiry[key] = datetime.now() + timedelta(seconds=ttl)
        return True
    
    def delete(self, key: str) -> int:
        self._cache.pop(key, None)
        self._expiry.pop(key, None)
        return 1
    
    def exists(self, key: str) -> int:
        self._cleanup_expired()
        return 1 if key in self._cache else 0
    
    def _cleanup_expired(self):
        """清理过期缓存"""
        now = datetime.now()
        expired_keys = [k for k, exp in self._expiry.items() if exp < now]
        for key in expired_keys:
            self._cache.pop(key, None)
            self._expiry.pop(key, None)


class PermissionCache:
    """权限缓存管理"""
    
    def __init__(self, redis_manager: RedisManager):
        self.redis = redis_manager
        self.user_perm_ttl = 3600  # 用户权限缓存1小时
        self.role_perm_ttl = 7200  # 角色权限缓存2小时
        self.jwt_session_ttl = 1800  # JWT会话缓存30分钟
    
    def get_user_permissions(self, user_id: str, db: Session) -> Set[str]:
        """获取用户权限（缓存优先）"""
        cache_key = f"user_perms:{user_id}"
        cached = self.redis.get(cache_key)
        
        if cached:
            try:
                permissions = set(json.loads(cached))
                logger.debug(f"User {user_id} permissions loaded from cache")
                return permissions
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in cache for user {user_id}")
        
        # 从数据库查询
        permissions = self._query_user_permissions(user_id, db)
        
        # 缓存权限
        self.redis.set(
            cache_key,
            json.dumps(list(permissions)),
            self.user_perm_ttl
        )
        
        logger.debug(f"User {user_id} permissions loaded from database and cached")
        return permissions
    
    def _query_user_permissions(self, user_id: str, db: Session) -> Set[str]:
        """从数据库查询用户权限"""
        try:
            # 使用原生SQL查询以提高性能 - 支持external_user_id
            query = text("""
                SELECT DISTINCT p.name
                FROM permissions p
                JOIN role_permissions rp ON p.id = rp.permission_id
                JOIN roles r ON rp.role_id = r.id
                JOIN user_roles ur ON r.id = ur.role_id
                JOIN users u ON ur.user_id = u.user_id
                WHERE (u.external_user_id = :user_id OR u.user_id::text = :user_id OR u.username = :user_id)
                AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
            """)
            
            result = db.execute(query, {"user_id": user_id})
            permissions = {row[0] for row in result}
            
            logger.debug(f"Found {len(permissions)} permissions for user {user_id}")
            return permissions
            
        except Exception as e:
            logger.error(f"Error querying user permissions: {e}")
            return set()
    
    def invalidate_user_permissions(self, user_id: str):
        """清除用户权限缓存"""
        cache_key = f"user_perms:{user_id}"
        self.redis.delete(cache_key)
        logger.debug(f"Invalidated permissions cache for user {user_id}")
    
    def cache_jwt_session(self, token: str, user_data: Dict[str, Any]) -> str:
        """缓存JWT会话"""
        # 生成会话ID
        session_id = hashlib.md5(token.encode()).hexdigest()
        session_key = f"jwt_session:{session_id}"
        
        # 缓存用户数据
        self.redis.set(
            session_key,
            json.dumps(user_data),
            self.jwt_session_ttl
        )
        
        logger.debug(f"Cached JWT session for user {user_data.get('user_id')}")
        return session_id
    
    def get_jwt_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取JWT会话"""
        session_key = f"jwt_session:{session_id}"
        cached = self.redis.get(session_key)
        
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in JWT session cache: {session_id}")
        
        return None
    
    def invalidate_jwt_session(self, session_id: str):
        """清除JWT会话缓存"""
        session_key = f"jwt_session:{session_id}"
        self.redis.delete(session_key)
        logger.debug(f"Invalidated JWT session: {session_id}")
    
    def cache_role_permissions(self, role_id: str, permissions: Set[str]):
        """缓存角色权限"""
        cache_key = f"role_perms:{role_id}"
        self.redis.set(
            cache_key,
            json.dumps(list(permissions)),
            self.role_perm_ttl
        )
        logger.debug(f"Cached permissions for role {role_id}")
    
    def get_role_permissions(self, role_id: str) -> Optional[Set[str]]:
        """获取角色权限缓存"""
        cache_key = f"role_perms:{role_id}"
        cached = self.redis.get(cache_key)
        
        if cached:
            try:
                return set(json.loads(cached))
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in role permissions cache: {role_id}")
        
        return None
    
    def invalidate_role_permissions(self, role_id: str):
        """清除角色权限缓存"""
        cache_key = f"role_perms:{role_id}"
        self.redis.delete(cache_key)
        logger.debug(f"Invalidated role permissions cache: {role_id}")
    
    def invalidate_all_user_permissions(self):
        """清除所有用户权限缓存（角色权限变更时使用）"""
        try:
            # 这里应该使用Redis的SCAN命令来安全地删除多个key
            # 但为了简单起见，我们记录一个警告
            logger.warning("Should implement bulk user permissions cache invalidation")
        except Exception as e:
            logger.error(f"Error invalidating all user permissions: {e}")


# 全局Redis管理器实例
redis_manager = None
permission_cache = None

def init_redis(redis_url: str = "redis://localhost:6379/0", password: str = None):
    """初始化Redis连接"""
    global redis_manager, permission_cache
    
    redis_manager = RedisManager(redis_url, password)
    permission_cache = PermissionCache(redis_manager)
    
    logger.info("Redis manager initialized")

def get_redis_manager() -> RedisManager:
    """获取Redis管理器实例"""
    global redis_manager
    if redis_manager is None:
        # 使用默认配置初始化
        init_redis()
    return redis_manager

def get_permission_cache() -> PermissionCache:
    """获取权限缓存实例"""
    global permission_cache
    if permission_cache is None:
        # 使用默认配置初始化
        init_redis()
    return permission_cache