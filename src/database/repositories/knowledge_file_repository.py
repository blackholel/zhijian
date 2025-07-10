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
from server.auth.models.user_models import User

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
    
    def _preload_and_detach_file(self, session: Session, file_obj: KnowledgeFile) -> KnowledgeFile:
        """预加载所有必要属性并分离对象，避免Session关闭后的LazyLoading问题"""
        # 预加载所有必要属性
        _ = file_obj.file_id
        _ = file_obj.filename
        _ = file_obj.path
        _ = file_obj.file_type
        _ = file_obj.status
        _ = file_obj.storage_type
        _ = file_obj.file_size
        _ = file_obj.file_metadata
        _ = file_obj.created_at
        _ = file_obj.uploaded_by
        _ = file_obj.database_id
        _ = file_obj.nodes  # 通过selectinload预加载
        
        # 从Session中分离对象，使其独立于Session
        session.expunge(file_obj)
        return file_obj

    async def _set_file_cache(self, key: str, files: List[KnowledgeFile], ttl: int = 1800) -> bool:
        """设置文件缓存，只缓存基本信息避免复杂对象序列化"""
        try:
            cached_data = []
            for file_obj in files:
                # 只缓存基本属性，避免复杂对象序列化和依赖关系
                file_dict = {
                    "file_id": getattr(file_obj, 'file_id', None),
                    "filename": getattr(file_obj, 'filename', None),
                    "path": getattr(file_obj, 'path', None),
                    "file_type": getattr(file_obj, 'file_type', None),
                    "status": getattr(file_obj, 'status', 'unknown'),
                    "storage_type": getattr(file_obj, 'storage_type', 'local'),
                    "file_size": getattr(file_obj, 'file_size', None),
                    "file_metadata": getattr(file_obj, 'file_metadata', None) or {},
                    "created_at": getattr(file_obj, 'created_at', None),
                    "uploaded_by": getattr(file_obj, 'uploaded_by', None),
                    "database_id": getattr(file_obj, 'database_id', None),
                    # 预计算节点数量，避免运行时依赖关系
                    "node_count": len(getattr(file_obj, 'nodes', []))
                }
                cached_data.append(file_dict)
            
            return await self._set_to_cache(key, cached_data, ttl)
        except Exception as e:
            logger.warning(f"Set file cache failed for key {key}: {e}")
            return False

    async def _get_file_cache(self, key: str) -> Optional[List[KnowledgeFile]]:
        """从缓存获取文件列表，增强验证逻辑确保对象安全重建"""
        try:
            cached_data = await self._get_from_cache(key)
            if not cached_data or not isinstance(cached_data, list):
                return None
            
            files = []
            # 定义安全的基本属性列表
            safe_attrs = [
                'file_id', 'filename', 'path', 'file_type', 'status', 
                'storage_type', 'file_size', 'file_metadata', 'created_at', 
                'uploaded_by', 'database_id', 'node_count'
            ]
            
            for file_dict in cached_data:
                # 类型检查：确保是字典格式
                if not isinstance(file_dict, dict):
                    logger.warning(f"Invalid cached file data type: {type(file_dict)}")
                    continue
                
                # 创建安全的KnowledgeFile对象
                file_obj = KnowledgeFile()
                
                # 安全地设置基本属性
                for attr in safe_attrs:
                    if attr in file_dict:
                        try:
                            # 特殊处理某些属性
                            if attr == 'file_metadata':
                                # 确保metadata是字典格式
                                value = file_dict[attr] if isinstance(file_dict[attr], dict) else {}
                            elif attr == 'node_count':
                                # 跳过node_count，使用预计算值
                                continue
                            else:
                                value = file_dict[attr]
                            
                            setattr(file_obj, attr, value)
                        except (AttributeError, TypeError) as e:
                            logger.warning(f"Failed to set attribute {attr}: {e}")
                            # 设置安全的默认值
                            if attr == 'status':
                                setattr(file_obj, attr, 'unknown')
                            elif attr == 'storage_type':
                                setattr(file_obj, attr, 'local')
                            elif attr == 'file_metadata':
                                setattr(file_obj, attr, {})
                
                # 设置安全的nodes属性（空列表，避免依赖关系）
                file_obj.nodes = []
                
                # 手动设置预计算的node_count，覆盖computed_node_count
                if 'node_count' in file_dict:
                    file_obj._cached_node_count = file_dict['node_count']
                else:
                    file_obj._cached_node_count = 0
                
                files.append(file_obj)
            
            return files
        except Exception as e:
            logger.warning(f"Get file cache failed for key {key}: {e}")
            return None

    async def _set_single_file_cache(self, key: str, file_obj: KnowledgeFile, ttl: int = 1800) -> bool:
        """设置单个文件缓存，只缓存基本信息"""
        try:
            # 只缓存基本属性，避免复杂对象序列化
            file_dict = {
                "file_id": getattr(file_obj, 'file_id', None),
                "filename": getattr(file_obj, 'filename', None),
                "path": getattr(file_obj, 'path', None),
                "file_type": getattr(file_obj, 'file_type', None),
                "status": getattr(file_obj, 'status', 'unknown'),
                "storage_type": getattr(file_obj, 'storage_type', 'local'),
                "file_size": getattr(file_obj, 'file_size', None),
                "file_metadata": getattr(file_obj, 'file_metadata', None) or {},
                # 将created_at转换为timestamp便于缓存和恢复
                "created_at": getattr(file_obj, 'created_at', None).timestamp() if getattr(file_obj, 'created_at', None) else None,
                "uploaded_by": getattr(file_obj, 'uploaded_by', None),
                "database_id": getattr(file_obj, 'database_id', None),
                # 预计算节点数量
                "node_count": len(getattr(file_obj, 'nodes', []))
            }
            return await self._set_to_cache(key, file_dict, ttl)
        except Exception as e:
            logger.warning(f"Set single file cache failed for key {key}: {e}")
            return False

    async def _get_single_file_cache(self, key: str) -> Optional[KnowledgeFile]:
        """从缓存获取单个文件，增强验证逻辑"""
        try:
            cached_data = await self._get_from_cache(key)
            if not cached_data or not isinstance(cached_data, dict):
                return None
            
            # 创建安全的KnowledgeFile对象
            file_obj = KnowledgeFile()
            
            # 定义安全的基本属性列表
            safe_attrs = [
                'file_id', 'filename', 'path', 'file_type', 'status', 
                'storage_type', 'file_size', 'file_metadata', 'created_at', 
                'uploaded_by', 'database_id'
            ]
            
            # 安全地设置基本属性
            for attr in safe_attrs:
                if attr in cached_data:
                    try:
                        # 特殊处理metadata
                        if attr == 'file_metadata':
                            value = cached_data[attr] if isinstance(cached_data[attr], dict) else {}
                        else:
                            value = cached_data[attr]
                        
                        setattr(file_obj, attr, value)
                    except (AttributeError, TypeError) as e:
                        logger.warning(f"Failed to set single file attribute {attr}: {e}")
                        # 设置安全的默认值
                        if attr == 'status':
                            setattr(file_obj, attr, 'unknown')
                        elif attr == 'storage_type':
                            setattr(file_obj, attr, 'local')
                        elif attr == 'file_metadata':
                            setattr(file_obj, attr, {})
            
            # 设置安全的nodes属性（空列表）
            file_obj.nodes = []
            
            # 设置预计算的node_count
            if 'node_count' in cached_data:
                file_obj._cached_node_count = cached_data['node_count']
            else:
                file_obj._cached_node_count = 0
            
            return file_obj
        except Exception as e:
            logger.warning(f"Get single file cache failed for key {key}: {e}")
            return None

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
                    storage_type=file_data.get('storage_type', 'local'),
                    file_size=file_data.get('file_size'),
                    file_metadata=file_data.get('metadata'),
                    uploaded_by=uploaded_by
                )
                
                session.add(file_obj)
                session.commit()
                session.refresh(file_obj)
                
                # 预加载所有必要属性并分离对象
                file_obj = self._preload_and_detach_file(session, file_obj)
                
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
            # 尝试从缓存获取（使用优化的缓存策略）
            cache_key = f"file:{file_id}"
            cached_file = await self._get_single_file_cache(cache_key)
            
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
                
                # 预加载所有必要属性并分离对象
                file_obj = self._preload_and_detach_file(session, file_obj)
                
                # 缓存结果（使用优化的缓存策略）
                await self._set_single_file_cache(cache_key, file_obj)
                
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
                files = session.query(KnowledgeFile).options(
                    selectinload(KnowledgeFile.nodes)
                ).offset(offset).limit(limit).all()
                
                # 预加载所有属性并分离对象
                detached_files = []
                for file_obj in files:
                    detached_file = self._preload_and_detach_file(session, file_obj)
                    detached_files.append(detached_file)
                
                return detached_files
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
            
            # 尝试从缓存获取（使用优化的缓存策略）
            cache_key = f"kb_files:{database_id}"
            cached_files = await self._get_file_cache(cache_key)
            if cached_files:
                return cached_files
            
            async with await self.get_session() as session:
                files = session.query(KnowledgeFile).options(
                    selectinload(KnowledgeFile.nodes)
                ).filter(KnowledgeFile.database_id == database_id).all()
                
                # 预加载所有属性并分离对象
                detached_files = []
                for file_obj in files:
                    detached_file = self._preload_and_detach_file(session, file_obj)
                    detached_files.append(detached_file)
                
                # 缓存结果（使用优化的缓存策略）
                await self._set_file_cache(cache_key, detached_files, ttl=1800)  # 30分钟缓存
                
                return detached_files
                
        except Exception as e:
            logger.error(f"获取知识库文件失败: {e}")
            return []
    
    async def get_files_by_user(self, user_id: str) -> List[KnowledgeFile]:
        """获取用户上传的所有文件"""
        try:
            # 尝试从缓存获取（使用优化的缓存策略）
            cache_key = f"user_files:{user_id}"
            cached_files = await self._get_file_cache(cache_key)
            if cached_files:
                return cached_files
            
            async with await self.get_session() as session:
                files = session.query(KnowledgeFile).options(
                    selectinload(KnowledgeFile.nodes)
                ).filter(KnowledgeFile.uploaded_by == user_id).all()
                
                # 预加载所有属性并分离对象
                detached_files = []
                for file_obj in files:
                    detached_file = self._preload_and_detach_file(session, file_obj)
                    detached_files.append(detached_file)
                
                # 缓存结果（使用优化的缓存策略）
                await self._set_file_cache(cache_key, detached_files, ttl=1800)
                
                return detached_files
                
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