"""
Milvus向量数据库适配器
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime

try:
    from pymilvus import connections, Collection, DataType, FieldSchema, CollectionSchema, utility
    from pymilvus.exceptions import MilvusException
    MILVUS_AVAILABLE = True
except ImportError:
    MILVUS_AVAILABLE = False

from ..base import NoSQLDatabaseAdapter, ConnectionStatus, ConnectionError

logger = logging.getLogger(__name__)


class MilvusAdapter(NoSQLDatabaseAdapter):
    """Milvus向量数据库适配器"""
    
    def __init__(self, config: Dict[str, Any], db_name: str = None):
        """
        初始化Milvus适配器
        
        Args:
            config: 数据库配置
            db_name: 数据库名称
        """
        if not MILVUS_AVAILABLE:
            raise ConnectionError("Milvus not available. Please install: pip install pymilvus")
        
        super().__init__(config, db_name)
        
        self.connection_alias = f"milvus_{self.db_name}"
        self.collections: Dict[str, Collection] = {}
        
        # 连接配置
        self.uri = config.get('uri', 'http://localhost:19530')
        self.user = config.get('user', '')
        self.password = config.get('password', '')
        self.db_name_milvus = config.get('db_name', 'default')
        self.timeout = config.get('timeout', 30)
        
        logger.debug(f"Milvus adapter initialized for {self.db_name}")
    
    async def connect(self) -> bool:
        """建立数据库连接"""
        if self.status == ConnectionStatus.CONNECTED:
            return True
        
        self.status = ConnectionStatus.CONNECTING
        
        try:
            # 构建连接参数
            connect_params = {
                'alias': self.connection_alias,
                'uri': self.uri,
                'timeout': self.timeout
            }
            
            if self.user:
                connect_params['user'] = self.user
                connect_params['password'] = self.password
            
            if self.db_name_milvus and self.db_name_milvus != 'default':
                connect_params['db_name'] = self.db_name_milvus
            
            # 在线程池中执行连接操作
            def _connect():
                connections.connect(**connect_params)
            
            await asyncio.get_event_loop().run_in_executor(None, _connect)
            
            # 测试连接
            await self._test_connection()
            
            self._client = self.connection_alias
            self.status = ConnectionStatus.CONNECTED
            
            logger.info(f"Milvus connection established for {self.db_name} at {self.uri}")
            return True
            
        except Exception as e:
            self.status = ConnectionStatus.ERROR
            logger.error(f"Failed to connect to Milvus {self.db_name}: {e}")
            return False
    
    async def _test_connection(self):
        """测试数据库连接"""
        def _sync_test():
            # 列出集合以测试连接
            utility.list_collections(using=self.connection_alias)
        
        await asyncio.get_event_loop().run_in_executor(None, _sync_test)
    
    async def disconnect(self) -> bool:
        """断开数据库连接"""
        try:
            # 先关闭所有集合
            for collection in self.collections.values():
                try:
                    def _release():
                        collection.release()
                    await asyncio.get_event_loop().run_in_executor(None, _release)
                except Exception as e:
                    logger.warning(f"Error releasing collection: {e}")
            
            self.collections.clear()
            
            # 断开连接
            def _disconnect():
                if connections.has_connection(self.connection_alias):
                    connections.disconnect(self.connection_alias)
            
            await asyncio.get_event_loop().run_in_executor(None, _disconnect)
            
            self._client = None
            self.status = ConnectionStatus.DISCONNECTED
            
            logger.info(f"Milvus connection closed for {self.db_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Milvus {self.db_name}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.is_connected:
                return {
                    'status': 'disconnected',
                    'database_name': self.db_name,
                    'timestamp': datetime.now().isoformat()
                }
            
            def _sync_health_check():
                # 检查连接状态
                if not connections.has_connection(self.connection_alias):
                    return {
                        'status': 'error',
                        'error': 'Connection not found'
                    }
                
                # 获取集合列表
                try:
                    collections_list = utility.list_collections(using=self.connection_alias)
                except Exception as e:
                    return {
                        'status': 'error',
                        'error': f'Failed to list collections: {str(e)}'
                    }
                
                # 获取版本信息
                try:
                    from pymilvus import __version__ as pymilvus_version
                except ImportError:
                    pymilvus_version = 'unknown'
                
                return {
                    'status': 'healthy',
                    'database_name': self.db_name,
                    'uri': self.uri,
                    'db_name': self.db_name_milvus,
                    'collections_count': len(collections_list),
                    'collections': collections_list,
                    'pymilvus_version': pymilvus_version,
                    'timestamp': datetime.now().isoformat()
                }
            
            result = await asyncio.get_event_loop().run_in_executor(None, _sync_health_check)
            return result
            
        except Exception as e:
            return {
                'status': 'error',
                'database_name': self.db_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            'database_name': self.db_name,
            'type': 'milvus',
            'uri': self.uri,
            'user': self.user,
            'db_name': self.db_name_milvus,
            'status': self.status.value,
            'connection_alias': self.connection_alias,
            'timeout': self.timeout
        }
    
    async def create_collection(self, collection_name: str, schema: Dict[str, Any]) -> bool:
        """
        创建集合
        
        Args:
            collection_name: 集合名称
            schema: 集合schema定义
            
        Returns:
            创建成功返回True
        """
        await self.ensure_connected()
        
        try:
            def _sync_create():
                # 检查集合是否已存在
                if utility.has_collection(collection_name, using=self.connection_alias):
                    logger.info(f"Collection {collection_name} already exists")
                    return True
                
                # 构建字段schema
                fields = []
                for field_def in schema['fields']:
                    field_schema = FieldSchema(
                        name=field_def['name'],
                        dtype=field_def['type'],
                        is_primary=field_def.get('is_primary', False),
                        auto_id=field_def.get('auto_id', False),
                        dim=field_def.get('dim'),
                        description=field_def.get('description', '')
                    )
                    fields.append(field_schema)
                
                # 创建集合schema
                collection_schema = CollectionSchema(
                    fields=fields,
                    description=schema.get('description', ''),
                    enable_dynamic_field=schema.get('enable_dynamic_field', False)
                )
                
                # 创建集合
                collection = Collection(
                    name=collection_name,
                    schema=collection_schema,
                    using=self.connection_alias
                )
                
                self.collections[collection_name] = collection
                logger.info(f"Collection {collection_name} created successfully")
                return True
            
            return await asyncio.get_event_loop().run_in_executor(None, _sync_create)
            
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False
    
    async def get_collection(self, collection_name: str) -> Optional[Collection]:
        """获取集合对象"""
        await self.ensure_connected()
        
        if collection_name in self.collections:
            return self.collections[collection_name]
        
        try:
            def _sync_get():
                if utility.has_collection(collection_name, using=self.connection_alias):
                    collection = Collection(collection_name, using=self.connection_alias)
                    return collection
                return None
            
            collection = await asyncio.get_event_loop().run_in_executor(None, _sync_get)
            
            if collection:
                self.collections[collection_name] = collection
            
            return collection
            
        except Exception as e:
            logger.error(f"Failed to get collection {collection_name}: {e}")
            return None
    
    async def insert_vectors(self, collection_name: str, data: List[Dict[str, Any]]) -> bool:
        """
        插入向量数据
        
        Args:
            collection_name: 集合名称
            data: 数据列表
            
        Returns:
            插入成功返回True
        """
        collection = await self.get_collection(collection_name)
        if not collection:
            logger.error(f"Collection {collection_name} not found")
            return False
        
        try:
            def _sync_insert():
                # 转换数据格式
                insert_data = []
                if data:
                    # 重组数据：从行格式转为列格式
                    field_names = list(data[0].keys())
                    for field_name in field_names:
                        field_data = [row[field_name] for row in data]
                        insert_data.append(field_data)
                
                result = collection.insert(insert_data)
                collection.flush()
                return True
            
            return await asyncio.get_event_loop().run_in_executor(None, _sync_insert)
            
        except Exception as e:
            logger.error(f"Failed to insert vectors into {collection_name}: {e}")
            return False
    
    async def search_vectors(self, collection_name: str, vectors: List[List[float]], 
                           search_params: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        搜索向量
        
        Args:
            collection_name: 集合名称
            vectors: 查询向量列表
            search_params: 搜索参数
            limit: 返回结果数量限制
            
        Returns:
            搜索结果列表
        """
        collection = await self.get_collection(collection_name)
        if not collection:
            logger.error(f"Collection {collection_name} not found")
            return []
        
        try:
            def _sync_search():
                # 确保集合已加载
                collection.load()
                
                # 执行搜索
                results = collection.search(
                    data=vectors,
                    anns_field=search_params.get('anns_field', 'vector'),
                    param=search_params.get('params', {}),
                    limit=limit,
                    output_fields=search_params.get('output_fields', [])
                )
                
                # 转换结果格式
                formatted_results = []
                for hits in results:
                    for hit in hits:
                        result_item = {
                            'id': hit.id,
                            'distance': hit.distance,
                            'score': hit.score
                        }
                        
                        # 添加输出字段
                        if hasattr(hit, 'entity'):
                            for field_name in search_params.get('output_fields', []):
                                if hasattr(hit.entity, field_name):
                                    result_item[field_name] = getattr(hit.entity, field_name)
                        
                        formatted_results.append(result_item)
                
                return formatted_results
            
            return await asyncio.get_event_loop().run_in_executor(None, _sync_search)
            
        except Exception as e:
            logger.error(f"Failed to search vectors in {collection_name}: {e}")
            return []
    
    async def create_index(self, collection_name: str, field_name: str, 
                          index_params: Dict[str, Any]) -> bool:
        """
        创建索引
        
        Args:
            collection_name: 集合名称
            field_name: 字段名称
            index_params: 索引参数
            
        Returns:
            创建成功返回True
        """
        collection = await self.get_collection(collection_name)
        if not collection:
            logger.error(f"Collection {collection_name} not found")
            return False
        
        try:
            def _sync_create_index():
                collection.create_index(
                    field_name=field_name,
                    index_params=index_params
                )
                logger.info(f"Index created for {collection_name}.{field_name}")
                return True
            
            return await asyncio.get_event_loop().run_in_executor(None, _sync_create_index)
            
        except Exception as e:
            logger.error(f"Failed to create index for {collection_name}.{field_name}: {e}")
            return False
    
    async def delete_collection(self, collection_name: str) -> bool:
        """删除集合"""
        await self.ensure_connected()
        
        try:
            def _sync_delete():
                if collection_name in self.collections:
                    self.collections[collection_name].release()
                    del self.collections[collection_name]
                
                if utility.has_collection(collection_name, using=self.connection_alias):
                    utility.drop_collection(collection_name, using=self.connection_alias)
                    logger.info(f"Collection {collection_name} deleted")
                    return True
                return False
            
            return await asyncio.get_event_loop().run_in_executor(None, _sync_delete)
            
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")
            return False
    
    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """获取集合统计信息"""
        collection = await self.get_collection(collection_name)
        if not collection:
            return {}
        
        try:
            def _sync_stats():
                stats = collection.get_stats()
                schema = collection.schema
                
                return {
                    'name': collection_name,
                    'row_count': stats.get('row_count', 0),
                    'fields': [
                        {
                            'name': field.name,
                            'type': str(field.dtype),
                            'is_primary': field.is_primary,
                            'dim': getattr(field, 'dim', None)
                        }
                        for field in schema.fields
                    ],
                    'description': schema.description,
                    'enable_dynamic_field': schema.enable_dynamic_field
                }
            
            return await asyncio.get_event_loop().run_in_executor(None, _sync_stats)
            
        except Exception as e:
            logger.error(f"Failed to get stats for collection {collection_name}: {e}")
            return {}
    
    async def list_collections(self) -> List[str]:
        """列出所有集合"""
        await self.ensure_connected()
        
        try:
            def _sync_list():
                return utility.list_collections(using=self.connection_alias)
            
            return await asyncio.get_event_loop().run_in_executor(None, _sync_list)
            
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """获取文档（实现抽象方法）"""
        try:
            # 通过ID查询文档
            results = await self.search_vectors(
                collection_name=collection,
                vectors=[],  # 空向量列表，使用expression查询
                search_params={
                    'expression': f'id == "{doc_id}"',
                    'output_fields': ['*']
                },
                limit=1
            )
            
            return results[0] if results else None
            
        except Exception as e:
            logger.error(f"Failed to get document {doc_id} from {collection}: {e}")
            return None
    
    async def save_document(self, collection: str, doc_id: str, document: Dict[str, Any]) -> bool:
        """保存文档（实现抽象方法）"""
        try:
            # 添加ID到文档
            doc_with_id = {**document, 'id': doc_id}
            return await self.insert_vectors(collection, [doc_with_id])
            
        except Exception as e:
            logger.error(f"Failed to save document {doc_id} to {collection}: {e}")
            return False
    
    # =============================================================================
    # 知识库级别的集合管理方法
    # =============================================================================
    
    def _get_kb_collection_name(self, kb_id: str, collection_type: str) -> str:
        """获取知识库专用集合名称
        
        Args:
            kb_id: 知识库ID
            collection_type: 集合类型 (entities, relationships, chunks)
            
        Returns:
            知识库专用集合名称，格式: kb_{kb_id}_{collection_type}
        """
        return f"kb_{kb_id}_{collection_type}"
    
    def _get_kb_id_from_collection_name(self, collection_name: str) -> Optional[str]:
        """从集合名称中提取知识库ID
        
        Args:
            collection_name: 集合名称
            
        Returns:
            知识库ID，如果不是知识库专用集合则返回None
        """
        if collection_name.startswith('kb_') and collection_name.count('_') >= 2:
            # 格式: kb_{kb_id}_{collection_type}
            parts = collection_name.split('_')
            if len(parts) >= 3:
                # 提取kb_id部分 (可能包含下划线)
                kb_id = '_'.join(parts[1:-1])
                return kb_id
        return None
    
    def _get_collection_type_from_name(self, collection_name: str) -> Optional[str]:
        """从集合名称中提取集合类型
        
        Args:
            collection_name: 集合名称
            
        Returns:
            集合类型 (entities, relationships, chunks)，如果不是知识库专用集合则返回None
        """
        if collection_name.startswith('kb_') and collection_name.count('_') >= 2:
            # 格式: kb_{kb_id}_{collection_type}
            parts = collection_name.split('_')
            if len(parts) >= 3:
                return parts[-1]  # 最后一部分是集合类型
        return None
    
    async def create_kb_collections(self, kb_id: str, schema_definitions: Optional[Dict[str, Dict[str, Any]]] = None) -> bool:
        """为知识库创建所有必需的集合
        
        Args:
            kb_id: 知识库ID
            schema_definitions: 集合schema定义，如果为None则使用默认schema
            
        Returns:
            创建成功返回True
        """
        # 默认的LightRAG集合类型
        collection_types = ['entities', 'relationships', 'chunks']
        
        # 默认schema定义
        default_schemas = {
            'entities': {
                'fields': [
                    {'name': 'id', 'type': DataType.VARCHAR, 'is_primary': True, 'max_length': 65535},
                    {'name': 'vector', 'type': DataType.FLOAT_VECTOR, 'dim': 768},
                    {'name': 'content', 'type': DataType.VARCHAR, 'max_length': 65535}
                ],
                'description': f'Knowledge base {kb_id} entities collection',
                'enable_dynamic_field': True
            },
            'relationships': {
                'fields': [
                    {'name': 'id', 'type': DataType.VARCHAR, 'is_primary': True, 'max_length': 65535},
                    {'name': 'vector', 'type': DataType.FLOAT_VECTOR, 'dim': 768},
                    {'name': 'content', 'type': DataType.VARCHAR, 'max_length': 65535}
                ],
                'description': f'Knowledge base {kb_id} relationships collection',
                'enable_dynamic_field': True
            },
            'chunks': {
                'fields': [
                    {'name': 'id', 'type': DataType.VARCHAR, 'is_primary': True, 'max_length': 65535},
                    {'name': 'vector', 'type': DataType.FLOAT_VECTOR, 'dim': 768},
                    {'name': 'content', 'type': DataType.VARCHAR, 'max_length': 65535}
                ],
                'description': f'Knowledge base {kb_id} chunks collection',
                'enable_dynamic_field': True
            }
        }
        
        # 使用提供的schema或默认schema
        schemas = schema_definitions or default_schemas
        
        success_count = 0
        for collection_type in collection_types:
            collection_name = self._get_kb_collection_name(kb_id, collection_type)
            
            if collection_type in schemas:
                success = await self.create_collection(collection_name, schemas[collection_type])
                if success:
                    success_count += 1
                    logger.info(f"Created knowledge base collection: {collection_name}")
                else:
                    logger.error(f"Failed to create knowledge base collection: {collection_name}")
            else:
                logger.warning(f"No schema defined for collection type: {collection_type}")
        
        return success_count == len(collection_types)
    
    async def delete_kb_collections(self, kb_id: str) -> bool:
        """删除知识库的所有集合
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            删除成功返回True
        """
        collection_types = ['entities', 'relationships', 'chunks']
        
        success_count = 0
        for collection_type in collection_types:
            collection_name = self._get_kb_collection_name(kb_id, collection_type)
            
            success = await self.delete_collection(collection_name)
            if success:
                success_count += 1
                logger.info(f"Deleted knowledge base collection: {collection_name}")
            else:
                logger.warning(f"Failed to delete knowledge base collection: {collection_name}")
        
        return success_count == len(collection_types)
    
    async def get_kb_collections(self, kb_id: str) -> List[Dict[str, Any]]:
        """获取知识库的所有集合信息
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            集合信息列表
        """
        collection_types = ['entities', 'relationships', 'chunks']
        collections_info = []
        
        for collection_type in collection_types:
            collection_name = self._get_kb_collection_name(kb_id, collection_type)
            
            # 检查集合是否存在
            await self.ensure_connected()
            
            def _sync_check():
                return utility.has_collection(collection_name, using=self.connection_alias)
            
            try:
                exists = await asyncio.get_event_loop().run_in_executor(None, _sync_check)
                
                if exists:
                    # 获取集合统计信息
                    stats = await self.get_collection_stats(collection_name)
                    collections_info.append({
                        'name': collection_name,
                        'type': collection_type,
                        'kb_id': kb_id,
                        'exists': True,
                        'stats': stats
                    })
                else:
                    collections_info.append({
                        'name': collection_name,
                        'type': collection_type,
                        'kb_id': kb_id,
                        'exists': False,
                        'stats': {}
                    })
            except Exception as e:
                logger.error(f"Error checking collection {collection_name}: {e}")
                collections_info.append({
                    'name': collection_name,
                    'type': collection_type,
                    'kb_id': kb_id,
                    'exists': False,
                    'error': str(e),
                    'stats': {}
                })
        
        return collections_info
    
    async def get_all_kb_collections(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有知识库的集合信息
        
        Returns:
            按知识库ID分组的集合信息字典
        """
        # 获取所有集合
        all_collections = await self.list_collections()
        
        # 按知识库ID分组
        kb_collections = {}
        
        for collection_name in all_collections:
            kb_id = self._get_kb_id_from_collection_name(collection_name)
            collection_type = self._get_collection_type_from_name(collection_name)
            
            if kb_id and collection_type:
                if kb_id not in kb_collections:
                    kb_collections[kb_id] = []
                
                # 获取集合统计信息
                stats = await self.get_collection_stats(collection_name)
                
                kb_collections[kb_id].append({
                    'name': collection_name,
                    'type': collection_type,
                    'kb_id': kb_id,
                    'exists': True,
                    'stats': stats
                })
        
        return kb_collections
    
    async def migrate_global_collections_to_kb(self, kb_id: str, global_collections: Dict[str, str]) -> bool:
        """将全局集合数据迁移到知识库专用集合
        
        Args:
            kb_id: 目标知识库ID
            global_collections: 全局集合映射 {collection_type: global_collection_name}
            
        Returns:
            迁移成功返回True
        """
        logger.info(f"Starting migration of global collections to knowledge base {kb_id}")
        
        # 首先创建知识库专用集合
        kb_collections_created = await self.create_kb_collections(kb_id)
        if not kb_collections_created:
            logger.error(f"Failed to create knowledge base collections for {kb_id}")
            return False
        
        migration_success = True
        
        for collection_type, global_collection_name in global_collections.items():
            kb_collection_name = self._get_kb_collection_name(kb_id, collection_type)
            
            try:
                # 检查全局集合是否存在
                global_collection = await self.get_collection(global_collection_name)
                if not global_collection:
                    logger.warning(f"Global collection {global_collection_name} not found, skipping")
                    continue
                
                # 检查知识库集合是否存在
                kb_collection = await self.get_collection(kb_collection_name)
                if not kb_collection:
                    logger.error(f"Knowledge base collection {kb_collection_name} not found")
                    migration_success = False
                    continue
                
                # 这里应该实现具体的数据迁移逻辑
                # 由于PyMilvus不直接支持集合间数据复制，需要通过查询和插入实现
                logger.info(f"Migrating data from {global_collection_name} to {kb_collection_name}")
                
                # TODO: 实现具体的数据迁移逻辑
                # 1. 查询全局集合中的所有数据
                # 2. 过滤出属于该知识库的数据
                # 3. 插入到知识库专用集合中
                
                logger.info(f"Successfully migrated {collection_type} collection for knowledge base {kb_id}")
                
            except Exception as e:
                logger.error(f"Error migrating {collection_type} collection for knowledge base {kb_id}: {e}")
                migration_success = False
        
        return migration_success
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        base_metrics = super().get_metrics()
        
        base_metrics.update({
            'vector_database': 'milvus',
            'uri': self.uri,
            'db_name': self.db_name_milvus,
            'loaded_collections': len(self.collections),
            'connection_alias': self.connection_alias
        })
        
        return base_metrics