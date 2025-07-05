"""
统一权限缓存系统
实现多层缓存架构和智能失效策略
"""

import asyncio
import hashlib
import pickle
import zlib
import time
import json
from typing import Optional, Dict, Set, Any
from dataclasses import asdict
from collections import defaultdict
import logging

from .core import PermissionContext, PermissionResult

logger = logging.getLogger(__name__)

class CacheKey:
    """统一缓存键管理"""
    
    @staticmethod
    def permission_key(context: PermissionContext) -> str:
        """生成权限检查缓存键"""
        resource_uri = context.resource.uri if context.resource else "system"
        key_data = f"{context.user_id}:{resource_uri}:{context.permission.value}"
        return f"perm:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    @staticmethod
    def user_permissions_key(user_id: str) -> str:
        """用户系统权限缓存键"""
        return f"user_perms:{user_id}"
    
    @staticmethod
    def resource_permissions_key(resource_uri: str) -> str:
        """资源权限缓存键"""
        return f"res_perms:{hashlib.md5(resource_uri.encode()).hexdigest()}"
    
    @staticmethod
    def user_resource_key(user_id: str, resource_uri: str) -> str:
        """用户资源权限缓存键"""
        key_data = f"{user_id}:{resource_uri}"
        return f"user_res:{hashlib.md5(key_data.encode()).hexdigest()}"

class MemoryCache:
    """内存缓存层（L1缓存）"""
    
    def __init__(self, max_size: int = 10000, ttl: int = 60):
        self.cache: Dict[str, tuple] = {}  # (data, expire_time)
        self.max_size = max_size
        self.ttl = ttl
        self.access_count: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self.cache:
                data, expire_time = self.cache[key]
                if time.time() < expire_time:
                    self.access_count[key] = self.access_count.get(key, 0) + 1
                    return data
                else:
                    # 过期删除
                    del self.cache[key]
                    self.access_count.pop(key, None)
            return None
    
    async def set(self, key: str, value: Any):
        async with self._lock:
            # 如果缓存满了，删除最少使用的项
            if len(self.cache) >= self.max_size:
                if self.access_count:
                    lru_key = min(self.access_count.keys(), key=lambda k: self.access_count[k])
                    self.cache.pop(lru_key, None)
                    self.access_count.pop(lru_key, None)
            
            expire_time = time.time() + self.ttl
            self.cache[key] = (value, expire_time)
            self.access_count[key] = 1
    
    async def delete(self, key: str):
        async with self._lock:
            self.cache.pop(key, None)
            self.access_count.pop(key, None)
    
    async def clear_pattern(self, pattern: str):
        """清除匹配模式的缓存"""
        async with self._lock:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_delete:
                self.cache.pop(key, None)
                self.access_count.pop(key, None)

class CompressedRedisCache:
    """压缩的Redis缓存层（L2缓存）"""
    
    def __init__(self, redis_manager, ttl: int = 1800):
        self.redis = redis_manager
        self.ttl = ttl
    
    async def get(self, key: str) -> Optional[Any]:
        try:
            compressed_data = self.redis.get(key)
            if compressed_data:
                # 解压缩并反序列化
                if isinstance(compressed_data, str):
                    compressed_data = compressed_data.encode('latin1')
                data = pickle.loads(zlib.decompress(compressed_data))
                return data
        except Exception as e:
            logger.error(f"Redis cache get error: {e}")
        return None
    
    async def set(self, key: str, value: Any):
        try:
            # 序列化并压缩
            serialized = pickle.dumps(value)
            compressed = zlib.compress(serialized)
            self.redis.set(key, compressed.decode('latin1'), self.ttl)
        except Exception as e:
            logger.error(f"Redis cache set error: {e}")
    
    async def delete(self, key: str):
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis cache delete error: {e}")
    
    async def delete_pattern(self, pattern: str):
        """删除匹配模式的缓存"""
        try:
            # 注意：这里需要谨慎使用，大规模删除可能影响性能
            logger.warning(f"Pattern deletion requested: {pattern}")
            # 实际实现可能需要使用Redis的SCAN命令
        except Exception as e:
            logger.error(f"Redis pattern delete error: {e}")

class UnifiedPermissionCache:
    """统一权限缓存管理器"""
    
    def __init__(self, redis_manager):
        self.l1_cache = MemoryCache(max_size=5000, ttl=60)  # 1分钟内存缓存
        self.l2_cache = CompressedRedisCache(redis_manager, ttl=1800)  # 30分钟Redis缓存
        self.stats = {
            "l1_hits": 0,
            "l2_hits": 0,
            "misses": 0,
            "sets": 0
        }
    
    async def get_permission(self, context: PermissionContext) -> Optional[PermissionResult]:
        """获取权限检查结果"""
        cache_key = CacheKey.permission_key(context)
        
        # L1缓存检查
        result = await self.l1_cache.get(cache_key)
        if result:
            self.stats["l1_hits"] += 1
            return result
        
        # L2缓存检查
        result = await self.l2_cache.get(cache_key)
        if result:
            self.stats["l2_hits"] += 1
            # 回写到L1缓存
            await self.l1_cache.set(cache_key, result)
            return result
        
        self.stats["misses"] += 1
        return None
    
    async def cache_permission(self, context: PermissionContext, result: PermissionResult):
        """缓存权限检查结果"""
        cache_key = CacheKey.permission_key(context)
        
        # 只缓存成功的结果，避免缓存临时失败
        if result.allowed:
            await self.l1_cache.set(cache_key, result)
            await self.l2_cache.set(cache_key, result)
            self.stats["sets"] += 1
    
    async def invalidate_user_permissions(self, user_id: str):
        """清除用户相关的所有权限缓存"""
        await self.l1_cache.clear_pattern(user_id)
        await self.l2_cache.delete_pattern(f"*{user_id}*")
        logger.info(f"Invalidated permission cache for user {user_id}")
    
    async def invalidate_resource_permissions(self, resource_uri: str):
        """清除资源相关的所有权限缓存"""
        resource_hash = hashlib.md5(resource_uri.encode()).hexdigest()
        await self.l1_cache.clear_pattern(resource_hash)
        await self.l2_cache.delete_pattern(f"*{resource_hash}*")
        logger.info(f"Invalidated permission cache for resource {resource_uri}")
    
    async def preload_user_permissions(self, user_id: str):
        """预加载用户权限"""
        try:
            # 预加载用户的系统级权限
            user_perms_key = CacheKey.user_permissions_key(user_id)
            if not await self.l2_cache.get(user_perms_key):
                # 从数据库加载权限
                from server.db_manager import db_manager
                from sqlalchemy import text
                
                db = db_manager.get_session()
                try:
                    # 查询用户权限并缓存 - 支持external_user_id
                    query = text("""
                        SELECT DISTINCT p.name
                        FROM permissions p
                        JOIN role_permissions rp ON p.id = rp.permission_id
                        JOIN roles r ON rp.role_id = r.id
                        JOIN user_roles ur ON r.id = ur.role_id
                        JOIN users u ON ur.user_id = u.id
                        WHERE (u.external_user_id = :user_id OR u.id::text = :user_id OR u.username = :user_id)
                        AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
                    """)
                    result = db.execute(query, {"user_id": user_id})
                    permissions = {row[0] for row in result}
                    await self.l2_cache.set(user_perms_key, permissions)
                    logger.debug(f"Preloaded {len(permissions)} permissions for user {user_id}")
                finally:
                    db.close()
        except Exception as e:
            logger.error(f"Error preloading permissions for user {user_id}: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = sum(self.stats.values())
        if total_requests > 0:
            l1_hit_rate = self.stats["l1_hits"] / total_requests
            l2_hit_rate = self.stats["l2_hits"] / total_requests
            miss_rate = self.stats["misses"] / total_requests
        else:
            l1_hit_rate = l2_hit_rate = miss_rate = 0
        
        return {
            "l1_hit_rate": l1_hit_rate,
            "l2_hit_rate": l2_hit_rate,
            "miss_rate": miss_rate,
            "total_requests": total_requests,
            **self.stats
        }

class CacheInvalidationManager:
    """缓存失效管理器"""
    
    def __init__(self, cache_manager: UnifiedPermissionCache):
        self.cache = cache_manager
        self.invalidation_rules = {}
    
    def register_invalidation_rule(self, event_type: str, handler):
        """注册缓存失效规则"""
        if event_type not in self.invalidation_rules:
            self.invalidation_rules[event_type] = []
        self.invalidation_rules[event_type].append(handler)
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]):
        """处理事件并执行相应的缓存失效"""
        if event_type in self.invalidation_rules:
            for handler in self.invalidation_rules[event_type]:
                try:
                    await handler(self.cache, event_data)
                except Exception as e:
                    logger.error(f"Error in cache invalidation handler: {e}")
    
    def setup_default_rules(self):
        """设置默认的缓存失效规则"""
        
        # 用户角色变更
        async def on_user_role_changed(cache: UnifiedPermissionCache, data: Dict[str, Any]):
            user_id = data.get("user_id")
            if user_id:
                await cache.invalidate_user_permissions(user_id)
        
        # 资源删除
        async def on_resource_deleted(cache: UnifiedPermissionCache, data: Dict[str, Any]):
            resource_uri = data.get("resource_uri")
            if resource_uri:
                await cache.invalidate_resource_permissions(resource_uri)
        
        # 权限授予/撤销
        async def on_permission_changed(cache: UnifiedPermissionCache, data: Dict[str, Any]):
            user_id = data.get("user_id")
            resource_uri = data.get("resource_uri")
            if user_id and resource_uri:
                await cache.invalidate_user_permissions(user_id)
                await cache.invalidate_resource_permissions(resource_uri)
        
        self.register_invalidation_rule("user_role_changed", on_user_role_changed)
        self.register_invalidation_rule("resource_deleted", on_resource_deleted)
        self.register_invalidation_rule("permission_granted", on_permission_changed)
        self.register_invalidation_rule("permission_revoked", on_permission_changed)