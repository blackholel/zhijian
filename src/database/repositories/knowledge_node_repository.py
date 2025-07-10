"""
知识库节点（分块）数据仓储
"""

import logging
import uuid
import hashlib
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_, func

from .base import PostgreSQLRepository
from ..connection_manager import DatabaseConnectionManager
from server.models.kb_models import KnowledgeNode, KnowledgeFile, KnowledgeDatabase
from server.auth.models.user_models import User

logger = logging.getLogger(__name__)


class KnowledgeNodeRepository(PostgreSQLRepository[KnowledgeNode]):
    """知识库节点数据仓储"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        super().__init__(connection_manager, 'server_db')
        self.enable_cache(ttl=3600)
        self.kb_repo = None  # 将在manager中注入
        self.file_repo = None  # 将在manager中注入
    
    def set_repositories(self, kb_repo, file_repo):
        """设置仓储引用"""
        self.kb_repo = kb_repo
        self.file_repo = file_repo
    
    async def _check_node_permission(self, node_id: int, user_id: str, permission: str) -> bool:
        """检查用户对节点的权限"""
        try:
            async with await self.get_session() as session:
                # 通过节点找到文件，再找到知识库
                node = session.query(KnowledgeNode).join(KnowledgeFile).filter(
                    KnowledgeNode.id == node_id
                ).first()
                
                if not node or not node.file:
                    return False
                
                # 通过知识库权限检查
                if self.kb_repo:
                    return await self.kb_repo._check_kb_permission(
                        node.file.database_id, user_id, permission
                    )
                
                return False
        except Exception as e:
            logger.error(f"检查节点权限失败: {e}")
            return False
    
    async def _check_file_permission_for_nodes(self, file_id: str, user_id: str, permission: str) -> bool:
        """检查用户对文件节点的权限"""
        try:
            if self.file_repo:
                return await self.file_repo._check_file_permission(file_id, user_id, permission)
            return False
        except Exception as e:
            logger.error(f"检查文件节点权限失败: {e}")
            return False
    
    async def create(self, node_data: Dict[str, Any], file_id: str, 
                    user_id: str) -> KnowledgeNode:
        """创建单个知识节点"""
        try:
            # 检查文件权限
            has_permission = await self._check_file_permission_for_nodes(file_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有创建节点权限")
            
            async with await self.get_session() as session:
                # 生成节点哈希
                text = node_data.get('text', '')
                text_hash = hashlib.md5(text.encode()).hexdigest()
                
                # 创建节点记录
                node = KnowledgeNode(
                    file_id=file_id,
                    text=text,
                    hash=text_hash,
                    start_char_idx=node_data.get('start_char_idx'),
                    end_char_idx=node_data.get('end_char_idx'),
                    meta_info=node_data.get('metadata', {})
                )
                
                session.add(node)
                session.commit()
                session.refresh(node)
                
                # 清除相关缓存
                await self._delete_from_cache(f"file_nodes:{file_id}")
                
                logger.info(f"创建知识节点成功: {node.id}")
                return node
                
        except Exception as e:
            logger.error(f"创建知识节点失败: {e}")
            raise
    
    async def batch_create(self, nodes_data: List[Dict[str, Any]], file_id: str, 
                          user_id: str) -> List[KnowledgeNode]:
        """批量创建知识节点"""
        try:
            # 检查文件权限
            has_permission = await self._check_file_permission_for_nodes(file_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有创建节点权限")
            
            async with await self.get_session() as session:
                nodes = []
                
                for node_data in nodes_data:
                    # 生成节点哈希
                    text = node_data.get('text', '')
                    text_hash = hashlib.md5(text.encode()).hexdigest()
                    
                    # 创建节点记录
                    node = KnowledgeNode(
                        file_id=file_id,
                        text=text,
                        hash=text_hash,
                        start_char_idx=node_data.get('start_char_idx'),
                        end_char_idx=node_data.get('end_char_idx'),
                        meta_info=node_data.get('metadata', {})
                    )
                    
                    nodes.append(node)
                    session.add(node)
                
                session.commit()
                
                # 刷新所有节点以获取ID
                for node in nodes:
                    session.refresh(node)
                
                # 清除相关缓存
                await self._delete_from_cache(f"file_nodes:{file_id}")
                
                logger.info(f"批量创建知识节点成功: {len(nodes)}个")
                return nodes
                
        except Exception as e:
            logger.error(f"批量创建知识节点失败: {e}")
            raise
    
    async def get_by_id(self, node_id: int, user_id: str = None, 
                       check_permission: bool = True) -> Optional[KnowledgeNode]:
        """根据ID获取节点"""
        try:
            # 尝试从缓存获取
            cache_key = f"node:{node_id}"
            cached_node = await self._get_from_cache(cache_key)
            
            if cached_node:
                # 权限检查
                if check_permission and user_id:
                    has_permission = await self._check_node_permission(node_id, user_id, 'read')
                    if not has_permission:
                        return None
                return cached_node
            
            async with await self.get_session() as session:
                node = session.query(KnowledgeNode).options(
                    selectinload(KnowledgeNode.file)
                ).filter(KnowledgeNode.id == node_id).first()
                
                if not node:
                    return None
                
                # 权限检查
                if check_permission and user_id:
                    has_permission = await self._check_node_permission(node_id, user_id, 'read')
                    if not has_permission:
                        return None
                
                # 缓存结果
                await self._set_to_cache(cache_key, node)
                
                return node
                
        except Exception as e:
            logger.error(f"获取知识节点失败: {e}")
            return None
    
    async def update(self, node_id: int, updates: Dict[str, Any], 
                    user_id: str) -> Optional[KnowledgeNode]:
        """更新知识节点"""
        try:
            # 权限检查
            has_permission = await self._check_node_permission(node_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有更新权限")
            
            async with await self.get_session() as session:
                node = session.query(KnowledgeNode).filter(
                    KnowledgeNode.id == node_id
                ).first()
                
                if not node:
                    return None
                
                # 更新字段
                for key, value in updates.items():
                    if hasattr(node, key) and key not in ['id', 'file_id']:
                        setattr(node, key, value)
                
                # 如果更新了text，重新计算hash
                if 'text' in updates:
                    node.hash = hashlib.md5(updates['text'].encode()).hexdigest()
                
                session.commit()
                session.refresh(node)
                
                # 清除缓存
                await self._delete_from_cache(f"node:{node_id}")
                await self._delete_from_cache(f"file_nodes:{node.file_id}")
                
                logger.info(f"更新知识节点成功: {node_id}")
                return node
                
        except Exception as e:
            logger.error(f"更新知识节点失败: {e}")
            raise
    
    async def delete(self, node_id: int, user_id: str) -> bool:
        """删除知识节点"""
        try:
            # 权限检查
            has_permission = await self._check_node_permission(node_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有删除权限")
            
            async with await self.get_session() as session:
                node = session.query(KnowledgeNode).filter(
                    KnowledgeNode.id == node_id
                ).first()
                
                if not node:
                    return False
                
                file_id = node.file_id
                
                # 删除节点
                session.delete(node)
                session.commit()
                
                # 清除缓存
                await self._delete_from_cache(f"node:{node_id}")
                await self._delete_from_cache(f"file_nodes:{file_id}")
                
                logger.info(f"删除知识节点成功: {node_id}")
                return True
                
        except Exception as e:
            logger.error(f"删除知识节点失败: {e}")
            raise
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[KnowledgeNode]:
        """查找所有节点（仅超级管理员）"""
        try:
            async with await self.get_session() as session:
                nodes = session.query(KnowledgeNode).offset(offset).limit(limit).all()
                return nodes
        except Exception as e:
            logger.error(f"查找所有节点失败: {e}")
            return []
    
    async def get_nodes_by_file(self, file_id: str, user_id: str = None) -> List[KnowledgeNode]:
        """获取文件下的所有节点"""
        try:
            # 权限检查
            if user_id:
                has_permission = await self._check_file_permission_for_nodes(file_id, user_id, 'read')
                if not has_permission:
                    return []
            
            # 尝试从缓存获取
            cache_key = f"file_nodes:{file_id}"
            cached_nodes = await self._get_from_cache(cache_key)
            if cached_nodes:
                return cached_nodes
            
            async with await self.get_session() as session:
                nodes = session.query(KnowledgeNode).filter(
                    KnowledgeNode.file_id == file_id
                ).order_by(KnowledgeNode.start_char_idx).all()
                
                # 缓存结果
                await self._set_to_cache(cache_key, nodes, ttl=1800)  # 30分钟缓存
                
                return nodes
                
        except Exception as e:
            logger.error(f"获取文件节点失败: {e}")
            return []
    
    async def get_nodes_by_database(self, database_id: str, user_id: str = None, 
                                  limit: int = 1000) -> List[KnowledgeNode]:
        """获取知识库下的所有节点"""
        try:
            # 权限检查
            if user_id and self.kb_repo:
                has_permission = await self.kb_repo._check_kb_permission(database_id, user_id, 'read')
                if not has_permission:
                    return []
            
            async with await self.get_session() as session:
                nodes = session.query(KnowledgeNode).join(KnowledgeFile).filter(
                    KnowledgeFile.database_id == database_id
                ).limit(limit).all()
                
                return nodes
                
        except Exception as e:
            logger.error(f"获取知识库节点失败: {e}")
            return []
    
    async def search_nodes_by_text(self, database_id: str, search_text: str, 
                                 user_id: str = None, limit: int = 20) -> List[KnowledgeNode]:
        """根据文本搜索节点"""
        try:
            # 权限检查
            if user_id and self.kb_repo:
                has_permission = await self.kb_repo._check_kb_permission(database_id, user_id, 'read')
                if not has_permission:
                    return []
            
            async with await self.get_session() as session:
                # 使用PostgreSQL的全文搜索
                nodes = session.query(KnowledgeNode).join(KnowledgeFile).filter(
                    and_(
                        KnowledgeFile.database_id == database_id,
                        KnowledgeNode.text.contains(search_text)
                    )
                ).limit(limit).all()
                
                return nodes
                
        except Exception as e:
            logger.error(f"搜索节点失败: {e}")
            return []
    
    async def get_similar_nodes(self, node_id: int, user_id: str = None, 
                              limit: int = 10) -> List[Tuple[KnowledgeNode, float]]:
        """获取相似节点（基于向量相似度）"""
        try:
            # 权限检查
            has_permission = await self._check_node_permission(node_id, user_id, 'read')
            if not has_permission:
                return []
            
            # 这里需要集成向量数据库（Milvus）进行相似度搜索
            # 当前先返回空列表，后续可以集成向量搜索
            
            logger.info(f"相似节点搜索功能待实现: {node_id}")
            return []
                
        except Exception as e:
            logger.error(f"获取相似节点失败: {e}")
            return []
    
    async def get_node_statistics(self, database_id: str = None, 
                                file_id: str = None, user_id: str = None) -> Dict[str, Any]:
        """获取节点统计信息"""
        try:
            async with await self.get_session() as session:
                query = session.query(KnowledgeNode)
                
                if file_id:
                    query = query.filter(KnowledgeNode.file_id == file_id)
                elif database_id:
                    query = query.join(KnowledgeFile).filter(
                        KnowledgeFile.database_id == database_id
                    )
                
                nodes = query.all()
                
                # 统计信息
                total_nodes = len(nodes)
                total_chars = sum(len(node.text) for node in nodes if node.text)
                avg_chars = total_chars / total_nodes if total_nodes > 0 else 0
                
                # 计算长度分布
                length_distribution = {
                    'short': 0,  # < 100字符
                    'medium': 0,  # 100-500字符
                    'long': 0,   # > 500字符
                }
                
                for node in nodes:
                    if node.text:
                        length = len(node.text)
                        if length < 100:
                            length_distribution['short'] += 1
                        elif length < 500:
                            length_distribution['medium'] += 1
                        else:
                            length_distribution['long'] += 1
                
                return {
                    'total_nodes': total_nodes,
                    'total_characters': total_chars,
                    'average_characters': round(avg_chars, 2),
                    'length_distribution': length_distribution,
                    'database_id': database_id,
                    'file_id': file_id
                }
                
        except Exception as e:
            logger.error(f"获取节点统计失败: {e}")
            return {
                'total_nodes': 0,
                'total_characters': 0,
                'average_characters': 0,
                'length_distribution': {'short': 0, 'medium': 0, 'long': 0},
                'error': str(e)
            }
    
    async def batch_delete_by_file(self, file_id: str, user_id: str) -> int:
        """批量删除文件的所有节点"""
        try:
            # 权限检查
            has_permission = await self._check_file_permission_for_nodes(file_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有删除权限")
            
            async with await self.get_session() as session:
                # 计算要删除的节点数
                count = session.query(KnowledgeNode).filter(
                    KnowledgeNode.file_id == file_id
                ).count()
                
                # 批量删除
                session.query(KnowledgeNode).filter(
                    KnowledgeNode.file_id == file_id
                ).delete()
                
                session.commit()
                
                # 清除缓存
                await self._delete_from_cache(f"file_nodes:{file_id}")
                
                logger.info(f"批量删除文件节点成功: {count}个")
                return count
                
        except Exception as e:
            logger.error(f"批量删除文件节点失败: {e}")
            raise
    
    async def rebuild_file_nodes(self, file_id: str, nodes_data: List[Dict[str, Any]], 
                               user_id: str) -> List[KnowledgeNode]:
        """重建文件的所有节点"""
        try:
            # 先删除现有节点
            await self.batch_delete_by_file(file_id, user_id)
            
            # 创建新节点
            new_nodes = await self.batch_create(nodes_data, file_id, user_id)
            
            logger.info(f"重建文件节点成功: {len(new_nodes)}个")
            return new_nodes
            
        except Exception as e:
            logger.error(f"重建文件节点失败: {e}")
            raise