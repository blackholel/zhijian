"""
RBAC系统初始化脚本
用于创建默认的角色和权限
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from server.models.user_model import Role, Permission, RolePermission
from server.db_manager import db_manager
from server.utils.redis_manager import init_redis

logger = logging.getLogger(__name__)

# 系统权限定义
SYSTEM_PERMISSIONS = [
    # 用户管理
    ("user:read", "查看用户", "user", "read", "查看用户信息"),
    ("user:create", "创建用户", "user", "create", "创建新用户"),
    ("user:update", "更新用户", "user", "update", "修改用户信息"),
    ("user:delete", "删除用户", "user", "delete", "删除用户"),
    ("user:grant_role", "分配角色", "user", "grant_role", "为用户分配角色"),
    ("user:revoke_role", "撤销角色", "user", "revoke_role", "撤销用户角色"),
    
    # 角色管理
    ("role:read", "查看角色", "role", "read", "查看角色信息"),
    ("role:create", "创建角色", "role", "create", "创建新角色"),
    ("role:update", "更新角色", "role", "update", "修改角色信息"),
    ("role:delete", "删除角色", "role", "delete", "删除角色"),
    ("role:grant_permission", "分配权限", "role", "grant_permission", "为角色分配权限"),
    ("role:revoke_permission", "撤销权限", "role", "revoke_permission", "撤销角色权限"),
    
    # 权限管理
    ("permission:read", "查看权限", "permission", "read", "查看权限信息"),
    ("permission:create", "创建权限", "permission", "create", "创建新权限"),
    ("permission:update", "更新权限", "permission", "update", "修改权限信息"),
    ("permission:delete", "删除权限", "permission", "delete", "删除权限"),
    
    # 知识库管理
    ("kb:read", "查看知识库", "knowledge_base", "read", "查看知识库内容"),
    ("kb:create", "创建知识库", "knowledge_base", "create", "创建新知识库"),
    ("kb:update", "更新知识库", "knowledge_base", "update", "修改知识库内容"),
    ("kb:delete", "删除知识库", "knowledge_base", "delete", "删除知识库"),
    ("kb:upload", "上传文档", "knowledge_base", "upload", "上传文档到知识库"),
    
    # 对话管理
    ("chat:read", "查看对话", "chat", "read", "查看对话记录"),
    ("chat:create", "创建对话", "chat", "create", "创建新对话"),
    ("chat:update", "更新对话", "chat", "update", "修改对话内容"),
    ("chat:delete", "删除对话", "chat", "delete", "删除对话记录"),
    
    # 代理管理
    ("agent:read", "查看代理", "agent", "read", "查看代理配置"),
    ("agent:create", "创建代理", "agent", "create", "创建新代理"),
    ("agent:update", "更新代理", "agent", "update", "修改代理配置"),
    ("agent:delete", "删除代理", "agent", "delete", "删除代理"),
    ("agent:execute", "执行代理", "agent", "execute", "运行代理任务"),
    
    # 系统管理
    ("system:read", "查看系统信息", "system", "read", "查看系统状态和配置"),
    ("system:config", "系统配置", "system", "config", "修改系统配置"),
    ("system:restart", "重启系统", "system", "restart", "重启系统服务"),
    ("system:logs", "查看日志", "system", "logs", "查看系统日志"),
    ("system:backup", "备份数据", "system", "backup", "备份系统数据"),
    
    # 文件管理
    ("file:read", "查看文件", "file", "read", "查看文件内容"),
    ("file:upload", "上传文件", "file", "upload", "上传文件"),
    ("file:download", "下载文件", "file", "download", "下载文件"),
    ("file:delete", "删除文件", "file", "delete", "删除文件"),
    
    # 图数据库管理
    ("graph:read", "查看图数据", "graph", "read", "查看图数据库内容"),
    ("graph:write", "写入图数据", "graph", "write", "修改图数据库内容"),
    ("graph:delete", "删除图数据", "graph", "delete", "删除图数据"),
    
    # 通配符权限（超级权限）
    ("*:*", "超级权限", "all", "all", "拥有所有权限"),
]

# 系统角色定义
SYSTEM_ROLES = [
    {
        "name": "superadmin",
        "display_name": "超级管理员",
        "description": "拥有系统所有权限",
        "permissions": ["*:*"]
    },
    {
        "name": "admin",
        "display_name": "管理员",
        "description": "拥有用户管理、知识库管理等权限",
        "permissions": [
            "user:read", "user:create", "user:update", "user:grant_role", "user:revoke_role",
            "role:read", "permission:read",
            "kb:read", "kb:create", "kb:update", "kb:delete", "kb:upload",
            "chat:read", "chat:create", "chat:update", "chat:delete",
            "agent:read", "agent:create", "agent:update", "agent:delete", "agent:execute",
            "system:read", "system:config", "system:logs",
            "file:read", "file:upload", "file:download", "file:delete",
            "graph:read", "graph:write"
        ]
    },
    {
        "name": "power_user",
        "display_name": "高级用户",
        "description": "拥有知识库和对话管理权限",
        "permissions": [
            "kb:read", "kb:create", "kb:update", "kb:upload",
            "chat:read", "chat:create", "chat:update", "chat:delete",
            "agent:read", "agent:execute",
            "file:read", "file:upload", "file:download",
            "graph:read"
        ]
    },
    {
        "name": "user",
        "display_name": "普通用户",
        "description": "基本的使用权限",
        "permissions": [
            "kb:read",
            "chat:read", "chat:create",
            "agent:read", "agent:execute",
            "file:read",
            "graph:read"
        ]
    }
]

class RBACInitializer:
    """RBAC系统初始化器"""
    
    def __init__(self):
        self.db = db_manager.get_session()
    
    def init_permissions(self):
        """初始化系统权限"""
        try:
            logger.info("开始初始化系统权限...")
            
            for perm_name, display_name, resource_type, action, description in SYSTEM_PERMISSIONS:
                # 检查权限是否已存在
                existing_permission = self.db.query(Permission).filter(
                    Permission.name == perm_name
                ).first()
                
                if not existing_permission:
                    permission = Permission(
                        name=perm_name,
                        display_name=display_name,
                        resource_type=resource_type,
                        action=action,
                        description=description
                    )
                    self.db.add(permission)
                    logger.debug(f"创建权限: {perm_name}")
                else:
                    # 更新现有权限信息
                    existing_permission.display_name = display_name
                    existing_permission.resource_type = resource_type
                    existing_permission.action = action
                    existing_permission.description = description
                    logger.debug(f"更新权限: {perm_name}")
            
            self.db.commit()
            logger.info("系统权限初始化完成")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"初始化权限失败: {e}")
            raise
    
    def init_roles(self):
        """初始化系统角色"""
        try:
            logger.info("开始初始化系统角色...")
            
            for role_data in SYSTEM_ROLES:
                # 检查角色是否已存在
                existing_role = self.db.query(Role).filter(
                    Role.name == role_data["name"]
                ).first()
                
                if not existing_role:
                    role = Role(
                        name=role_data["name"],
                        display_name=role_data["display_name"],
                        description=role_data["description"],
                        is_system=True
                    )
                    self.db.add(role)
                    self.db.commit()
                    self.db.refresh(role)
                    logger.debug(f"创建角色: {role_data['name']}")
                else:
                    # 更新现有角色信息
                    existing_role.display_name = role_data["display_name"]
                    existing_role.description = role_data["description"]
                    role = existing_role
                    logger.debug(f"更新角色: {role_data['name']}")
                
                # 分配权限给角色
                self._assign_permissions_to_role(role, role_data["permissions"])
            
            self.db.commit()
            logger.info("系统角色初始化完成")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"初始化角色失败: {e}")
            raise
    
    def _assign_permissions_to_role(self, role: Role, permission_names: list):
        """为角色分配权限"""
        try:
            # 获取当前角色的权限
            current_permissions = self.db.query(RolePermission).filter(
                RolePermission.role_id == role.id
            ).all()
            
            current_perm_names = set()
            for rp in current_permissions:
                perm = self.db.query(Permission).filter(Permission.id == rp.permission_id).first()
                if perm:
                    current_perm_names.add(perm.name)
            
            # 计算需要添加的权限
            target_perm_names = set(permission_names)
            to_add = target_perm_names - current_perm_names
            to_remove = current_perm_names - target_perm_names
            
            # 添加新权限
            for perm_name in to_add:
                permission = self.db.query(Permission).filter(
                    Permission.name == perm_name
                ).first()
                
                if permission:
                    role_permission = RolePermission(
                        role_id=role.id,
                        permission_id=permission.id
                    )
                    self.db.add(role_permission)
                    logger.debug(f"为角色 {role.name} 添加权限 {perm_name}")
                else:
                    logger.warning(f"权限 {perm_name} 不存在，跳过")
            
            # 移除不需要的权限
            for perm_name in to_remove:
                permission = self.db.query(Permission).filter(
                    Permission.name == perm_name
                ).first()
                
                if permission:
                    role_permission = self.db.query(RolePermission).filter(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == permission.id
                    ).first()
                    
                    if role_permission:
                        self.db.delete(role_permission)
                        logger.debug(f"从角色 {role.name} 移除权限 {perm_name}")
            
        except Exception as e:
            logger.error(f"为角色分配权限失败: {e}")
            raise
    
    def migrate_old_users(self):
        """迁移旧用户到新的RBAC系统"""
        try:
            logger.info("开始迁移旧用户...")
            
            # 查找所有没有external_user_id的用户
            users_query = text("SELECT id, username FROM users WHERE external_user_id IS NULL")
            result = self.db.execute(users_query)
            
            for user_id, username in result:
                # 生成external_user_id
                external_user_id = f"legacy_{user_id}"
                
                # 更新用户信息
                update_query = text("""
                    UPDATE users 
                    SET external_user_id = :external_user_id,
                        login_name = :username,
                        is_active = true
                    WHERE id = :user_id
                """)
                
                self.db.execute(update_query, {
                    "external_user_id": external_user_id,
                    "username": username,
                    "user_id": user_id
                })
                
                # 为所有迁移的用户分配默认的'user'角色
                default_role = self.db.query(Role).filter(Role.name == "user").first()
                
                if default_role:
                    # 检查是否已分配角色
                    existing_assignment = self.db.execute(text("""
                        SELECT 1 FROM user_roles 
                        WHERE user_id = :user_id AND role_id = :role_id
                    """), {"user_id": user_id, "role_id": default_role.id}).first()
                    
                    if not existing_assignment:
                        # 分配默认角色
                        assign_query = text("""
                            INSERT INTO user_roles (id, user_id, role_id, granted_at)
                            VALUES (gen_random_uuid(), :user_id, :role_id, NOW())
                        """)
                        
                        self.db.execute(assign_query, {
                            "user_id": user_id,
                            "role_id": default_role.id
                        })
                        
                        logger.debug(f"为用户 {username} 分配默认角色 user")
                
            self.db.commit()
            logger.info("旧用户迁移完成")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"迁移旧用户失败: {e}")
            raise
    
    def initialize_rbac_system(self):
        """初始化整个RBAC系统"""
        try:
            logger.info("开始初始化RBAC系统...")
            
            # 初始化Redis
            logger.info("初始化Redis连接...")
            init_redis(password="A6pgsql202#00624")
            
            # 初始化权限
            self.init_permissions()
            
            # 初始化角色
            self.init_roles()
            
            # 迁移旧用户
            self.migrate_old_users()
            
            logger.info("RBAC系统初始化完成!")
            
        except Exception as e:
            logger.error(f"RBAC系统初始化失败: {e}")
            raise
        finally:
            self.db.close()

def init_rbac_system():
    """初始化RBAC系统的便捷函数"""
    initializer = RBACInitializer()
    initializer.initialize_rbac_system()

if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(level=logging.INFO)
    
    # 初始化RBAC系统
    init_rbac_system()