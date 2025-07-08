"""
LightRAG存储适配器 - 集成统一数据库管理系统
为LightRAG提供高性能的Neo4j、Redis、PostgreSQL存储配置
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from src.database.manager import get_database_manager

logger = logging.getLogger(__name__)


class LightRAGStorageAdapter:
    """
    LightRAG存储适配器
    负责将统一数据库管理系统的适配器转换为LightRAG兼容的存储配置
    """
    
    def __init__(self):
        self.db_manager = get_database_manager()
        self._storage_cache = {}
        
    async def initialize(self):
        """初始化数据库管理器"""
        if not self.db_manager._initialized:
            await self.db_manager.initialize()
    
    async def get_neo4j_storage_config(self, kb_id: str = None) -> Dict[str, Any]:
        """
        获取Neo4j图存储配置
        
        Args:
            kb_id: 知识库ID，用于日志记录
            
        Returns:
            Dict: Neo4j存储配置
        """
        try:
            await self.initialize()
            neo4j_adapter = await self.db_manager.get_neo4j_adapter()
            
            if not neo4j_adapter:
                raise ValueError("Neo4j adapter not available")
            
            # 设置LightRAG需要的环境变量
            os.environ['NEO4J_URI'] = neo4j_adapter.uri
            os.environ['NEO4J_USERNAME'] = neo4j_adapter.username
            os.environ['NEO4J_PASSWORD'] = neo4j_adapter.password
            
            logger.info(f"Neo4j存储配置就绪 [kb_id={kb_id}]: {neo4j_adapter.uri}")
            
            return {
                'storage_type': 'Neo4JStorage',
                'uri': neo4j_adapter.uri,
                'username': neo4j_adapter.username,
                'password': neo4j_adapter.password,
                'database': neo4j_adapter.database_name,
                'adapter': neo4j_adapter
            }
            
        except Exception as e:
            logger.error(f"Failed to get Neo4j storage config [kb_id={kb_id}]: {e}")
            return self._get_fallback_graph_storage()
    
    async def get_redis_storage_config(self, kb_id: str = None) -> Dict[str, Any]:
        """
        获取Redis KV存储配置
        
        Args:
            kb_id: 知识库ID，用于日志记录
            
        Returns:
            Dict: Redis存储配置
        """
        try:
            await self.initialize()
            redis_adapter = await self.db_manager.get_redis_adapter()
            
            if not redis_adapter:
                raise ValueError("Redis adapter not available")
            
            # 构建Redis URI - 对密码进行URL编码
            from urllib.parse import quote
            if redis_adapter.password:
                encoded_password = quote(redis_adapter.password, safe='')
                redis_uri = f"redis://:{encoded_password}@{redis_adapter.host}:{redis_adapter.port}/{redis_adapter.db}"
            else:
                redis_uri = f"redis://{redis_adapter.host}:{redis_adapter.port}/{redis_adapter.db}"
            
            # 设置LightRAG需要的环境变量
            os.environ['REDIS_URI'] = redis_uri
            
            logger.info(f"Redis存储配置就绪 [kb_id={kb_id}]: {redis_adapter.host}:{redis_adapter.port}")
            
            return {
                'storage_type': 'RedisKVStorage',
                'uri': redis_uri,
                'host': redis_adapter.host,
                'port': redis_adapter.port,
                'password': redis_adapter.password,
                'db': redis_adapter.db,
                'adapter': redis_adapter
            }
            
        except Exception as e:
            logger.error(f"Failed to get Redis storage config [kb_id={kb_id}]: {e}")
            return self._get_fallback_kv_storage()
    
    async def get_postgresql_storage_config(self, kb_id: str = None) -> Dict[str, Any]:
        """
        获取PostgreSQL文档状态存储配置
        
        Args:
            kb_id: 知识库ID，用于日志记录
            
        Returns:
            Dict: PostgreSQL存储配置
        """
        try:
            await self.initialize()
            # 使用lightrag_db专用数据库
            pg_adapter = await self.db_manager.get_postgresql_adapter('lightrag_db')
            
            if not pg_adapter:
                raise ValueError("PostgreSQL adapter not available")
            
            # 设置LightRAG需要的环境变量
            config = self.db_manager.get_database_config('lightrag_db')
            os.environ['POSTGRES_USER'] = config['username']
            os.environ['POSTGRES_PASSWORD'] = config['password']
            os.environ['POSTGRES_DATABASE'] = config['database']
            os.environ['POSTGRES_HOST'] = config['host']
            os.environ['POSTGRES_PORT'] = str(config['port'])
            
            logger.info(f"PostgreSQL存储配置就绪 [kb_id={kb_id}]: {config['host']}:{config['port']}/{config['database']}")
            
            return {
                'storage_type': 'PGDocStatusStorage',
                'host': config['host'],
                'port': config['port'],
                'database': config['database'],
                'username': config['username'],
                'password': config['password'],
                'adapter': pg_adapter
            }
            
        except Exception as e:
            logger.error(f"Failed to get PostgreSQL storage config [kb_id={kb_id}]: {e}")
            return self._get_fallback_doc_status_storage()
    
    async def get_complete_storage_config(self, kb_id: str = None) -> Dict[str, Any]:
        """
        获取完整的LightRAG存储配置
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            Dict: 完整存储配置
        """
        logger.info(f"获取LightRAG完整存储配置 [kb_id={kb_id}]")
        
        # 并行获取所有存储配置
        neo4j_config, redis_config, pg_config, milvus_config = await asyncio.gather(
            self.get_neo4j_storage_config(kb_id),
            self.get_redis_storage_config(kb_id),
            self.get_postgresql_storage_config(kb_id),
            self.get_milvus_config(kb_id),
            return_exceptions=True
        )
        
        # 处理异常
        for config_name, config in [
            ('neo4j', neo4j_config),
            ('redis', redis_config), 
            ('postgresql', pg_config),
            ('milvus', milvus_config)
        ]:
            if isinstance(config, Exception):
                logger.error(f"Failed to get {config_name} config [kb_id={kb_id}]: {config}")
        
        # 检查关键存储配置是否成功获取
        if isinstance(milvus_config, Exception):
            raise ValueError(f"Milvus配置获取失败: {milvus_config}")
        
        return {
            'graph_storage': neo4j_config['storage_type'] if isinstance(neo4j_config, dict) else 'JsonKVStorage',
            'kv_storage': redis_config['storage_type'] if isinstance(redis_config, dict) else 'JsonKVStorage', 
            'doc_status_storage': pg_config['storage_type'] if isinstance(pg_config, dict) else 'JsonKVStorage',
            'vector_storage': milvus_config['storage_type'] if isinstance(milvus_config, dict) else 'SimpleVectorStorage',
            'configs': {
                'neo4j': neo4j_config if isinstance(neo4j_config, dict) else None,
                'redis': redis_config if isinstance(redis_config, dict) else None,
                'postgresql': pg_config if isinstance(pg_config, dict) else None,
                'milvus': milvus_config if isinstance(milvus_config, dict) else None
            }
        }
    
    async def setup_lightrag_environment(self, kb_id: str = None):
        """
        设置LightRAG运行环境（仅设置环境变量）
        
        Args:
            kb_id: 知识库ID
        """
        # 获取各存储配置并设置环境变量
        neo4j_config, redis_config, pg_config, milvus_config = await asyncio.gather(
            self.get_neo4j_storage_config(kb_id),
            self.get_redis_storage_config(kb_id), 
            self.get_postgresql_storage_config(kb_id),
            self.get_milvus_config(kb_id),
            return_exceptions=True
        )
        
        # 检查关键存储配置是否成功获取
        if isinstance(milvus_config, Exception):
            raise ValueError(f"Milvus配置获取失败: {milvus_config}")
        
        # 确保所有必要的环境变量都已设置
        env_vars = [
            'NEO4J_URI', 'NEO4J_USERNAME', 'NEO4J_PASSWORD',
            'REDIS_URI',
            'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DATABASE',
            'POSTGRES_HOST', 'POSTGRES_PORT',
            'MILVUS_URI', 'MILVUS_USER', 'MILVUS_PASSWORD'
        ]
        
        missing_vars = [var for var in env_vars if not os.getenv(var)]
        if missing_vars:
            logger.warning(f"Missing environment variables for LightRAG [kb_id={kb_id}]: {missing_vars}")
        
        logger.info(f"LightRAG环境变量设置完成 [kb_id={kb_id}]")
    
    async def get_storage_type_config(self, kb_id: str = None) -> Dict[str, Any]:
        """
        获取存储类型配置（不设置环境变量）
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            Dict: 存储类型配置
        """
        logger.info(f"获取LightRAG存储类型配置 [kb_id={kb_id}]")
        
        # 并行获取所有存储配置
        neo4j_config, redis_config, pg_config, milvus_config = await asyncio.gather(
            self.get_neo4j_storage_config(kb_id),
            self.get_redis_storage_config(kb_id),
            self.get_postgresql_storage_config(kb_id),
            self.get_milvus_config(kb_id),
            return_exceptions=True
        )
        
        # 处理异常
        for config_name, config in [
            ('neo4j', neo4j_config),
            ('redis', redis_config), 
            ('postgresql', pg_config),
            ('milvus', milvus_config)
        ]:
            if isinstance(config, Exception):
                logger.error(f"Failed to get {config_name} config [kb_id={kb_id}]: {config}")
        
        # 检查关键存储配置是否成功获取
        if isinstance(milvus_config, Exception):
            raise ValueError(f"Milvus配置获取失败: {milvus_config}")
        
        config = {
            'graph_storage': neo4j_config['storage_type'] if isinstance(neo4j_config, dict) else 'JsonKVStorage',
            'kv_storage': redis_config['storage_type'] if isinstance(redis_config, dict) else 'JsonKVStorage', 
            'doc_status_storage': pg_config['storage_type'] if isinstance(pg_config, dict) else 'JsonKVStorage',
            'vector_storage': milvus_config['storage_type'] if isinstance(milvus_config, dict) else 'SimpleVectorStorage',
            'configs': {
                'neo4j': neo4j_config if isinstance(neo4j_config, dict) else None,
                'redis': redis_config if isinstance(redis_config, dict) else None,
                'postgresql': pg_config if isinstance(pg_config, dict) else None,
                'milvus': milvus_config if isinstance(milvus_config, dict) else None
            }
        }
        
        logger.info(f"存储类型配置获取完成 [kb_id={kb_id}]: graph={config['graph_storage']}, kv={config['kv_storage']}, doc_status={config['doc_status_storage']}, vector={config['vector_storage']}")
        return config
    
    def _get_fallback_graph_storage(self) -> Dict[str, Any]:
        """获取图存储降级配置"""
        logger.warning("使用图存储降级配置: JsonKVStorage")
        return {
            'storage_type': 'JsonKVStorage',
            'adapter': None
        }
    
    def _get_fallback_kv_storage(self) -> Dict[str, Any]:
        """获取KV存储降级配置"""
        logger.warning("使用KV存储降级配置: JsonKVStorage")
        return {
            'storage_type': 'JsonKVStorage',
            'adapter': None
        }
    
    def _get_fallback_doc_status_storage(self) -> Dict[str, Any]:
        """获取文档状态存储降级配置"""
        logger.warning("使用文档状态存储降级配置: JsonKVStorage")
        return {
            'storage_type': 'JsonKVStorage',
            'adapter': None
        }
    
    async def get_milvus_config(self, kb_id: str = None) -> Dict[str, Any]:
        """
        获取Milvus向量存储配置
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            Dict: Milvus配置
        """
        try:
            await self.initialize()
            milvus_adapter = await self.db_manager.get_milvus_adapter()
            
            if not milvus_adapter:
                raise ValueError("Milvus adapter not available")
            
            # 设置LightRAG需要的环境变量
            os.environ['MILVUS_URI'] = milvus_adapter.uri
            os.environ['MILVUS_USER'] = milvus_adapter.user
            os.environ['MILVUS_PASSWORD'] = milvus_adapter.password
            if milvus_adapter.db_name_milvus:
                os.environ['MILVUS_DB_NAME'] = milvus_adapter.db_name_milvus
            
            logger.info(f"Milvus存储配置就绪 [kb_id={kb_id}]: {milvus_adapter.uri}")
            
            return {
                'storage_type': 'MilvusVectorDBStorage',
                'uri': milvus_adapter.uri,
                'user': milvus_adapter.user,
                'password': milvus_adapter.password,
                'db_name': milvus_adapter.db_name_milvus,
                'adapter': milvus_adapter
            }
            
        except Exception as e:
            logger.error(f"Failed to get Milvus config [kb_id={kb_id}]: {e}")
            raise ValueError(f"无法获取Milvus配置: {e}")
    
    async def create_database_specific_config(self, kb_id: str, custom_configs: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        为特定知识库创建定制化存储配置
        
        Args:
            kb_id: 知识库ID
            custom_configs: 自定义配置覆盖
            
        Returns:
            Dict: 定制化存储配置
        """
        base_config = await self.get_complete_storage_config(kb_id)
        
        if custom_configs:
            # 合并自定义配置
            for storage_type, custom_config in custom_configs.items():
                if storage_type in base_config['configs']:
                    base_config['configs'][storage_type].update(custom_config)
        
        # 为这个知识库设置特定的环境变量前缀
        kb_prefix = f"LIGHTRAG_{kb_id.upper()}_"
        
        # 如果需要，可以为每个知识库设置独立的存储空间
        if base_config['configs']['neo4j']:
            base_config['configs']['neo4j']['database'] = f"lightrag_{kb_id}"
        
        if base_config['configs']['redis']:
            base_config['configs']['redis']['key_prefix'] = f"lightrag:{kb_id}:"
        
        logger.info(f"知识库特定存储配置创建完成 [kb_id={kb_id}]")
        return base_config
    
    @asynccontextmanager
    async def get_storage_adapters(self, kb_id: str = None):
        """
        获取存储适配器的异步上下文管理器
        
        Args:
            kb_id: 知识库ID
            
        Yields:
            tuple: (neo4j_adapter, redis_adapter, pg_adapter, milvus_adapter)
        """
        adapters = []
        try:
            await self.initialize()
            
            # 获取所有适配器
            neo4j_adapter = await self.db_manager.get_neo4j_adapter()
            redis_adapter = await self.db_manager.get_redis_adapter()
            pg_adapter = await self.db_manager.get_postgresql_adapter('lightrag_db')
            milvus_adapter = await self.db_manager.get_milvus_adapter()
            
            adapters = [neo4j_adapter, redis_adapter, pg_adapter, milvus_adapter]
            
            yield (neo4j_adapter, redis_adapter, pg_adapter, milvus_adapter)
            
        except Exception as e:
            logger.error(f"Error in storage adapters context [kb_id={kb_id}]: {e}")
            raise
        finally:
            # 清理工作（如果需要）
            pass


# 全局单例实例
_storage_adapter = None

def get_lightrag_storage_adapter() -> LightRAGStorageAdapter:
    """获取LightRAG存储适配器单例"""
    global _storage_adapter
    if _storage_adapter is None:
        _storage_adapter = LightRAGStorageAdapter()
    return _storage_adapter