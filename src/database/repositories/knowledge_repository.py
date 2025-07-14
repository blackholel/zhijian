"""
知识库数据仓储
"""

import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_

from .base import PostgreSQLRepository
from ..connection_manager import DatabaseConnectionManager
from server.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode, KnowledgeDatabasePermission
from server.models.user_model import User

logger = logging.getLogger(__name__)


class KnowledgeRepository(PostgreSQLRepository[KnowledgeDatabase]):
    """知识库数据仓储"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        super().__init__(connection_manager, 'server_db')
        self.enable_cache(ttl=3600)
    
    async def _check_kb_permission(self, kb_id: str, user_id: str, permission: str) -> bool:
        """检查用户对知识库的权限"""
        try:
            async with await self.get_session() as session:
                # 检查是否是所有者
                kb = session.query(KnowledgeDatabase).filter(
                    KnowledgeDatabase.db_id == kb_id
                ).first()
                
                if kb and str(kb.owner_id) == user_id:
                    return True
                
                # 检查是否有明确的权限
                kb_permission = session.query(KnowledgeDatabasePermission).filter(
                    and_(
                        KnowledgeDatabasePermission.database_id == kb_id,
                        KnowledgeDatabasePermission.user_id == user_id,
                        or_(
                            KnowledgeDatabasePermission.permission_type == permission,
                            KnowledgeDatabasePermission.permission_type == 'admin'
                        )
                    )
                ).first()
                
                if kb_permission:
                    # 检查权限是否过期
                    if kb_permission.expires_at and kb_permission.expires_at < datetime.now():
                        return False
                    return True
                
                # 检查是否是公开知识库
                if kb and kb.is_public and permission == 'read':
                    return True
                    
                return False
        except Exception as e:
            logger.error(f"检查权限失败: {e}")
            return False
    
    async def create(self, kb_data: Dict[str, Any], owner_id: str) -> KnowledgeDatabase:
        """创建知识库"""
        try:
            async with await self.get_session() as session:
                # 生成知识库ID
                kb_id = kb_data.get('db_id', str(uuid.uuid4()).replace('-', ''))
                
                # 创建知识库记录
                kb = KnowledgeDatabase(
                    db_id=kb_id,
                    name=kb_data['name'],
                    description=kb_data.get('description'),
                    embed_model=kb_data.get('embed_model'),
                    dimension=kb_data.get('dimension'),
                    meta_info=kb_data.get('metadata', {}),
                    owner_id=owner_id,
                    is_public=kb_data.get('is_public', False),
                    access_level=kb_data.get('access_level', 'private')
                )
                
                session.add(kb)
                session.commit()
                session.refresh(kb)
                
                # 预加载关系属性，避免Session关闭后的LazyLoading问题
                _ = kb.files  # 触发加载files关系
                _ = kb.permissions  # 触发加载permissions关系
                
                # 设置空的files列表（新创建的知识库没有文件）
                kb.files = []
                
                # 从Session中分离对象，使其独立于Session
                session.expunge(kb)
                
                # 清除相关缓存
                await self._delete_from_cache(f"user_kbs:{owner_id}")
                
                logger.info(f"创建知识库成功: {kb_id}")
                return kb
                
        except Exception as e:
            logger.error(f"创建知识库失败: {e}")
            raise
    
    async def get_by_id(self, kb_id: str, user_id: str = None, check_permission: bool = True) -> Optional[KnowledgeDatabase]:
        """根据ID获取知识库"""
        try:
            # 尝试从缓存获取
            cache_key = f"kb:{kb_id}"
            cached_kb = await self._get_from_cache(cache_key)
            
            if cached_kb:
                # 如果需要权限检查
                if check_permission and user_id:
                    has_permission = await self._check_kb_permission(kb_id, user_id, 'read')
                    if not has_permission:
                        return None
                return cached_kb
            
            async with await self.get_session() as session:
                kb = session.query(KnowledgeDatabase).options(
                    selectinload(KnowledgeDatabase.files).selectinload(KnowledgeFile.nodes),
                    selectinload(KnowledgeDatabase.permissions)
                ).filter(KnowledgeDatabase.db_id == kb_id).first()
                
                if not kb:
                    return None
                
                # 权限检查
                if check_permission and user_id:
                    has_permission = await self._check_kb_permission(kb_id, user_id, 'read')
                    if not has_permission:
                        return None
                
                # 预加载关系属性并分离对象
                _ = kb.owner_id  # 确保owner_id已加载
                _ = kb.files  # 触发加载files关系
                _ = kb.permissions  # 触发加载permissions关系
                
                # 从Session中分离对象，使其独立于Session
                session.expunge(kb)
                
                # 缓存结果
                await self._set_to_cache(cache_key, kb)
                
                return kb
                
        except Exception as e:
            logger.error(f"获取知识库失败: {e}")
            return None
    
    async def update(self, kb_id: str, updates: Dict[str, Any], user_id: str) -> Optional[KnowledgeDatabase]:
        """更新知识库"""
        try:
            # 权限检查
            has_permission = await self._check_kb_permission(kb_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有更新权限")
            
            async with await self.get_session() as session:
                kb = session.query(KnowledgeDatabase).filter(
                    KnowledgeDatabase.db_id == kb_id
                ).first()
                
                if not kb:
                    return None
                
                # 更新字段
                for key, value in updates.items():
                    if hasattr(kb, key) and key not in ['id', 'db_id', 'created_at']:
                        setattr(kb, key, value)
                
                session.commit()
                session.refresh(kb)
                
                # 预加载关系属性并分离对象
                _ = kb.owner_id  # 确保owner_id已加载
                _ = kb.files  # 触发加载files关系
                _ = kb.permissions  # 触发加载permissions关系
                
                # 从Session中分离对象，使其独立于Session
                session.expunge(kb)
                
                # 清除缓存
                await self._delete_from_cache(f"kb:{kb_id}")
                await self._delete_from_cache(f"user_kbs:{user_id}")
                
                logger.info(f"更新知识库成功: {kb_id}")
                return kb
                
        except Exception as e:
            logger.error(f"更新知识库失败: {e}")
            raise
    
    async def delete(self, kb_id: str, user_id: str) -> bool:
        """删除知识库"""
        try:
            # 权限检查
            has_permission = await self._check_kb_permission(kb_id, user_id, 'admin')
            if not has_permission:
                raise PermissionError("没有删除权限")
            
            async with await self.get_session() as session:
                kb = session.query(KnowledgeDatabase).filter(
                    KnowledgeDatabase.db_id == kb_id
                ).first()
                
                if not kb:
                    return False
                
                # 删除关联数据（由于设置了cascade，会自动删除）
                session.delete(kb)
                session.commit()
                
                # 清除缓存
                await self._delete_from_cache(f"kb:{kb_id}")
                await self._delete_from_cache(f"user_kbs:{user_id}")
                
                logger.info(f"删除知识库成功: {kb_id}")
                return True
                
        except Exception as e:
            logger.error(f"删除知识库失败: {e}")
            raise
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[KnowledgeDatabase]:
        """查找所有知识库（仅超级管理员）"""
        try:
            async with await self.get_session() as session:
                kbs = session.query(KnowledgeDatabase).options(
                    selectinload(KnowledgeDatabase.files),
                    selectinload(KnowledgeDatabase.permissions)
                ).offset(offset).limit(limit).all()
                
                # 预加载关系属性并分离对象
                for kb in kbs:
                    _ = kb.owner_id  # 确保owner_id已加载
                    _ = kb.files  # 触发加载files关系
                    _ = kb.permissions  # 触发加载permissions关系
                    session.expunge(kb)
                
                return kbs
        except Exception as e:
            logger.error(f"查找所有知识库失败: {e}")
            return []
    
    async def get_user_accessible_kbs(self, user_id: str) -> List[KnowledgeDatabase]:
        """获取用户可访问的知识库列表"""
        logger.debug(f"查询用户 {user_id} 可访问的知识库（缓存: {getattr(self, '_cache_enabled', False)}）")
        
        try:
            # 尝试从缓存获取（如果缓存启用）
            cached_kbs = None
            if getattr(self, '_cache_enabled', False):
                cache_key = f"user_kbs:{user_id}"
                try:
                    cached_kbs = await self._get_from_cache(cache_key)
                    if cached_kbs:
                        logger.debug(f"从缓存获取到 {len(cached_kbs)} 个知识库")
                        return cached_kbs
                except Exception as cache_e:
                    logger.warning(f"缓存访问失败: {cache_e}")
            
            async with await self.get_session() as session:
                # 查询用户拥有的知识库
                owned_kbs = session.query(KnowledgeDatabase).filter(
                    KnowledgeDatabase.owner_id == user_id
                ).all()
                
                # 查询用户有权限的共享知识库
                shared_kb_ids_query = session.query(KnowledgeDatabasePermission.database_id).filter(
                    and_(
                        KnowledgeDatabasePermission.user_id == user_id,
                        or_(
                            KnowledgeDatabasePermission.expires_at.is_(None),
                            KnowledgeDatabasePermission.expires_at > datetime.now()
                        )
                    )
                ).subquery()
                
                shared_kbs = session.query(KnowledgeDatabase).filter(
                    KnowledgeDatabase.db_id.in_(session.query(shared_kb_ids_query.c.database_id))
                ).all()
                
                # 查询公开知识库
                public_kbs = session.query(KnowledgeDatabase).filter(
                    KnowledgeDatabase.is_public == True
                ).all()
                
                # 合并去重，并预加载关系属性，避免会话关闭后的lazy loading问题
                all_kbs = {}
                for kb in owned_kbs + shared_kbs + public_kbs:
                    # 预加载关系属性
                    _ = kb.owner_id  # 确保owner_id已加载
                    _ = kb.files  # 触发加载files关系
                    _ = kb.permissions  # 触发加载permissions关系
                    
                    all_kbs[kb.db_id] = kb
                
                result = list(all_kbs.values())
                
                logger.debug(f"数据库查询完成: 拥有({len(owned_kbs)}) + 共享({len(shared_kbs)}) + 公开({len(public_kbs)}) = 总计{len(result)}个知识库")
                
                # 从Session中分离对象，使其独立于Session
                for kb in result:
                    session.expunge(kb)
                
                logger.debug(f"知识库对象已从Session分离")
                
                # 缓存结果（如果缓存启用）
                if getattr(self, '_cache_enabled', False):
                    try:
                        cache_key = f"user_kbs:{user_id}"
                        await self._set_to_cache(cache_key, result, ttl=1800)  # 30分钟缓存
                        logger.debug(f"知识库列表已缓存")
                    except Exception as cache_e:
                        logger.warning(f"缓存设置失败: {cache_e}")
                
                return result
                
        except Exception as e:
            logger.error(f"获取用户可访问知识库失败: {e}")
            return []
    
    async def grant_permission(self, kb_id: str, user_id: str, permission_type: str, 
                             granted_by: str, expires_at: datetime = None) -> bool:
        """授予知识库权限"""
        try:
            # 检查授权者权限
            has_admin_permission = await self._check_kb_permission(kb_id, granted_by, 'admin')
            if not has_admin_permission:
                raise PermissionError("没有授权权限")
            
            async with await self.get_session() as session:
                # 检查是否已存在权限
                existing_permission = session.query(KnowledgeDatabasePermission).filter(
                    and_(
                        KnowledgeDatabasePermission.database_id == kb_id,
                        KnowledgeDatabasePermission.user_id == user_id
                    )
                ).first()
                
                if existing_permission:
                    # 更新现有权限
                    existing_permission.permission_type = permission_type
                    existing_permission.granted_by = granted_by
                    existing_permission.granted_at = datetime.now()
                    existing_permission.expires_at = expires_at
                else:
                    # 创建新权限
                    permission = KnowledgeDatabasePermission(
                        database_id=kb_id,
                        user_id=user_id,
                        permission_type=permission_type,
                        granted_by=granted_by,
                        expires_at=expires_at
                    )
                    session.add(permission)
                
                session.commit()
                
                # 清除相关缓存
                await self._delete_from_cache(f"user_kbs:{user_id}")
                
                logger.info(f"授予知识库权限成功: {kb_id} -> {user_id} ({permission_type})")
                return True
                
        except Exception as e:
            logger.error(f"授予知识库权限失败: {e}")
            raise
    
    async def revoke_permission(self, kb_id: str, user_id: str, revoked_by: str) -> bool:
        """撤销知识库权限"""
        try:
            # 检查撤销者权限
            has_admin_permission = await self._check_kb_permission(kb_id, revoked_by, 'admin')
            if not has_admin_permission:
                raise PermissionError("没有撤销权限")
            
            async with await self.get_session() as session:
                permission = session.query(KnowledgeDatabasePermission).filter(
                    and_(
                        KnowledgeDatabasePermission.database_id == kb_id,
                        KnowledgeDatabasePermission.user_id == user_id
                    )
                ).first()
                
                if permission:
                    session.delete(permission)
                    session.commit()
                    
                    # 清除相关缓存
                    await self._delete_from_cache(f"user_kbs:{user_id}")
                    
                    logger.info(f"撤销知识库权限成功: {kb_id} -> {user_id}")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"撤销知识库权限失败: {e}")
            raise