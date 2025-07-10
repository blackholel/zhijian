from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

class User(Base):
    """用户模型"""
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_user_id = Column(String(255), unique=True, nullable=False, index=True)  # 外部用户ID
    username = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)
    organization = Column(String(255), nullable=True)
    region = Column(String(10), nullable=True)
    login_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    password_hash = Column(String, nullable=True)  # 外部用户可能没有密码
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_login = Column(DateTime, nullable=True)

    # 关联操作日志
    operation_logs = relationship("OperationLog", back_populates="user")
    # 关联用户角色
    user_roles = relationship("UserRole", back_populates="user", foreign_keys="UserRole.user_id")

    def to_dict(self, include_password=False):
        result = {
            "id": str(self.id),
            "external_user_id": self.external_user_id,
            "username": self.username,
            "display_name": self.display_name,
            "organization": self.organization,
            "region": self.region,
            "login_name": self.login_name,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }
        if include_password:
            result["password_hash"] = self.password_hash
        return result

class Role(Base):
    """角色模型"""
    __tablename__ = 'roles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, default=False)  # 系统角色不可删除
    created_at = Column(DateTime, default=func.now())

    # 关联
    user_roles = relationship("UserRole", back_populates="role")
    role_permissions = relationship("RolePermission", back_populates="role")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Permission(Base):
    """权限模型"""
    __tablename__ = 'permissions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)  # 如: user:read, kb:write
    display_name = Column(String(255), nullable=True)
    resource_type = Column(String(50), nullable=False)  # 资源类型
    action = Column(String(50), nullable=False)  # 操作类型
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # 关联
    role_permissions = relationship("RolePermission", back_populates="permission")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "display_name": self.display_name,
            "resource_type": self.resource_type,
            "action": self.action,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class UserRole(Base):
    """用户角色关联模型"""
    __tablename__ = 'user_roles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    granted_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    granted_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)

    # 关联
    user = relationship("User", back_populates="user_roles", foreign_keys=[user_id])
    role = relationship("Role", back_populates="user_roles")
    granter = relationship("User", foreign_keys=[granted_by], post_update=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "role_id": str(self.role_id),
            "granted_by": str(self.granted_by) if self.granted_by else None,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }


class RolePermission(Base):
    """角色权限关联模型"""
    __tablename__ = 'role_permissions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey('permissions.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # 关联
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")

    def to_dict(self):
        return {
            "id": str(self.id),
            "role_id": str(self.role_id),
            "permission_id": str(self.permission_id),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class UserPermissionCache(Base):
    """用户权限缓存模型"""
    __tablename__ = 'user_permission_cache'

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    permissions = Column(JSON, nullable=False)
    last_updated = Column(DateTime, default=func.now())

    # 关联
    user = relationship("User")

    def to_dict(self):
        return {
            "user_id": str(self.user_id),
            "permissions": self.permissions,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None
        }


class OperationLog(Base):
    """操作日志模型"""
    __tablename__ = 'operation_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    operation = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now())

    # 关联用户
    user = relationship("User", back_populates="operation_logs")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "operation": self.operation,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }