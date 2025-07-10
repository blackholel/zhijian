"""角色服务层"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from server.auth.models.user_models import Role, UserRole, RolePermission


class RoleService:
    """角色管理服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def get_role_by_id(self, role_id: str) -> Optional[Role]:
        """根据ID获取角色"""
        return self.db.query(Role).filter(Role.id == role_id).first()
    
    async def get_role_by_name(self, role_name: str) -> Optional[Role]:
        """根据名称获取角色"""
        return self.db.query(Role).filter(Role.name == role_name).first()
    
    async def create_role(self, role_data: Dict[str, Any]) -> Role:
        """创建角色"""
        role = Role(**role_data)
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role
    
    async def update_role(self, role_id: str, update_data: Dict[str, Any]) -> Optional[Role]:
        """更新角色"""
        role = await self.get_role_by_id(role_id)
        if not role:
            return None
        
        for key, value in update_data.items():
            if hasattr(role, key):
                setattr(role, key, value)
        
        self.db.commit()
        self.db.refresh(role)
        return role
    
    async def delete_role(self, role_id: str) -> bool:
        """删除角色"""
        role = await self.get_role_by_id(role_id)
        if not role or role.is_system:
            return False
        
        # 检查是否有用户使用该角色
        user_count = self.db.query(UserRole).filter(UserRole.role_id == role_id).count()
        if user_count > 0:
            return False
        
        self.db.delete(role)
        self.db.commit()
        return True
    
    async def assign_user_role(self, user_id: str, role_id: str, granted_by: str, expires_at=None) -> bool:
        """为用户分配角色"""
        # 检查是否已经分配
        existing = self.db.query(UserRole).filter(
            and_(UserRole.user_id == user_id, UserRole.role_id == role_id)
        ).first()
        
        if existing:
            return False
        
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            granted_by=granted_by,
            expires_at=expires_at
        )
        
        self.db.add(user_role)
        self.db.commit()
        return True
    
    async def revoke_user_role(self, user_id: str, role_id: str) -> bool:
        """撤销用户角色"""
        user_role = self.db.query(UserRole).filter(
            and_(UserRole.user_id == user_id, UserRole.role_id == role_id)
        ).first()
        
        if not user_role:
            return False
        
        self.db.delete(user_role)
        self.db.commit()
        return True
    
    async def get_role_permissions(self, role_id: str) -> List[Dict[str, Any]]:
        """获取角色权限"""
        role_permissions = self.db.query(RolePermission).filter(
            RolePermission.role_id == role_id
        ).all()
        
        return [rp.to_dict() for rp in role_permissions]
    
    async def search_roles(self, search_term: str, skip: int = 0, limit: int = 100) -> List[Role]:
        """搜索角色"""
        query = self.db.query(Role).filter(
            (Role.name.ilike(f"%{search_term}%")) |
            (Role.display_name.ilike(f"%{search_term}%"))
        )
        
        return query.offset(skip).limit(limit).all()