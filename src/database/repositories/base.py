"""
基础仓储抽象类
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Generic, TypeVar, Union

from ..connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """基础仓储抽象类"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        """
        初始化仓储
        
        Args:
            connection_manager: 数据库连接管理器
        """
        self.connection_manager = connection_manager
        self._cache_enabled = True
        self._cache_ttl = 3600  # 1小时默认缓存时间
    
    @abstractmethod
    async def create(self, entity: T) -> T:
        """
        创建实体
        
        Args:
            entity: 实体对象
            
        Returns:
            创建后的实体对象
        """
        pass
    
    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """
        根据ID获取实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            实体对象或None
        """
        pass
    
    @abstractmethod
    async def update(self, entity: T) -> T:
        """
        更新实体
        
        Args:
            entity: 实体对象
            
        Returns:
            更新后的实体对象
        """
        pass
    
    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """
        删除实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            删除成功返回True
        """
        pass
    
    @abstractmethod
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """
        查找所有实体
        
        Args:
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            实体列表
        """
        pass
    
    async def find_by_criteria(self, criteria: Dict[str, Any], 
                              limit: int = 100, offset: int = 0) -> List[T]:
        """
        根据条件查找实体
        
        Args:
            criteria: 查询条件
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            实体列表
        """
        # 默认实现，子类可以重写
        return await self.find_all(limit, offset)
    
    async def exists(self, entity_id: str) -> bool:
        """
        检查实体是否存在
        
        Args:
            entity_id: 实体ID
            
        Returns:
            存在返回True
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None
    
    async def count(self, criteria: Dict[str, Any] = None) -> int:
        """
        统计实体数量
        
        Args:
            criteria: 查询条件
            
        Returns:
            实体数量
        """
        # 默认实现，子类应该重写以提高性能
        entities = await self.find_by_criteria(criteria or {}, limit=1000000)
        return len(entities)
    
    # 缓存相关方法
    
    def _get_cache_key(self, key: str) -> str:
        """生成缓存键"""
        return f"{self.__class__.__name__}:{key}"
    
    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if not self._cache_enabled:
            return None
        
        try:
            redis_adapter = await self.connection_manager.get_adapter('redis')
            if redis_adapter and redis_adapter.is_available:
                cache_key = self._get_cache_key(key)
                return await redis_adapter.get(cache_key)
        except Exception as e:
            logger.warning(f"Cache get failed for key {key}: {e}")
        
        return None
    
    async def _set_to_cache(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存数据"""
        if not self._cache_enabled:
            return False
        
        try:
            redis_adapter = await self.connection_manager.get_adapter('redis')
            if redis_adapter and redis_adapter.is_available:
                cache_key = self._get_cache_key(key)
                cache_ttl = ttl or self._cache_ttl
                return await redis_adapter.set(cache_key, value, cache_ttl)
        except Exception as e:
            logger.warning(f"Cache set failed for key {key}: {e}")
        
        return False
    
    async def _delete_from_cache(self, key: str) -> bool:
        """从缓存删除数据"""
        if not self._cache_enabled:
            return False
        
        try:
            redis_adapter = await self.connection_manager.get_adapter('redis')
            if redis_adapter and redis_adapter.is_available:
                cache_key = self._get_cache_key(key)
                return await redis_adapter.delete(cache_key)
        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")
        
        return False
    
    async def _invalidate_cache_pattern(self, pattern: str) -> int:
        """根据模式清除缓存"""
        if not self._cache_enabled:
            return 0
        
        try:
            redis_adapter = await self.connection_manager.get_adapter('redis')
            if redis_adapter and redis_adapter.is_available:
                cache_pattern = self._get_cache_key(pattern)
                return await redis_adapter.delete_pattern(cache_pattern)
        except Exception as e:
            logger.warning(f"Cache pattern invalidation failed for pattern {pattern}: {e}")
        
        return 0
    
    def enable_cache(self, ttl: int = 3600):
        """启用缓存"""
        self._cache_enabled = True
        self._cache_ttl = ttl
    
    def disable_cache(self):
        """禁用缓存"""
        self._cache_enabled = False
    
    # 事务支持
    
    async def execute_in_transaction(self, operations: List[Dict[str, Any]], 
                                   database: str = 'server_db') -> bool:
        """
        在事务中执行操作
        
        Args:
            operations: 操作列表
            database: 数据库名称
            
        Returns:
            事务执行成功返回True
        """
        try:
            adapter = await self.connection_manager.get_adapter(database)
            if adapter and hasattr(adapter, 'execute_transaction'):
                return await adapter.execute_transaction(operations)
            else:
                logger.warning(f"Transaction not supported for database {database}")
                return False
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            return False
    
    # 批量操作支持
    
    async def batch_create(self, entities: List[T]) -> List[T]:
        """
        批量创建实体
        
        Args:
            entities: 实体列表
            
        Returns:
            创建后的实体列表
        """
        results = []
        for entity in entities:
            try:
                created_entity = await self.create(entity)
                results.append(created_entity)
            except Exception as e:
                logger.error(f"Batch create failed for entity: {e}")
                results.append(None)
        
        return [entity for entity in results if entity is not None]
    
    async def batch_update(self, entities: List[T]) -> List[T]:
        """
        批量更新实体
        
        Args:
            entities: 实体列表
            
        Returns:
            更新后的实体列表
        """
        results = []
        for entity in entities:
            try:
                updated_entity = await self.update(entity)
                results.append(updated_entity)
            except Exception as e:
                logger.error(f"Batch update failed for entity: {e}")
                results.append(None)
        
        return [entity for entity in results if entity is not None]
    
    async def batch_delete(self, entity_ids: List[str]) -> int:
        """
        批量删除实体
        
        Args:
            entity_ids: 实体ID列表
            
        Returns:
            成功删除的数量
        """
        deleted_count = 0
        for entity_id in entity_ids:
            try:
                if await self.delete(entity_id):
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Batch delete failed for entity {entity_id}: {e}")
        
        return deleted_count
    
    # 健康检查
    
    async def health_check(self) -> Dict[str, Any]:
        """
        仓储健康检查
        
        Returns:
            健康检查结果
        """
        try:
            # 尝试执行一个简单的查询
            count = await self.count()
            
            return {
                'status': 'healthy',
                'repository': self.__class__.__name__,
                'entity_count': count,
                'cache_enabled': self._cache_enabled,
                'timestamp': asyncio.get_event_loop().time()
            }
        except Exception as e:
            return {
                'status': 'error',
                'repository': self.__class__.__name__,
                'error': str(e),
                'timestamp': asyncio.get_event_loop().time()
            }


class PostgreSQLRepository(BaseRepository[T]):
    """PostgreSQL仓储基类"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager, 
                 database_name: str = 'server_db'):
        """
        初始化PostgreSQL仓储
        
        Args:
            connection_manager: 数据库连接管理器
            database_name: 数据库名称
        """
        super().__init__(connection_manager)
        self.database_name = database_name
    
    async def get_session(self):
        """获取数据库会话上下文管理器"""
        adapter = await self.connection_manager.ensure_connection(self.database_name)
        return adapter.get_session_context()
    
    async def execute_query(self, query: str, params: Dict[str, Any] = None) -> Any:
        """执行SQL查询"""
        adapter = await self.connection_manager.ensure_connection(self.database_name)
        return await adapter.execute_query(query, params)


class Neo4jRepository(BaseRepository[T]):
    """Neo4j仓储基类"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager, 
                 database_name: str = 'neo4j'):
        """
        初始化Neo4j仓储
        
        Args:
            connection_manager: 数据库连接管理器
            database_name: 数据库名称
        """
        super().__init__(connection_manager)
        self.database_name = database_name
    
    async def get_session(self):
        """获取数据库会话上下文管理器"""
        adapter = await self.connection_manager.ensure_connection(self.database_name)
        return adapter.get_session()
    
    async def execute_cypher(self, query: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """执行Cypher查询"""
        adapter = await self.connection_manager.ensure_connection(self.database_name)
        return await adapter.execute_cypher(query, parameters)


class FileRepository(BaseRepository[T]):
    """文件存储仓储基类"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager, 
                 storage_name: str = 'minio'):
        """
        初始化文件仓储
        
        Args:
            connection_manager: 数据库连接管理器
            storage_name: 存储名称
        """
        super().__init__(connection_manager)
        self.storage_name = storage_name
    
    async def get_storage(self):
        """获取存储适配器"""
        return await self.connection_manager.ensure_connection(self.storage_name)