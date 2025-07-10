"""权限服务层"""
from typing import Optional, List, Dict, Any, Set
from sqlalchemy.orm import Session
from sqlalchemy import and_

from server.auth.models.user_models import Permission, RolePermission, UserRole


class PermissionService:
    """权限管理服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def get_permission_by_id(self, permission_id: str) -> Optional[Permission]:
        """根据ID获取权限"""
        return self.db.query(Permission).filter(Permission.id == permission_id).first()
    
    async def get_permission_by_name(self, permission_name: str) -> Optional[Permission]:
        """根据名称获取权限"""
        return self.db.query(Permission).filter(Permission.name == permission_name).first()
    
    async def create_permission(self, permission_data: Dict[str, Any]) -> Permission:
        """创建权限"""
        permission = Permission(**permission_data)
        self.db.add(permission)
        self.db.commit()
        self.db.refresh(permission)
        return permission
    
    async def update_permission(self, permission_id: str, update_data: Dict[str, Any]) -> Optional[Permission]:
        """更新权限"""
        permission = await self.get_permission_by_id(permission_id)
        if not permission:
            return None
        
        for key, value in update_data.items():
            if hasattr(permission, key):
                setattr(permission, key, value)
        
        self.db.commit()
        self.db.refresh(permission)
        return permission
    
    async def delete_permission(self, permission_id: str) -> bool:
        """删除权限"""
        permission = await self.get_permission_by_id(permission_id)
        if not permission:
            return False
        
        # 检查是否有角色使用该权限
        role_count = self.db.query(RolePermission).filter(
            RolePermission.permission_id == permission_id
        ).count()
        
        if role_count > 0:
            return False
        
        self.db.delete(permission)
        self.db.commit()
        return True
    
    async def assign_role_permission(self, role_id: str, permission_id: str) -> bool:
        """为角色分配权限"""
        # 检查是否已经分配
        existing = self.db.query(RolePermission).filter(
            and_(RolePermission.role_id == role_id, RolePermission.permission_id == permission_id)
        ).first()
        
        if existing:
            return False
        
        role_permission = RolePermission(
            role_id=role_id,
            permission_id=permission_id
        )
        
        self.db.add(role_permission)
        self.db.commit()
        return True
    
    async def revoke_role_permission(self, role_id: str, permission_id: str) -> bool:
        """撤销角色权限"""
        role_permission = self.db.query(RolePermission).filter(
            and_(RolePermission.role_id == role_id, RolePermission.permission_id == permission_id)
        ).first()
        
        if not role_permission:
            return False
        
        self.db.delete(role_permission)
        self.db.commit()
        return True
    
    async def get_user_permissions(self, user_id: str) -> Set[str]:
        """获取用户的所有权限"""
        # 通过用户角色获取权限
        from sqlalchemy import text
        
        query = text("""
            SELECT DISTINCT p.name
            FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            JOIN roles r ON rp.role_id = r.id
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = :user_id
            AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
        """)
        
        result = self.db.execute(query, {"user_id": user_id})
        return {row[0] for row in result}
    
    async def check_user_permission(self, user_id: str, permission_name: str) -> bool:
        """检查用户是否有特定权限"""
        user_permissions = await self.get_user_permissions(user_id)
        return permission_name in user_permissions
    
    async def search_permissions(self, search_term: str, resource_type: str = None, 
                               action: str = None, skip: int = 0, limit: int = 100) -> List[Permission]:
        """搜索权限"""
        query = self.db.query(Permission)
        
        if search_term:
            query = query.filter(
                (Permission.name.ilike(f"%{search_term}%")) |
                (Permission.display_name.ilike(f"%{search_term}%"))
            )
        
        if resource_type:
            query = query.filter(Permission.resource_type == resource_type)
        
        if action:
            query = query.filter(Permission.action == action)
        
        return query.offset(skip).limit(limit).all()