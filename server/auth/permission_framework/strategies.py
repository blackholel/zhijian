"""
权限策略实现
包含各种权限检查策略
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from .core import PermissionContext, PermissionResult, Permission, ResourceType
from server.models.user_model import User
from server.db_manager import db_manager

logger = logging.getLogger(__name__)

class PermissionStrategy(ABC):
    """权限策略抽象基类"""
    
    @abstractmethod
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        """检查权限"""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass
    
    @abstractmethod
    def get_priority(self) -> int:
        """获取策略优先级（数字越小优先级越高）"""
        pass
    
    def is_applicable(self, context: PermissionContext) -> bool:
        """检查策略是否适用于当前上下文"""
        return True
    
    async def _get_user(self, user_id: str) -> Optional[User]:
        """获取用户对象"""
        db = db_manager.get_session()
        try:
            # 先尝试按external_user_id查找（外部JWT用户）
            user = db.query(User).filter(User.external_user_id == user_id).first()
            if user:
                return user
            
            # 再尝试按UUID查找（内部用户）
            try:
                # 检查是否为有效的UUID格式
                import uuid
                uuid.UUID(user_id)
                return db.query(User).filter(User.id == user_id).first()
            except ValueError:
                # 不是UUID格式，可能是用户名
                return db.query(User).filter(User.username == user_id).first()
        finally:
            db.close()
    
    def _get_db(self) -> Session:
        """获取数据库会话"""
        return db_manager.get_session()

class SuperAdminStrategy(PermissionStrategy):
    """超级管理员策略"""
    
    def __init__(self, rbac_middleware):
        self.rbac = rbac_middleware
    
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        user = await self._get_user(context.user_id)
        if user:
            db = self._get_db()
            try:
                if await self.rbac.verify_permission(user, "*:*", db):
                    return PermissionResult(True, "SuperAdmin privileges", "SuperAdminStrategy")
            finally:
                db.close()
        return PermissionResult(False, "Not a super admin", "SuperAdminStrategy")
    
    def get_strategy_name(self) -> str:
        return "SuperAdminStrategy"
    
    def get_priority(self) -> int:
        return 1  # 最高优先级

class OwnershipStrategy(PermissionStrategy):
    """所有者策略"""
    
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        if context.resource:
            owner_id = await context.resource.get_owner()
            if owner_id == context.user_id:
                return PermissionResult(True, "Resource owner", "OwnershipStrategy")
        return PermissionResult(False, "Not resource owner", "OwnershipStrategy")
    
    def get_strategy_name(self) -> str:
        return "OwnershipStrategy"
    
    def get_priority(self) -> int:
        return 2

class PublicResourceStrategy(PermissionStrategy):
    """公开资源策略"""
    
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        if context.permission == Permission.READ and context.resource:
            if await context.resource.is_public():
                return PermissionResult(True, "Public resource read access", "PublicResourceStrategy")
        return PermissionResult(False, "Not public or not read access", "PublicResourceStrategy")
    
    def get_strategy_name(self) -> str:
        return "PublicResourceStrategy"
    
    def get_priority(self) -> int:
        return 3

class SystemPermissionStrategy(PermissionStrategy):
    """系统级权限策略"""
    
    def __init__(self, rbac_middleware):
        self.rbac = rbac_middleware
    
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        # 构建系统级权限字符串
        if context.resource:
            system_permission = f"{context.resource.resource_type.value}:{context.permission.value}"
        else:
            system_permission = f"system:{context.permission.value}"
        
        user = await self._get_user(context.user_id)
        if user:
            db = self._get_db()
            try:
                if await self.rbac.verify_permission(user, system_permission, db):
                    return PermissionResult(True, f"System permission: {system_permission}", "SystemPermissionStrategy")
            finally:
                db.close()
        
        return PermissionResult(False, f"No system permission: {system_permission}", "SystemPermissionStrategy")
    
    def get_strategy_name(self) -> str:
        return "SystemPermissionStrategy"
    
    def get_priority(self) -> int:
        return 4

class ResourcePermissionStrategy(PermissionStrategy):
    """资源级权限策略"""
    
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        if not context.resource:
            return PermissionResult(False, "No resource specified", "ResourcePermissionStrategy")
        
        # 检查特定资源的权限
        db = self._get_db()
        try:
            # 根据资源类型查询相应的权限表
            if context.resource.resource_type == ResourceType.KNOWLEDGE_BASE:
                result = db.execute(text("""
                    SELECT permission_type FROM knowledge_database_permissions 
                    WHERE database_id = :resource_id AND user_id = :user_id
                    AND (expires_at IS NULL OR expires_at > NOW())
                """), {
                    "resource_id": context.resource.resource_id,
                    "user_id": context.user_id
                }).fetchall()
                
                permissions = [row[0] for row in result]
                if self._check_permission_hierarchy(context.permission.value, permissions):
                    return PermissionResult(True, f"Resource permission granted", "ResourcePermissionStrategy")
        except Exception as e:
            logger.error(f"Error checking resource permission: {e}")
        finally:
            db.close()
        
        return PermissionResult(False, "No resource permission", "ResourcePermissionStrategy")
    
    def _check_permission_hierarchy(self, required: str, granted: List[str]) -> bool:
        """检查权限层级关系"""
        hierarchy = {
            "read": ["read", "write", "admin"],
            "write": ["write", "admin"],
            "admin": ["admin"],
            "execute": ["execute", "admin"],
            "create": ["create", "write", "admin"],
            "update": ["update", "write", "admin"],
            "delete": ["delete", "admin"],
            "share": ["share", "admin"]
        }
        return any(perm in granted for perm in hierarchy.get(required, [required]))
    
    def get_strategy_name(self) -> str:
        return "ResourcePermissionStrategy"
    
    def get_priority(self) -> int:
        return 5

class InheritanceStrategy(PermissionStrategy):
    """继承权限策略"""
    
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        if not context.resource or not context.resource.parent:
            return PermissionResult(False, "No parent resource", "InheritanceStrategy")
        
        # 检查父资源的权限
        parent = context.resource.parent
        parent_context = PermissionContext(
            user_id=context.user_id,
            resource=parent,
            permission=context.permission,
            request_metadata=context.request_metadata,
            timestamp=context.timestamp
        )
        
        # 避免无限递归，这里需要引用引擎实例
        from .engine import PermissionEngine
        engine = PermissionEngine.get_instance()
        parent_result = await engine.check_permission(parent_context, skip_inheritance=True)
        
        if parent_result.allowed:
            return PermissionResult(True, f"Inherited from parent: {parent.uri}", "InheritanceStrategy")
        
        return PermissionResult(False, "No inherited permission", "InheritanceStrategy")
    
    def get_strategy_name(self) -> str:
        return "InheritanceStrategy"
    
    def get_priority(self) -> int:
        return 6

class DenyAllStrategy(PermissionStrategy):
    """拒绝所有策略（兜底策略）"""
    
    async def check_permission(self, context: PermissionContext) -> PermissionResult:
        return PermissionResult(False, "Default deny", "DenyAllStrategy")
    
    def get_strategy_name(self) -> str:
        return "DenyAllStrategy"
    
    def get_priority(self) -> int:
        return 999  # 最低优先级