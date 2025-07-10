"""用户服务层"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.auth.models.user_models import User, UserRole
from src.database.repositories.user_repository import UserRepository


class UserService:
    """用户管理服务"""
    
    def __init__(self, db: Session, user_repository: UserRepository):
        self.db = db
        self.user_repository = user_repository
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据ID获取用户"""
        return self.db.query(User).filter(User.id == user_id).first()
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return self.db.query(User).filter(User.username == username).first()
    
    async def get_user_by_external_id(self, external_user_id: str) -> Optional[User]:
        """根据外部用户ID获取用户"""
        return self.db.query(User).filter(User.external_user_id == external_user_id).first()
    
    async def create_user(self, user_data: Dict[str, Any]) -> User:
        """创建用户"""
        user = User(**user_data)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    async def update_user(self, user_id: str, update_data: Dict[str, Any]) -> Optional[User]:
        """更新用户信息"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        for key, value in update_data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        self.db.commit()
        self.db.refresh(user)
        return user
    
    async def deactivate_user(self, user_id: str) -> bool:
        """停用用户"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = False
        self.db.commit()
        return True
    
    async def get_user_roles(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户角色"""
        user_roles = self.db.query(UserRole).filter(
            and_(
                UserRole.user_id == user_id,
                UserRole.expires_at.is_(None) | (UserRole.expires_at > self.db.now())
            )
        ).all()
        
        return [ur.to_dict() for ur in user_roles]
    
    async def search_users(self, search_term: str, skip: int = 0, limit: int = 100) -> List[User]:
        """搜索用户"""
        query = self.db.query(User).filter(
            (User.username.ilike(f"%{search_term}%")) |
            (User.display_name.ilike(f"%{search_term}%")) |
            (User.email.ilike(f"%{search_term}%"))
        )
        
        return query.offset(skip).limit(limit).all()