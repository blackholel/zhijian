"""
Redis缓存数据库适配器
"""

import asyncio
import json
import logging
import pickle
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

try:
    import redis.asyncio as aioredis
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from ..base import CacheAdapter, ConnectionStatus, ConnectionError

logger = logging.getLogger(__name__)


class RedisAdapter(CacheAdapter):
    """Redis缓存数据库适配器"""
    
    def __init__(self, config: Dict[str, Any], db_name: str = None):
        """
        初始化Redis适配器
        
        Args:
            config: 数据库配置
            db_name: 数据库名称
        """
        if not REDIS_AVAILABLE:
            raise ConnectionError("Redis not available. Please install: pip install redis")
        
        super().__init__(config, db_name)
        
        self.redis_client = None
        self.connection_pool = None
        
        # 连接配置
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 6379)
        self.password = config.get('password', '')
        self.db = config.get('db', 0)
        self.max_connections = config.get('max_connections', 20)
        self.decode_responses = config.get('decode_responses', True)
        self.retry_on_timeout = config.get('retry_on_timeout', True)
        self.connection_timeout = config.get('connection_timeout', 30)
        self.socket_timeout = config.get('socket_timeout', 30)
        
        # 缓存配置
        self.default_ttl = config.get('default_ttl', 3600)
        self.key_prefix = config.get('key_prefix', 'app:')
        
        # Fallback配置
        self._use_fallback = False
        self._fallback_cache = {}
        self._fallback_expiry = {}
        
        logger.debug(f"Redis adapter initialized for {self.db_name}")
    
    def _build_redis_url(self) -> str:
        """构建Redis连接URL"""
        from urllib.parse import quote
        if self.password:
            # URL编码密码中的特殊字符
            encoded_password = quote(self.password, safe='')
            return f"redis://:{encoded_password}@{self.host}:{self.port}/{self.db}"
        else:
            return f"redis://{self.host}:{self.port}/{self.db}"
    
    async def connect(self) -> bool:
        """建立数据库连接"""
        if self.status == ConnectionStatus.CONNECTED:
            return True
        
        self.status = ConnectionStatus.CONNECTING
        
        try:
            redis_url = self._build_redis_url()
            
            # 创建连接池
            self.connection_pool = aioredis.ConnectionPool.from_url(
                redis_url,
                max_connections=self.max_connections,
                decode_responses=self.decode_responses,
                retry_on_timeout=self.retry_on_timeout
            )
            
            # 创建客户端
            self.redis_client = aioredis.Redis(
                connection_pool=self.connection_pool,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.connection_timeout
            )
            
            # 测试连接
            await self._test_connection()
            
            self._client = self.redis_client
            self.status = ConnectionStatus.CONNECTED
            self._use_fallback = False
            
            logger.info(f"Redis connection established for {self.db_name} at {self.host}:{self.port}")
            return True
            
        except Exception as e:
            self.status = ConnectionStatus.ERROR
            logger.warning(f"Failed to connect to Redis {self.db_name}: {e}, using fallback cache")
            self._init_fallback()
            return True  # 总是返回True，因为有fallback
    
    def _init_fallback(self):
        """初始化内存fallback缓存"""
        self._use_fallback = True
        self._fallback_cache = {}
        self._fallback_expiry = {}
        logger.info(f"Using memory fallback cache for {self.db_name}")
    
    async def _test_connection(self):
        """测试数据库连接"""
        await self.redis_client.ping()
    
    async def disconnect(self) -> bool:
        """断开数据库连接"""
        try:
            if self.redis_client:
                await self.redis_client.aclose()
                self.redis_client = None
            
            if self.connection_pool:
                await self.connection_pool.aclose()
                self.connection_pool = None
            
            self._client = None
            self.status = ConnectionStatus.DISCONNECTED
            
            logger.info(f"Redis connection closed for {self.db_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Redis {self.db_name}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if self._use_fallback:
                return {
                    'status': 'fallback',
                    'database_name': self.db_name,
                    'cache_type': 'memory',
                    'fallback_entries': len(self._fallback_cache),
                    'timestamp': datetime.now().isoformat()
                }
            
            if not self.is_connected:
                return {
                    'status': 'disconnected',
                    'database_name': self.db_name,
                    'timestamp': datetime.now().isoformat()
                }
            
            # 基本连接测试
            await self.redis_client.ping()
            
            # 获取Redis信息
            info = await self.redis_client.info()
            memory_info = await self.redis_client.info('memory')
            keyspace_info = await self.redis_client.info('keyspace')
            
            return {
                'status': 'healthy',
                'database_name': self.db_name,
                'redis_version': info.get('redis_version', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': memory_info.get('used_memory_human', 'unknown'),
                'total_keys': self._count_db_keys(keyspace_info),
                'db_number': self.db,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'database_name': self.db_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _count_db_keys(self, keyspace_info: Dict) -> int:
        """计算当前数据库的键数量"""
        db_key = f'db{self.db}'
        if db_key in keyspace_info:
            db_stats = keyspace_info[db_key]
            
            # 处理不同的数据格式
            if isinstance(db_stats, dict):
                # 如果是字典格式，直接取keys值
                return db_stats.get('keys', 0)
            elif isinstance(db_stats, str):
                # 如果是字符串格式，解析格式如: "keys=123,expires=45,avg_ttl=789"
                try:
                    keys_part = db_stats.split(',')[0]
                    return int(keys_part.split('=')[1])
                except (IndexError, ValueError):
                    return 0
            else:
                return 0
        return 0
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            'database_name': self.db_name,
            'type': 'redis',
            'host': self.host,
            'port': self.port,
            'db': self.db,
            'status': self.status.value,
            'fallback_mode': self._use_fallback,
            'max_connections': self.max_connections,
            'decode_responses': self.decode_responses
        }
    
    def _cleanup_fallback(self):
        """清理过期的fallback缓存"""
        if not self._use_fallback:
            return
        
        now = datetime.now().timestamp()
        expired_keys = [
            k for k, exp_time in self._fallback_expiry.items()
            if exp_time < now
        ]
        
        for key in expired_keys:
            self._fallback_cache.pop(key, None)
            self._fallback_expiry.pop(key, None)
    
    def _add_key_prefix(self, key: str) -> str:
        """添加键前缀"""
        if self.key_prefix and not key.startswith(self.key_prefix):
            return f"{self.key_prefix}{key}"
        return key
    
    def _serialize_value(self, value: Any) -> Union[str, bytes]:
        """序列化值"""
        if isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, (dict, list, tuple)):
            return json.dumps(value, default=str)
        else:
            # 对于复杂对象使用pickle
            return pickle.dumps(value)
    
    def _deserialize_value(self, value: Union[str, bytes]) -> Any:
        """反序列化值"""
        if isinstance(value, bytes):
            try:
                return pickle.loads(value)
            except Exception as e:
                # 处理模块路径变更导致的pickle反序列化失败
                if 'server.auth' in str(e):
                    logger.warning(f"Detected outdated pickle data with server.auth reference, skipping: {e}")
                    return None
                try:
                    return json.loads(value.decode())
                except:
                    return value.decode()
        elif isinstance(value, str):
            try:
                return json.loads(value)
            except:
                return value
        return value
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        full_key = self._add_key_prefix(key)
        
        try:
            if self._use_fallback:
                self._cleanup_fallback()
                value = self._fallback_cache.get(full_key)
                return value
            
            value = await self.redis_client.get(full_key)
            if value is not None:
                return self._deserialize_value(value)
            return None
            
        except Exception as e:
            logger.error(f"Get operation failed for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存值"""
        full_key = self._add_key_prefix(key)
        
        try:
            if ttl is None:
                ttl = self.default_ttl
            
            if self._use_fallback:
                self._fallback_cache[full_key] = value
                self._fallback_expiry[full_key] = datetime.now().timestamp() + ttl
                return True
            
            serialized_value = self._serialize_value(value)
            
            if isinstance(serialized_value, bytes):
                # 对于二进制数据
                result = await self.redis_client.setex(full_key, ttl, serialized_value)
            else:
                # 对于文本数据
                result = await self.redis_client.setex(full_key, ttl, serialized_value)
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"Set operation failed for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存值"""
        full_key = self._add_key_prefix(key)
        
        try:
            if self._use_fallback:
                self._fallback_cache.pop(full_key, None)
                self._fallback_expiry.pop(full_key, None)
                return True
            
            result = await self.redis_client.delete(full_key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Delete operation failed for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        full_key = self._add_key_prefix(key)
        
        try:
            if self._use_fallback:
                self._cleanup_fallback()
                return full_key in self._fallback_cache
            
            result = await self.redis_client.exists(full_key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Exists check failed for key {key}: {e}")
            return False
    
    async def expire(self, key: str, ttl: int) -> bool:
        """设置键的过期时间"""
        full_key = self._add_key_prefix(key)
        
        try:
            if self._use_fallback:
                if full_key in self._fallback_cache:
                    self._fallback_expiry[full_key] = datetime.now().timestamp() + ttl
                    return True
                return False
            
            result = await self.redis_client.expire(full_key, ttl)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Expire operation failed for key {key}: {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """获取键的剩余生存时间"""
        full_key = self._add_key_prefix(key)
        
        try:
            if self._use_fallback:
                if full_key in self._fallback_expiry:
                    remaining = self._fallback_expiry[full_key] - datetime.now().timestamp()
                    return max(0, int(remaining))
                return -1
            
            result = await self.redis_client.ttl(full_key)
            return result
            
        except Exception as e:
            logger.error(f"TTL operation failed for key {key}: {e}")
            return -1
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的键列表"""
        pattern_with_prefix = self._add_key_prefix(pattern)
        
        try:
            if self._use_fallback:
                import fnmatch
                self._cleanup_fallback()
                matching_keys = [
                    k.replace(self.key_prefix, '', 1) if self.key_prefix else k
                    for k in self._fallback_cache.keys()
                    if fnmatch.fnmatch(k, pattern_with_prefix)
                ]
                return matching_keys
            
            keys = await self.redis_client.keys(pattern_with_prefix)
            # 移除前缀
            if self.key_prefix:
                keys = [k.replace(self.key_prefix, '', 1) for k in keys if k.startswith(self.key_prefix)]
            return keys
            
        except Exception as e:
            logger.error(f"Keys operation failed for pattern {pattern}: {e}")
            return []
    
    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的键"""
        try:
            keys_to_delete = await self.keys(pattern)
            if not keys_to_delete:
                return 0
            
            if self._use_fallback:
                count = 0
                for key in keys_to_delete:
                    full_key = self._add_key_prefix(key)
                    if full_key in self._fallback_cache:
                        self._fallback_cache.pop(full_key, None)
                        self._fallback_expiry.pop(full_key, None)
                        count += 1
                return count
            
            # 添加前缀
            full_keys = [self._add_key_prefix(key) for key in keys_to_delete]
            deleted = await self.redis_client.delete(*full_keys)
            return deleted
            
        except Exception as e:
            logger.error(f"Delete pattern operation failed for pattern {pattern}: {e}")
            return 0
    
    async def clear(self) -> bool:
        """清空当前数据库"""
        try:
            if self._use_fallback:
                self._fallback_cache.clear()
                self._fallback_expiry.clear()
                return True
            
            await self.redis_client.flushdb()
            logger.info(f"Redis database {self.db} cleared")
            return True
            
        except Exception as e:
            logger.error(f"Clear operation failed: {e}")
            return False
    
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """递增键值"""
        full_key = self._add_key_prefix(key)
        
        try:
            if self._use_fallback:
                current = self._fallback_cache.get(full_key, 0)
                if isinstance(current, (int, float)):
                    new_value = current + amount
                    self._fallback_cache[full_key] = new_value
                    return new_value
                return None
            
            result = await self.redis_client.incrby(full_key, amount)
            return result
            
        except Exception as e:
            logger.error(f"Increment operation failed for key {key}: {e}")
            return None
    
    async def get_multiple(self, keys: List[str]) -> Dict[str, Any]:
        """批量获取键值"""
        if not keys:
            return {}
        
        try:
            if self._use_fallback:
                self._cleanup_fallback()
                result = {}
                for key in keys:
                    full_key = self._add_key_prefix(key)
                    if full_key in self._fallback_cache:
                        result[key] = self._fallback_cache[full_key]
                return result
            
            full_keys = [self._add_key_prefix(key) for key in keys]
            values = await self.redis_client.mget(full_keys)
            
            result = {}
            for i, key in enumerate(keys):
                if values[i] is not None:
                    result[key] = self._deserialize_value(values[i])
            
            return result
            
        except Exception as e:
            logger.error(f"Get multiple operation failed: {e}")
            return {}
    
    async def set_multiple(self, data: Dict[str, Any], ttl: int = None) -> bool:
        """批量设置键值"""
        if not data:
            return True
        
        try:
            if ttl is None:
                ttl = self.default_ttl
            
            if self._use_fallback:
                exp_time = datetime.now().timestamp() + ttl
                for key, value in data.items():
                    full_key = self._add_key_prefix(key)
                    self._fallback_cache[full_key] = value
                    self._fallback_expiry[full_key] = exp_time
                return True
            
            # 使用pipeline批量操作
            async with self.redis_client.pipeline() as pipe:
                for key, value in data.items():
                    full_key = self._add_key_prefix(key)
                    serialized_value = self._serialize_value(value)
                    pipe.setex(full_key, ttl, serialized_value)
                await pipe.execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Set multiple operation failed: {e}")
            return False
    
    @asynccontextmanager
    async def pipeline(self):
        """获取Redis pipeline上下文管理器"""
        if self._use_fallback:
            # Fallback模式下不支持pipeline
            yield self
            return
        
        await self.ensure_connected()
        async with self.redis_client.pipeline() as pipe:
            yield pipe
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        base_metrics = super().get_metrics()
        
        if self._use_fallback:
            base_metrics.update({
                'cache_type': 'memory_fallback',
                'fallback_entries': len(self._fallback_cache),
                'expired_entries': len([
                    k for k, exp_time in self._fallback_expiry.items()
                    if exp_time < datetime.now().timestamp()
                ])
            })
        else:
            base_metrics.update({
                'cache_type': 'redis',
                'db_number': self.db,
                'max_connections': self.max_connections
            })
        
        return base_metrics
    
    # Pub/Sub功能增强
    
    async def publish(self, channel: str, message: str) -> bool:
        """发布消息到Redis频道"""
        try:
            if self._use_fallback:
                logger.warning("Fallback模式下不支持pub/sub")
                return False
            
            result = await self.redis_client.publish(channel, message)
            logger.debug(f"消息发布成功: {channel}, 订阅者数量: {result}")
            return True
            
        except Exception as e:
            logger.error(f"消息发布失败 {channel}: {e}")
            return False
    
    async def subscribe(self, channel: str, timeout: int = None):
        """订阅Redis频道，返回异步生成器"""
        try:
            if self._use_fallback:
                logger.warning("Fallback模式下不支持pub/sub")
                return
            
            # 创建新的连接用于订阅
            subscribe_client = aioredis.from_url(
                self._build_redis_url(),
                decode_responses=self.decode_responses,
                retry_on_timeout=self.retry_on_timeout,
                socket_connect_timeout=self.connection_timeout,
                socket_timeout=self.socket_timeout
            )
            
            pubsub = subscribe_client.pubsub()
            await pubsub.subscribe(channel)
            
            logger.info(f"开始订阅频道: {channel}")
            
            try:
                async for message in pubsub.listen():
                    if message['type'] == 'message':
                        yield message['data']
                    elif message['type'] == 'subscribe':
                        logger.info(f"订阅成功: {channel}")
                        
            except asyncio.CancelledError:
                logger.info(f"订阅被取消: {channel}")
            except Exception as e:
                logger.error(f"订阅过程中出错: {e}")
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
                await subscribe_client.close()
                
        except Exception as e:
            logger.error(f"订阅失败 {channel}: {e}")
    
    async def subscribe_pattern(self, pattern: str):
        """订阅Redis频道模式"""
        try:
            if self._use_fallback:
                logger.warning("Fallback模式下不支持pub/sub")
                return
            
            # 创建新的连接用于订阅
            subscribe_client = aioredis.from_url(
                self._build_redis_url(),
                decode_responses=self.decode_responses,
                retry_on_timeout=self.retry_on_timeout,
                socket_connect_timeout=self.connection_timeout,
                socket_timeout=self.socket_timeout
            )
            
            pubsub = subscribe_client.pubsub()
            await pubsub.psubscribe(pattern)
            
            logger.info(f"开始订阅模式: {pattern}")
            
            try:
                async for message in pubsub.listen():
                    if message['type'] == 'pmessage':
                        yield {
                            'channel': message['channel'],
                            'pattern': message['pattern'],
                            'data': message['data']
                        }
                    elif message['type'] == 'psubscribe':
                        logger.info(f"模式订阅成功: {pattern}")
                        
            except asyncio.CancelledError:
                logger.info(f"模式订阅被取消: {pattern}")
            except Exception as e:
                logger.error(f"模式订阅过程中出错: {e}")
            finally:
                await pubsub.punsubscribe(pattern)
                await pubsub.close()
                await subscribe_client.close()
                
        except Exception as e:
            logger.error(f"模式订阅失败 {pattern}: {e}")
    
    async def get_subscribers_count(self, channel: str) -> int:
        """获取频道订阅者数量"""
        try:
            if self._use_fallback:
                return 0
            
            result = await self.redis_client.pubsub_numsub(channel)
            return result.get(channel, 0)
            
        except Exception as e:
            logger.error(f"获取订阅者数量失败 {channel}: {e}")
            return 0