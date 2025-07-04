from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import logging

from server.db_manager import db_manager
from server.models.user_model import User, Role, Permission, UserRole, RolePermission
from server.utils.rbac_middleware import get_required_user, require_permission, rbac_middleware
from server.utils.redis_manager import get_permission_cache
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rbac", tags=["权限管理"])

# 获取数据库会话
def get_db():
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()

# Pydantic模型
class RoleCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None

class RoleUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None

class PermissionCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    resource_type: str
    action: str
    description: Optional[str] = None

class UserRoleAssign(BaseModel):
    user_id: str
    role_id: str
    expires_at: Optional[datetime] = None

class RolePermissionAssign(BaseModel):
    role_id: str
    permission_id: str

class UserPermissionResponse(BaseModel):
    user_id: str
    username: str
    permissions: List[str]
    roles: List[Dict[str, Any]]

# 角色管理
@router.get("/roles", summary="获取角色列表")
async def list_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    current_user: User = Depends(require_permission("role:read")),
    db: Session = Depends(get_db)
):
    """获取角色列表"""
    try:
        query = db.query(Role)
        
        if search:
            query = query.filter(
                or_(
                    Role.name.ilike(f"%{search}%"),
                    Role.display_name.ilike(f"%{search}%")
                )
            )
        
        total = query.count()
        roles = query.offset(skip).limit(limit).all()
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "roles": [role.to_dict() for role in roles]
        }
        
    except Exception as e:
        logger.error(f"Error listing roles: {e}")
        raise HTTPException(status_code=500, detail="获取角色列表失败")

@router.post("/roles", summary="创建角色")
async def create_role(
    role_data: RoleCreate,
    current_user: User = Depends(require_permission("role:create")),
    db: Session = Depends(get_db)
):
    """创建新角色"""
    try:
        # 检查角色名是否已存在
        existing_role = db.query(Role).filter(Role.name == role_data.name).first()
        if existing_role:
            raise HTTPException(status_code=400, detail="角色名已存在")
        
        # 创建角色
        role = Role(
            name=role_data.name,
            display_name=role_data.display_name,
            description=role_data.description,
            is_system=False
        )
        
        db.add(role)
        db.commit()
        db.refresh(role)
        
        logger.info(f"Role created: {role.name} by {current_user.username}")
        return role.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating role: {e}")
        raise HTTPException(status_code=500, detail="创建角色失败")

@router.put("/roles/{role_id}", summary="更新角色")
async def update_role(
    role_id: str,
    role_data: RoleUpdate,
    current_user: User = Depends(require_permission("role:update")),
    db: Session = Depends(get_db)
):
    """更新角色信息"""
    try:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        if role.is_system:
            raise HTTPException(status_code=400, detail="系统角色不能修改")
        
        # 更新角色信息
        if role_data.display_name is not None:
            role.display_name = role_data.display_name
        if role_data.description is not None:
            role.description = role_data.description
        
        db.commit()
        db.refresh(role)
        
        logger.info(f"Role updated: {role.name} by {current_user.username}")
        return role.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating role: {e}")
        raise HTTPException(status_code=500, detail="更新角色失败")

@router.delete("/roles/{role_id}", summary="删除角色")
async def delete_role(
    role_id: str,
    current_user: User = Depends(require_permission("role:delete")),
    db: Session = Depends(get_db)
):
    """删除角色"""
    try:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        if role.is_system:
            raise HTTPException(status_code=400, detail="系统角色不能删除")
        
        # 检查是否有用户使用该角色
        user_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()
        if user_count > 0:
            raise HTTPException(status_code=400, detail=f"该角色被{user_count}个用户使用，无法删除")
        
        db.delete(role)
        db.commit()
        
        logger.info(f"Role deleted: {role.name} by {current_user.username}")
        return {"message": "角色删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting role: {e}")
        raise HTTPException(status_code=500, detail="删除角色失败")

# 权限管理
@router.get("/permissions", summary="获取权限列表")
async def list_permissions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_permission("permission:read")),
    db: Session = Depends(get_db)
):
    """获取权限列表"""
    try:
        query = db.query(Permission)
        
        if resource_type:
            query = query.filter(Permission.resource_type == resource_type)
        
        if action:
            query = query.filter(Permission.action == action)
        
        if search:
            query = query.filter(
                or_(
                    Permission.name.ilike(f"%{search}%"),
                    Permission.display_name.ilike(f"%{search}%")
                )
            )
        
        total = query.count()
        permissions = query.offset(skip).limit(limit).all()
        
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "permissions": [perm.to_dict() for perm in permissions]
        }
        
    except Exception as e:
        logger.error(f"Error listing permissions: {e}")
        raise HTTPException(status_code=500, detail="获取权限列表失败")

@router.post("/permissions", summary="创建权限")
async def create_permission(
    permission_data: PermissionCreate,
    current_user: User = Depends(require_permission("permission:create")),
    db: Session = Depends(get_db)
):
    """创建新权限"""
    try:
        # 检查权限名是否已存在
        existing_permission = db.query(Permission).filter(
            Permission.name == permission_data.name
        ).first()
        if existing_permission:
            raise HTTPException(status_code=400, detail="权限名已存在")
        
        # 创建权限
        permission = Permission(
            name=permission_data.name,
            display_name=permission_data.display_name,
            resource_type=permission_data.resource_type,
            action=permission_data.action,
            description=permission_data.description
        )
        
        db.add(permission)
        db.commit()
        db.refresh(permission)
        
        logger.info(f"Permission created: {permission.name} by {current_user.username}")
        return permission.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating permission: {e}")
        raise HTTPException(status_code=500, detail="创建权限失败")

# 用户角色管理
@router.post("/user-roles", summary="为用户分配角色")
async def assign_user_role(
    assignment: UserRoleAssign,
    current_user: User = Depends(require_permission("user:grant_role")),
    db: Session = Depends(get_db)
):
    """为用户分配角色"""
    try:
        # 验证用户和角色存在
        user = db.query(User).filter(User.id == assignment.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        role = db.query(Role).filter(Role.id == assignment.role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        # 检查是否已经分配
        existing_assignment = db.query(UserRole).filter(
            and_(
                UserRole.user_id == assignment.user_id,
                UserRole.role_id == assignment.role_id
            )
        ).first()
        
        if existing_assignment:
            raise HTTPException(status_code=400, detail="用户已拥有该角色")
        
        # 创建角色分配
        user_role = UserRole(
            user_id=assignment.user_id,
            role_id=assignment.role_id,
            granted_by=current_user.id,
            expires_at=assignment.expires_at
        )
        
        db.add(user_role)
        db.commit()
        
        # 清除用户权限缓存
        rbac_middleware.invalidate_user_cache(assignment.user_id)
        
        logger.info(f"Role {role.name} assigned to user {user.username} by {current_user.username}")
        return {"message": "角色分配成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning user role: {e}")
        raise HTTPException(status_code=500, detail="分配角色失败")

@router.delete("/user-roles/{user_id}/{role_id}", summary="撤销用户角色")
async def revoke_user_role(
    user_id: str,
    role_id: str,
    current_user: User = Depends(require_permission("user:revoke_role")),
    db: Session = Depends(get_db)
):
    """撤销用户角色"""
    try:
        user_role = db.query(UserRole).filter(
            and_(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id
            )
        ).first()
        
        if not user_role:
            raise HTTPException(status_code=404, detail="用户角色分配不存在")
        
        db.delete(user_role)
        db.commit()
        
        # 清除用户权限缓存
        rbac_middleware.invalidate_user_cache(user_id)
        
        logger.info(f"Role revoked from user {user_id} by {current_user.username}")
        return {"message": "角色撤销成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error revoking user role: {e}")
        raise HTTPException(status_code=500, detail="撤销角色失败")

# 角色权限管理
@router.post("/role-permissions", summary="为角色分配权限")
async def assign_role_permission(
    assignment: RolePermissionAssign,
    current_user: User = Depends(require_permission("role:grant_permission")),
    db: Session = Depends(get_db)
):
    """为角色分配权限"""
    try:
        # 验证角色和权限存在
        role = db.query(Role).filter(Role.id == assignment.role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        permission = db.query(Permission).filter(Permission.id == assignment.permission_id).first()
        if not permission:
            raise HTTPException(status_code=404, detail="权限不存在")
        
        # 检查是否已经分配
        existing_assignment = db.query(RolePermission).filter(
            and_(
                RolePermission.role_id == assignment.role_id,
                RolePermission.permission_id == assignment.permission_id
            )
        ).first()
        
        if existing_assignment:
            raise HTTPException(status_code=400, detail="角色已拥有该权限")
        
        # 创建权限分配
        role_permission = RolePermission(
            role_id=assignment.role_id,
            permission_id=assignment.permission_id
        )
        
        db.add(role_permission)
        db.commit()
        
        # 清除相关缓存
        permission_cache = get_permission_cache()
        permission_cache.invalidate_role_permissions(assignment.role_id)
        permission_cache.invalidate_all_user_permissions()
        
        logger.info(f"Permission {permission.name} assigned to role {role.name} by {current_user.username}")
        return {"message": "权限分配成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning role permission: {e}")
        raise HTTPException(status_code=500, detail="分配权限失败")

@router.delete("/role-permissions/{role_id}/{permission_id}", summary="撤销角色权限")
async def revoke_role_permission(
    role_id: str,
    permission_id: str,
    current_user: User = Depends(require_permission("role:revoke_permission")),
    db: Session = Depends(get_db)
):
    """撤销角色权限"""
    try:
        role_permission = db.query(RolePermission).filter(
            and_(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id
            )
        ).first()
        
        if not role_permission:
            raise HTTPException(status_code=404, detail="角色权限分配不存在")
        
        db.delete(role_permission)
        db.commit()
        
        # 清除相关缓存
        permission_cache = get_permission_cache()
        permission_cache.invalidate_role_permissions(role_id)
        permission_cache.invalidate_all_user_permissions()
        
        logger.info(f"Permission revoked from role {role_id} by {current_user.username}")
        return {"message": "权限撤销成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error revoking role permission: {e}")
        raise HTTPException(status_code=500, detail="撤销权限失败")

# 用户权限查询
@router.get("/users/{user_id}/permissions", summary="获取用户权限")
async def get_user_permissions(
    user_id: str,
    current_user: User = Depends(require_permission("user:read")),
    db: Session = Depends(get_db)
):
    """获取用户的所有权限"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        # 获取用户权限
        permissions = rbac_middleware.get_user_permissions(user, db)
        
        # 获取用户角色
        user_roles_query = text("""
            SELECT r.id, r.name, r.display_name, ur.granted_at, ur.expires_at
            FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = :user_id
            AND (ur.expires_at IS NULL OR ur.expires_at > NOW())
        """)
        
        result = db.execute(user_roles_query, {"user_id": user_id})
        roles = [
            {
                "id": str(row[0]),
                "name": row[1],
                "display_name": row[2],
                "granted_at": row[3].isoformat() if row[3] else None,
                "expires_at": row[4].isoformat() if row[4] else None
            }
            for row in result
        ]
        
        return UserPermissionResponse(
            user_id=str(user.id),
            username=user.username,
            permissions=list(permissions),
            roles=roles
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}")
        raise HTTPException(status_code=500, detail="获取用户权限失败")

@router.get("/roles/{role_id}/permissions", summary="获取角色权限")
async def get_role_permissions(
    role_id: str,
    current_user: User = Depends(require_permission("role:read")),
    db: Session = Depends(get_db)
):
    """获取角色的所有权限"""
    try:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        # 获取角色权限
        permissions_query = text("""
            SELECT p.id, p.name, p.display_name, p.resource_type, p.action, p.description
            FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = :role_id
        """)
        
        result = db.execute(permissions_query, {"role_id": role_id})
        permissions = [
            {
                "id": str(row[0]),
                "name": row[1],
                "display_name": row[2],
                "resource_type": row[3],
                "action": row[4],
                "description": row[5]
            }
            for row in result
        ]
        
        return {
            "role": role.to_dict(),
            "permissions": permissions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting role permissions: {e}")
        raise HTTPException(status_code=500, detail="获取角色权限失败")