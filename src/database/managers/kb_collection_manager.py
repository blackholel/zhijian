"""
知识库集合管理器 - 负责知识库级别的Milvus集合管理
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..adapters.milvus import MilvusAdapter
from ..manager import get_database_manager

logger = logging.getLogger(__name__)


class KnowledgeBaseCollectionManager:
    """知识库集合管理器 - 管理知识库级别的向量集合"""
    
    def __init__(self):
        """初始化知识库集合管理器"""
        self.db_manager = None
        self.milvus_adapter: Optional[MilvusAdapter] = None
        
    async def initialize(self):
        """初始化管理器"""
        try:
            self.db_manager = get_database_manager()
            await self.db_manager.initialize()
            
            # 获取Milvus适配器
            self.milvus_adapter = await self.db_manager.get_milvus_adapter()
            if not self.milvus_adapter:
                raise Exception("Failed to get Milvus adapter")
            
            logger.info("Knowledge base collection manager initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize KB collection manager: {e}")
            return False
    
    async def ensure_initialized(self):
        """确保管理器已初始化"""
        if not self.db_manager or not self.milvus_adapter:
            await self.initialize()
    
    async def create_kb_collections(self, kb_id: str, force_recreate: bool = False) -> Dict[str, Any]:
        """
        为知识库创建所有必需的集合
        
        Args:
            kb_id: 知识库ID
            force_recreate: 是否强制重新创建（删除现有集合）
            
        Returns:
            操作结果
        """
        await self.ensure_initialized()
        
        result = {
            'kb_id': kb_id,
            'success': False,
            'collections_created': [],
            'collections_failed': [],
            'message': '',
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # 检查现有集合
            existing_collections = await self.milvus_adapter.get_kb_collections(kb_id)
            
            if force_recreate:
                # 强制重新创建：先删除现有集合
                logger.info(f"Force recreating collections for knowledge base {kb_id}")
                for collection_info in existing_collections:
                    if collection_info['exists']:
                        await self.milvus_adapter.delete_collection(collection_info['name'])
                        logger.info(f"Deleted existing collection: {collection_info['name']}")
            else:
                # 检查是否已存在所有必需的集合
                existing_count = sum(1 for c in existing_collections if c['exists'])
                if existing_count == len(existing_collections):
                    result.update({
                        'success': True,
                        'message': 'All collections already exist',
                        'collections_created': [c['name'] for c in existing_collections if c['exists']]
                    })
                    return result
            
            # 创建集合
            success = await self.milvus_adapter.create_kb_collections(kb_id)
            
            if success:
                # 获取创建后的集合信息
                created_collections = await self.milvus_adapter.get_kb_collections(kb_id)
                
                result.update({
                    'success': True,
                    'message': f'Successfully created {len(created_collections)} collections for knowledge base {kb_id}',
                    'collections_created': [c['name'] for c in created_collections if c['exists']],
                    'collections_info': created_collections
                })
                
                logger.info(f"Successfully created collections for knowledge base {kb_id}")
            else:
                result.update({
                    'success': False,
                    'message': 'Failed to create one or more collections'
                })
                
        except Exception as e:
            logger.error(f"Error creating collections for knowledge base {kb_id}: {e}")
            result.update({
                'success': False,
                'message': f'Error: {str(e)}'
            })
        
        return result
    
    async def delete_kb_collections(self, kb_id: str, confirm: bool = False) -> Dict[str, Any]:
        """
        删除知识库的所有集合
        
        Args:
            kb_id: 知识库ID
            confirm: 确认删除（安全检查）
            
        Returns:
            操作结果
        """
        await self.ensure_initialized()
        
        result = {
            'kb_id': kb_id,
            'success': False,
            'collections_deleted': [],
            'collections_failed': [],
            'message': '',
            'timestamp': datetime.now().isoformat()
        }
        
        if not confirm:
            result.update({
                'success': False,
                'message': 'Deletion not confirmed. Set confirm=True to proceed.'
            })
            return result
        
        try:
            # 获取现有集合
            existing_collections = await self.milvus_adapter.get_kb_collections(kb_id)
            collections_to_delete = [c for c in existing_collections if c['exists']]
            
            if not collections_to_delete:
                result.update({
                    'success': True,
                    'message': 'No collections found for the knowledge base'
                })
                return result
            
            # 删除集合
            success = await self.milvus_adapter.delete_kb_collections(kb_id)
            
            if success:
                result.update({
                    'success': True,
                    'message': f'Successfully deleted {len(collections_to_delete)} collections for knowledge base {kb_id}',
                    'collections_deleted': [c['name'] for c in collections_to_delete]
                })
                
                logger.info(f"Successfully deleted collections for knowledge base {kb_id}")
            else:
                result.update({
                    'success': False,
                    'message': 'Failed to delete one or more collections'
                })
                
        except Exception as e:
            logger.error(f"Error deleting collections for knowledge base {kb_id}: {e}")
            result.update({
                'success': False,
                'message': f'Error: {str(e)}'
            })
        
        return result
    
    async def get_kb_collection_info(self, kb_id: str) -> Dict[str, Any]:
        """
        获取知识库集合信息
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            集合信息
        """
        await self.ensure_initialized()
        
        try:
            collections_info = await self.milvus_adapter.get_kb_collections(kb_id)
            
            return {
                'kb_id': kb_id,
                'collections': collections_info,
                'total_collections': len(collections_info),
                'existing_collections': len([c for c in collections_info if c['exists']]),
                'missing_collections': len([c for c in collections_info if not c['exists']]),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting collection info for knowledge base {kb_id}: {e}")
            return {
                'kb_id': kb_id,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_all_kb_collections_summary(self) -> Dict[str, Any]:
        """
        获取所有知识库的集合摘要信息
        
        Returns:
            所有知识库的集合摘要
        """
        await self.ensure_initialized()
        
        try:
            all_kb_collections = await self.milvus_adapter.get_all_kb_collections()
            
            summary = {
                'total_knowledge_bases': len(all_kb_collections),
                'knowledge_bases': {},
                'global_stats': {
                    'total_collections': 0,
                    'total_entities': 0,
                    'total_relationships': 0,
                    'total_chunks': 0
                },
                'timestamp': datetime.now().isoformat()
            }
            
            for kb_id, collections in all_kb_collections.items():
                kb_summary = {
                    'collections': collections,
                    'collection_count': len(collections),
                    'stats': {
                        'entities': 0,
                        'relationships': 0,
                        'chunks': 0
                    }
                }
                
                # 统计各类型集合的数据量
                for collection in collections:
                    collection_type = collection['type']
                    row_count = collection.get('stats', {}).get('row_count', 0)
                    
                    if collection_type in kb_summary['stats']:
                        kb_summary['stats'][collection_type] = row_count
                        summary['global_stats'][f'total_{collection_type}'] += row_count
                    
                    summary['global_stats']['total_collections'] += 1
                
                summary['knowledge_bases'][kb_id] = kb_summary
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting all KB collections summary: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def migrate_from_global_collections(self, kb_id: str, 
                                            global_collection_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        从全局集合迁移数据到知识库专用集合
        
        Args:
            kb_id: 知识库ID
            global_collection_mapping: 全局集合映射 {collection_type: global_collection_name}
            
        Returns:
            迁移结果
        """
        await self.ensure_initialized()
        
        # 默认的全局集合映射
        default_mapping = {
            'entities': 'entities',
            'relationships': 'relationships', 
            'chunks': 'chunks'
        }
        
        mapping = global_collection_mapping or default_mapping
        
        result = {
            'kb_id': kb_id,
            'success': False,
            'migrated_collections': [],
            'failed_collections': [],
            'message': '',
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # 执行迁移
            success = await self.milvus_adapter.migrate_global_collections_to_kb(kb_id, mapping)
            
            if success:
                result.update({
                    'success': True,
                    'message': f'Successfully migrated collections for knowledge base {kb_id}',
                    'migrated_collections': list(mapping.keys())
                })
                logger.info(f"Successfully migrated global collections to knowledge base {kb_id}")
            else:
                result.update({
                    'success': False,
                    'message': 'Failed to migrate one or more collections'
                })
                
        except Exception as e:
            logger.error(f"Error migrating collections for knowledge base {kb_id}: {e}")
            result.update({
                'success': False,
                'message': f'Error: {str(e)}'
            })
        
        return result
    
    async def health_check(self) -> Dict[str, Any]:
        """
        集合管理器健康检查
        
        Returns:
            健康状态信息
        """
        try:
            await self.ensure_initialized()
            
            # 检查Milvus连接
            milvus_health = await self.milvus_adapter.health_check()
            
            # 获取集合概览
            collections_summary = await self.get_all_kb_collections_summary()
            
            return {
                'status': 'healthy' if milvus_health.get('status') == 'healthy' else 'unhealthy',
                'milvus_health': milvus_health,
                'collections_summary': collections_summary,
                'manager_initialized': self.db_manager is not None and self.milvus_adapter is not None,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Collection manager health check failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


# 全局实例
_kb_collection_manager = None


async def get_kb_collection_manager() -> KnowledgeBaseCollectionManager:
    """获取知识库集合管理器实例"""
    global _kb_collection_manager
    
    if _kb_collection_manager is None:
        _kb_collection_manager = KnowledgeBaseCollectionManager()
        await _kb_collection_manager.initialize()
    
    return _kb_collection_manager