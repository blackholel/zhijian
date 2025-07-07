"""
知识库管理器 - 业务逻辑层
"""

import logging
import uuid
import asyncio
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from ..repositories.knowledge_repository import KnowledgeRepository
from ..repositories.knowledge_file_repository import KnowledgeFileRepository
from ..repositories.knowledge_node_repository import KnowledgeNodeRepository
from ..repositories.permission_mixin import PermissionValidator, AuditLogger
from ..connection_manager import DatabaseConnectionManager
from server.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode

logger = logging.getLogger(__name__)


class KnowledgeBaseManager:
    """知识库管理器 - 统一的业务逻辑层"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        self.connection_manager = connection_manager
        
        # 初始化仓储
        self.kb_repo = KnowledgeRepository(connection_manager)
        self.file_repo = KnowledgeFileRepository(connection_manager)
        self.node_repo = KnowledgeNodeRepository(connection_manager)
        
        # 设置仓储间的引用
        self.file_repo.set_kb_repository(self.kb_repo)
        self.node_repo.set_repositories(self.kb_repo, self.file_repo)
        
        # 权限验证器
        self.permission_validator = PermissionValidator()
    
    # 知识库管理方法
    
    async def create_knowledge_base(self, kb_data: Dict[str, Any], 
                                  owner_id: str) -> KnowledgeDatabase:
        """创建知识库 - 完整业务流程"""
        try:
            # 数据验证
            self._validate_kb_data(kb_data)
            
            # 创建知识库
            kb = await self.kb_repo.create(kb_data, owner_id)
            
            # 在Session关闭前获取需要的属性
            kb_id = kb.db_id
            
            # 记录审计日志
            await AuditLogger.log_access_attempt(
                owner_id, 'knowledge_base', kb_id, 'create', True
            )
            
            logger.info(f"创建知识库成功: {kb_id} by {owner_id}")
            return kb
            
        except Exception as e:
            # 记录失败审计
            await AuditLogger.log_access_attempt(
                owner_id, 'knowledge_base', 'unknown', 'create', False,
                {'error': str(e)}
            )
            logger.error(f"创建知识库失败: {e}")
            raise
    
    async def get_knowledge_base(self, kb_id: str, user_id: str, 
                               include_files: bool = True) -> Optional[KnowledgeDatabase]:
        """获取知识库详情"""
        try:
            # 获取知识库
            kb = await self.kb_repo.get_by_id(kb_id, user_id, check_permission=True)
            
            if not kb:
                return None
            
            # 如果需要包含文件信息
            if include_files:
                files = await self.file_repo.get_files_by_database(kb_id, user_id)
                # 将文件信息添加到知识库对象中（如果需要）
                # kb.files = files
            
            # 记录访问审计
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'read', True
            )
            
            return kb
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'read', False,
                {'error': str(e)}
            )
            logger.error(f"获取知识库失败: {e}")
            return None
    
    async def update_knowledge_base(self, kb_id: str, updates: Dict[str, Any], 
                                  user_id: str) -> Optional[KnowledgeDatabase]:
        """更新知识库"""
        try:
            # 数据验证
            self._validate_kb_updates(updates)
            
            # 更新知识库
            kb = await self.kb_repo.update(kb_id, updates, user_id)
            
            if kb:
                await AuditLogger.log_access_attempt(
                    user_id, 'knowledge_base', kb_id, 'update', True,
                    {'updates': list(updates.keys())}
                )
                logger.info(f"更新知识库成功: {kb_id}")
            
            return kb
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'update', False,
                {'error': str(e)}
            )
            logger.error(f"更新知识库失败: {e}")
            raise
    
    async def delete_knowledge_base(self, kb_id: str, user_id: str) -> bool:
        """删除知识库 - 完整清理流程"""
        try:
            # 首先检查权限
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'admin')
            if not has_permission:
                raise PermissionError("没有删除权限")
            
            # 获取知识库信息（用于清理）
            kb = await self.kb_repo.get_by_id(kb_id, user_id, check_permission=False)
            if not kb:
                return False
            
            # 1. 删除所有文件的节点数据
            files = await self.file_repo.get_files_by_database(kb_id, user_id)
            for file_obj in files:
                await self.node_repo.batch_delete_by_file(file_obj.file_id, user_id)
            
            # 2. 删除文件记录
            for file_obj in files:
                await self.file_repo.delete(file_obj.file_id, user_id)
            
            # 3. 删除知识库记录（会级联删除权限）
            success = await self.kb_repo.delete(kb_id, user_id)
            
            if success:
                await AuditLogger.log_access_attempt(
                    user_id, 'knowledge_base', kb_id, 'delete', True
                )
                logger.info(f"删除知识库成功: {kb_id}")
            
            return success
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'delete', False,
                {'error': str(e)}
            )
            logger.error(f"删除知识库失败: {e}")
            raise
    
    async def get_user_knowledge_bases(self, user_id: str) -> List[KnowledgeDatabase]:
        """获取用户可访问的知识库列表"""
        try:
            return await self.kb_repo.get_user_accessible_kbs(user_id)
        except Exception as e:
            logger.error(f"获取用户知识库列表失败: {e}")
            return []
    
    # 文件管理方法
    
    async def upload_document_minio(self, kb_id: str, storage_key: str,
                                  filename: str, file_type: str, user_id: str,
                                  metadata: Dict[str, Any] = None, file_id: str = None,
                                  file_size: int = 0) -> KnowledgeFile:
        """上传文档到MinIO - 新的统一方法"""
        try:
            # 1. 权限检查
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有上传权限")
            
            # 2. 使用提供的file_id或生成新的
            if not file_id:
                file_id = str(uuid.uuid4()).replace('-', '')
            
            # 3. 创建文件记录（使用MinIO存储路径）
            file_record_data = {
                'file_id': file_id,
                'filename': filename,
                'path': storage_key,  # 使用MinIO存储键作为路径
                'file_type': file_type,
                'status': 'uploaded',  # MinIO已上传，直接设为uploaded
                'metadata': {
                    **(metadata or {}),
                    'storage_type': 'minio',
                    'file_size': file_size,
                    'storage_key': storage_key
                }
            }
            
            file_obj = await self.file_repo.create(file_record_data, kb_id, user_id)
            
            # 4. 异步启动文档处理（传递file_id而不是对象）
            asyncio.create_task(self._process_document_async(file_id, user_id))
            
            # 记录审计
            await AuditLogger.log_access_attempt(
                user_id, 'file', file_id, 'upload', True,
                {'filename': filename, 'kb_id': kb_id, 'storage_type': 'minio'}
            )
            
            logger.info(f"MinIO文档上传成功: {filename} -> {file_id}")
            return file_obj
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'file', 'unknown', 'upload', False,
                {'error': str(e), 'filename': filename, 'storage_type': 'minio'}
            )
            logger.error(f"MinIO文档上传失败: {e}")
            raise
    
    async def upload_document(self, kb_id: str, file_data: bytes, 
                            filename: str, file_type: str,
                            user_id: str, metadata: Dict[str, Any] = None) -> KnowledgeFile:
        """上传文档 - 完整处理流程"""
        try:
            # 1. 权限检查
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有上传权限")
            
            # 2. 生成文件ID和路径
            file_id = str(uuid.uuid4()).replace('-', '')
            file_path = f"saves/lightrag_data/{kb_id}/uploads/{filename}"
            
            # 3. 创建文件记录
            file_record_data = {
                'file_id': file_id,
                'filename': filename,
                'path': file_path,
                'file_type': file_type,
                'status': 'uploading'
            }
            
            file_obj = await self.file_repo.create(file_record_data, kb_id, user_id)
            
            # 4. 保存文件到存储（这里应该集成MinIO或文件系统）
            # TODO: 集成文件存储系统
            
            # 5. 更新文件状态为已上传
            await self.file_repo.update_file_status(file_id, 'uploaded')
            
            # 6. 异步启动文档处理（传递file_id而不是对象）
            asyncio.create_task(self._process_document_async(file_id, user_id))
            
            # 记录审计
            await AuditLogger.log_access_attempt(
                user_id, 'file', file_id, 'upload', True,
                {'filename': filename, 'kb_id': kb_id}
            )
            
            logger.info(f"文档上传成功: {filename} -> {file_id}")
            return file_obj
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'file', 'unknown', 'upload', False,
                {'error': str(e), 'filename': filename}
            )
            logger.error(f"文档上传失败: {e}")
            raise
    
    async def _process_document_async(self, file_id: str, user_id: str):
        """异步文档处理"""
        try:
            # 更新状态为处理中
            await self.file_repo.update_file_status(file_id, 'processing')
            
            # 获取文件信息（用于日志）
            file_obj = await self.file_repo.get_by_id(file_id, user_id, check_permission=False)
            filename = file_obj.filename if file_obj else file_id
            
            # TODO: 集成文档处理功能
            # 1. OCR处理（如果是图片）
            # 2. 文本提取
            # 3. 文档分块
            # 4. 向量化
            # 5. 存储到向量数据库
            
            # 模拟处理过程
            await asyncio.sleep(2)
            
            # 创建示例节点数据
            nodes_data = [
                {
                    'text': f"文档 {filename} 的内容块 1",
                    'start_char_idx': 0,
                    'end_char_idx': 100,
                    'metadata': {'chunk_index': 0}
                },
                {
                    'text': f"文档 {filename} 的内容块 2",
                    'start_char_idx': 100,
                    'end_char_idx': 200,
                    'metadata': {'chunk_index': 1}
                }
            ]
            
            # 批量创建节点
            await self.node_repo.batch_create(nodes_data, file_id, user_id)
            
            # 更新文件状态为完成
            await self.file_repo.update_file_status(file_id, 'completed')
            
            logger.info(f"文档处理完成: {file_id}")
            
        except Exception as e:
            # 更新状态为失败
            await self.file_repo.update_file_status(file_id, 'failed')
            logger.error(f"文档处理失败: {e}")
    
    async def get_file_details(self, file_id: str, user_id: str, 
                             include_nodes: bool = False) -> Optional[KnowledgeFile]:
        """获取文件详情"""
        try:
            file_obj = await self.file_repo.get_by_id(file_id, user_id, check_permission=True)
            
            if file_obj and include_nodes:
                nodes = await self.node_repo.get_nodes_by_file(file_id, user_id)
                # 将节点信息添加到文件对象中
                # file_obj.nodes = nodes
            
            return file_obj
            
        except Exception as e:
            logger.error(f"获取文件详情失败: {e}")
            return None
    
    async def delete_document(self, file_id: str, user_id: str) -> bool:
        """删除文档"""
        try:
            # 1. 删除所有节点
            await self.node_repo.batch_delete_by_file(file_id, user_id)
            
            # 2. 删除文件记录
            success = await self.file_repo.delete(file_id, user_id)
            
            # 3. 删除物理文件（TODO: 集成文件存储）
            
            if success:
                await AuditLogger.log_access_attempt(
                    user_id, 'file', file_id, 'delete', True
                )
                logger.info(f"删除文档成功: {file_id}")
            
            return success
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'file', file_id, 'delete', False,
                {'error': str(e)}
            )
            logger.error(f"删除文档失败: {e}")
            raise
    
    # 查询和搜索方法
    
    async def query_knowledge_base(self, kb_id: str, query: str, 
                                 user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """查询知识库 - RAG流程"""
        try:
            # 权限检查
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'read')
            if not has_permission:
                raise PermissionError("没有查询权限")
            
            # 1. 文本搜索（当前实现）
            nodes = await self.node_repo.search_nodes_by_text(kb_id, query, user_id, limit)
            
            # 2. TODO: 向量搜索
            # vector_nodes = await self._vector_search(kb_id, query, limit)
            
            # 3. 合并和排序结果
            results = []
            for node in nodes:
                results.append({
                    'node_id': node.id,
                    'text': node.text,
                    'file_id': node.file_id,
                    'metadata': node.meta_info,
                    'score': 1.0  # 临时评分
                })
            
            # 记录查询审计
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'query', True,
                {'query': query, 'results_count': len(results)}
            )
            
            return results
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'query', False,
                {'error': str(e), 'query': query}
            )
            logger.error(f"查询知识库失败: {e}")
            raise
    
    # 权限管理方法
    
    async def grant_kb_permission(self, kb_id: str, target_user_id: str, 
                                permission_type: str, granted_by: str,
                                expires_at: datetime = None) -> bool:
        """授予知识库权限"""
        try:
            success = await self.kb_repo.grant_permission(
                kb_id, target_user_id, permission_type, granted_by, expires_at
            )
            
            if success:
                await AuditLogger.log_permission_change(
                    granted_by, target_user_id, 'knowledge_base', kb_id,
                    'none', permission_type
                )
                logger.info(f"授权成功: {kb_id} -> {target_user_id} ({permission_type})")
            
            return success
            
        except Exception as e:
            logger.error(f"授权失败: {e}")
            raise
    
    async def revoke_kb_permission(self, kb_id: str, target_user_id: str, 
                                 revoked_by: str) -> bool:
        """撤销知识库权限"""
        try:
            success = await self.kb_repo.revoke_permission(kb_id, target_user_id, revoked_by)
            
            if success:
                await AuditLogger.log_permission_change(
                    revoked_by, target_user_id, 'knowledge_base', kb_id,
                    'existing', 'none'
                )
                logger.info(f"撤销权限成功: {kb_id} -> {target_user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"撤销权限失败: {e}")
            raise
    
    # 统计和监控方法
    
    async def get_knowledge_base_statistics(self, kb_id: str, 
                                          user_id: str) -> Dict[str, Any]:
        """获取知识库统计信息"""
        try:
            # 权限检查
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'read')
            if not has_permission:
                raise PermissionError("没有查看权限")
            
            # 获取文件统计
            file_stats = await self.file_repo.get_file_statistics(database_id=kb_id)
            
            # 获取节点统计
            node_stats = await self.node_repo.get_node_statistics(database_id=kb_id)
            
            # 合并统计信息
            return {
                'kb_id': kb_id,
                'files': file_stats,
                'nodes': node_stats,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {'error': str(e)}
    
    # 数据验证方法
    
    def _validate_kb_data(self, kb_data: Dict[str, Any]):
        """验证知识库数据"""
        required_fields = ['name']
        for field in required_fields:
            if field not in kb_data or not kb_data[field]:
                raise ValueError(f"缺少必需字段: {field}")
        
        # 验证名称长度
        if len(kb_data['name']) > 255:
            raise ValueError("知识库名称过长")
    
    def _validate_kb_updates(self, updates: Dict[str, Any]):
        """验证知识库更新数据"""
        # 不允许更新的字段
        forbidden_fields = ['id', 'db_id', 'created_at', 'owner_id']
        for field in forbidden_fields:
            if field in updates:
                raise ValueError(f"不允许更新字段: {field}")
        
        # 验证名称长度
        if 'name' in updates and len(updates['name']) > 255:
            raise ValueError("知识库名称过长")
    
    # 健康检查
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查各个仓储的健康状态
            kb_health = await self.kb_repo.health_check()
            file_health = await self.file_repo.health_check()
            node_health = await self.node_repo.health_check()
            
            return {
                'status': 'healthy',
                'components': {
                    'knowledge_repository': kb_health,
                    'file_repository': file_health,
                    'node_repository': node_health
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }