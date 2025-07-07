"""
知识库文件数据仓储
"""

import logging
import uuid
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_

from .base import PostgreSQLRepository
from ..connection_manager import DatabaseConnectionManager
from server.models.kb_models import KnowledgeFile, KnowledgeDatabase, KnowledgeNode
from server.models.user_model import User

logger = logging.getLogger(__name__)


class KnowledgeFileRepository(PostgreSQLRepository[KnowledgeFile]):
    """知识库文件数据仓储"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        super().__init__(connection_manager, 'server_db')
        self.enable_cache(ttl=3600)
        self.kb_repo = None  # 将在manager中注入
    
    def set_kb_repository(self, kb_repo):
        """设置知识库仓储引用"""
        self.kb_repo = kb_repo
    
    async def _check_file_permission(self, file_id: str, user_id: str, permission: str) -> bool:
        """检查用户对文件的权限"""
        try:
            async with await self.get_session() as session:
                file_obj = session.query(KnowledgeFile).filter(
                    KnowledgeFile.file_id == file_id
                ).first()
                
                if not file_obj:
                    return False
                
                # 通过知识库权限检查
                if self.kb_repo:
                    return await self.kb_repo._check_kb_permission(
                        file_obj.database_id, user_id, permission
                    )
                
                return False
        except Exception as e:
            logger.error(f"检查文件权限失败: {e}")
            return False
    
    async def create(self, file_data: Dict[str, Any], database_id: str, 
                    uploaded_by: str) -> KnowledgeFile:
        """创建文件记录"""
        try:
            # 检查知识库权限
            if self.kb_repo:
                has_permission = await self.kb_repo._check_kb_permission(
                    database_id, uploaded_by, 'write'
                )
                if not has_permission:
                    raise PermissionError("没有上传权限")
            
            async with await self.get_session() as session:
                # 生成文件ID
                file_id = file_data.get('file_id', str(uuid.uuid4()).replace('-', ''))
                
                # 创建文件记录
                file_obj = KnowledgeFile(
                    file_id=file_id,
                    database_id=database_id,
                    filename=file_data['filename'],
                    path=file_data['path'],
                    file_type=file_data.get('file_type', 'unknown'),
                    status=file_data.get('status', 'uploading'),
                    uploaded_by=uploaded_by
                )
                
                session.add(file_obj)
                session.commit()
                session.refresh(file_obj)
                
                # 清除相关缓存
                await self._delete_from_cache(f"kb_files:{database_id}")
                await self._delete_from_cache(f"user_files:{uploaded_by}")
                
                logger.info(f"创建文件记录成功: {file_id}")
                return file_obj
                
        except Exception as e:
            logger.error(f"创建文件记录失败: {e}")
            raise
    
    async def get_by_id(self, file_id: str, user_id: str = None, 
                       check_permission: bool = True) -> Optional[KnowledgeFile]:
        """根据ID获取文件"""
        try:
            # 尝试从缓存获取
            cache_key = f"file:{file_id}"
            cached_file = await self._get_from_cache(cache_key)
            
            if cached_file:
                # 权限检查
                if check_permission and user_id:
                    has_permission = await self._check_file_permission(file_id, user_id, 'read')
                    if not has_permission:
                        return None
                return cached_file
            
            async with await self.get_session() as session:
                file_obj = session.query(KnowledgeFile).options(
                    selectinload(KnowledgeFile.nodes)
                ).filter(KnowledgeFile.file_id == file_id).first()
                
                if not file_obj:
                    return None
                
                # 权限检查
                if check_permission and user_id:
                    has_permission = await self._check_file_permission(file_id, user_id, 'read')
                    if not has_permission:
                        return None
                
                # 缓存结果
                await self._set_to_cache(cache_key, file_obj)
                
                return file_obj
                
        except Exception as e:
            logger.error(f"获取文件失败: {e}")
            return None
    
    async def update(self, file_id: str, updates: Dict[str, Any], 
                    user_id: str) -> Optional[KnowledgeFile]:
        """更新文件"""
        try:
            # 权限检查
            has_permission = await self._check_file_permission(file_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有更新权限")
            
            async with await self.get_session() as session:
                file_obj = session.query(KnowledgeFile).filter(
                    KnowledgeFile.file_id == file_id
                ).first()
                
                if not file_obj:
                    return None
                
                # 更新字段
                for key, value in updates.items():
                    if hasattr(file_obj, key) and key not in ['id', 'file_id', 'created_at']:
                        setattr(file_obj, key, value)
                
                session.commit()
                session.refresh(file_obj)
                
                # 清除缓存
                await self._delete_from_cache(f"file:{file_id}")
                await self._delete_from_cache(f"kb_files:{file_obj.database_id}")
                
                logger.info(f"更新文件成功: {file_id}")
                return file_obj
                
        except Exception as e:
            logger.error(f"更新文件失败: {e}")
            raise
    
    async def delete(self, file_id: str, user_id: str) -> bool:
        """删除文件"""
        try:
            # 权限检查
            has_permission = await self._check_file_permission(file_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有删除权限")
            
            async with await self.get_session() as session:
                file_obj = session.query(KnowledgeFile).filter(
                    KnowledgeFile.file_id == file_id
                ).first()
                
                if not file_obj:
                    return False
                
                database_id = file_obj.database_id
                
                # 删除关联数据（由于设置了cascade，会自动删除）
                session.delete(file_obj)
                session.commit()
                
                # 清除缓存
                await self._delete_from_cache(f"file:{file_id}")
                await self._delete_from_cache(f"kb_files:{database_id}")
                
                logger.info(f"删除文件成功: {file_id}")
                return True
                
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            raise
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[KnowledgeFile]:
        """查找所有文件（仅超级管理员）"""
        try:
            async with await self.get_session() as session:
                files = session.query(KnowledgeFile).offset(offset).limit(limit).all()
                return files
        except Exception as e:
            logger.error(f"查找所有文件失败: {e}")
            return []
    
    async def get_files_by_database(self, database_id: str, user_id: str = None) -> List[KnowledgeFile]:
        """获取知识库下的所有文件"""
        try:
            # 权限检查
            if user_id and self.kb_repo:
                has_permission = await self.kb_repo._check_kb_permission(database_id, user_id, 'read')
                if not has_permission:
                    return []
            
            # 尝试从缓存获取
            cache_key = f"kb_files:{database_id}"
            cached_files = await self._get_from_cache(cache_key)
            if cached_files:
                return cached_files
            
            async with await self.get_session() as session:
                files = session.query(KnowledgeFile).options(
                    selectinload(KnowledgeFile.nodes)
                ).filter(KnowledgeFile.database_id == database_id).all()
                
                # 缓存结果
                await self._set_to_cache(cache_key, files, ttl=1800)  # 30分钟缓存
                
                return files
                
        except Exception as e:
            logger.error(f"获取知识库文件失败: {e}")
            return []
    
    async def get_files_by_user(self, user_id: str) -> List[KnowledgeFile]:
        """获取用户上传的所有文件"""
        try:
            # 尝试从缓存获取
            cache_key = f"user_files:{user_id}"
            cached_files = await self._get_from_cache(cache_key)
            if cached_files:
                return cached_files
            
            async with await self.get_session() as session:
                files = session.query(KnowledgeFile).filter(
                    KnowledgeFile.uploaded_by == user_id
                ).all()
                
                # 缓存结果
                await self._set_to_cache(cache_key, files, ttl=1800)
                
                return files
                
        except Exception as e:
            logger.error(f"获取用户文件失败: {e}")
            return []
    
    async def update_file_status(self, file_id: str, status: str, 
                               error_message: str = None) -> bool:
        """更新文件处理状态"""
        try:
            async with await self.get_session() as session:
                file_obj = session.query(KnowledgeFile).filter(
                    KnowledgeFile.file_id == file_id
                ).first()
                
                if not file_obj:
                    return False
                
                file_obj.status = status
                if error_message:
                    # 可以在元数据中存储错误信息
                    pass
                
                session.commit()
                
                # 清除缓存
                await self._delete_from_cache(f"file:{file_id}")
                await self._delete_from_cache(f"kb_files:{file_obj.database_id}")
                
                logger.info(f"更新文件状态成功: {file_id} -> {status}")
                return True
                
        except Exception as e:
            logger.error(f"更新文件状态失败: {e}")
            return False
    
    async def get_file_statistics(self, database_id: str = None, 
                                user_id: str = None) -> Dict[str, Any]:
        """获取文件统计信息"""
        try:
            async with await self.get_session() as session:
                query = session.query(KnowledgeFile)
                
                if database_id:
                    query = query.filter(KnowledgeFile.database_id == database_id)
                
                if user_id:
                    query = query.filter(KnowledgeFile.uploaded_by == user_id)
                
                files = query.all()
                
                # 统计信息
                total_files = len(files)
                status_stats = {}
                type_stats = {}
                
                for file_obj in files:
                    # 状态统计
                    status = file_obj.status
                    status_stats[status] = status_stats.get(status, 0) + 1
                    
                    # 类型统计
                    file_type = file_obj.file_type
                    type_stats[file_type] = type_stats.get(file_type, 0) + 1
                
                return {
                    'total_files': total_files,
                    'status_statistics': status_stats,
                    'type_statistics': type_stats,
                    'database_id': database_id,
                    'user_id': user_id
                }
                
        except Exception as e:
            logger.error(f"获取文件统计失败: {e}")
            return {
                'total_files': 0,
                'status_statistics': {},
                'type_statistics': {},
                'error': str(e)
            }
    
    async def batch_update_status(self, file_ids: List[str], status: str) -> int:
        """批量更新文件状态"""
        try:
            updated_count = 0
            async with await self.get_session() as session:
                for file_id in file_ids:
                    file_obj = session.query(KnowledgeFile).filter(
                        KnowledgeFile.file_id == file_id
                    ).first()
                    
                    if file_obj:
                        file_obj.status = status
                        updated_count += 1
                        
                        # 清除缓存
                        await self._delete_from_cache(f"file:{file_id}")
                
                session.commit()
                
                logger.info(f"批量更新文件状态成功: {updated_count}/{len(file_ids)}")
                return updated_count
                
        except Exception as e:
            logger.error(f"批量更新文件状态失败: {e}")
            return 0