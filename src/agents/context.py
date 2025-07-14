"""
用户执行上下文

提供智能体执行时的用户身份、权限、会话信息等上下文数据。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Set, Dict, Any, Optional
from src.utils import logger

if TYPE_CHECKING:
    from server.models.user import User

@dataclass
class UserContext:
    """
    用户执行上下文
    
    包含智能体执行时需要的完整用户信息，支持权限验证、会话管理和个性化配置。
    """
    
    # 基础用户信息
    user_id: str
    username: str
    display_name: Optional[str] = None
    
    # 权限相关
    roles: List[str] = field(default_factory=list)
    permissions: Set[str] = field(default_factory=set)
    
    # 会话信息
    thread_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # 知识库上下文
    kb_id: Optional[str] = None
    accessible_kbs: List[str] = field(default_factory=list)
    
    # 扩展元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 配置信息
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    async def from_user(cls, 
                       user: 'User', 
                       thread_id: str = None,
                       kb_id: str = None,
                       **kwargs) -> 'UserContext':
        """
        从用户对象创建上下文
        
        Args:
            user: 用户数据模型对象
            thread_id: 会话线程ID
            kb_id: 当前知识库ID
            **kwargs: 额外的上下文参数
            
        Returns:
            UserContext: 用户上下文对象
        """
        try:
            # 获取用户权限
            permissions = await cls._get_user_permissions(user.id)
            
            # 获取用户角色
            roles = []
            if hasattr(user, 'roles') and user.roles:
                roles = [role.name for role in user.roles]
            
            # 获取用户可访问的知识库
            accessible_kbs = await cls._get_accessible_kbs(user.id)
            
            # 获取用户偏好设置
            user_preferences = await cls._get_user_preferences(user.id)
            
            context = cls(
                user_id=user.id,
                username=user.username,
                display_name=getattr(user, 'display_name', None),
                roles=roles,
                permissions=set(permissions),
                thread_id=thread_id,
                kb_id=kb_id,
                accessible_kbs=accessible_kbs,
                user_preferences=user_preferences,
                **kwargs
            )
            
            logger.debug(f"用户上下文创建成功: {user.username} ({user.id})")
            return context
            
        except Exception as e:
            logger.error(f"创建用户上下文失败: {e}")
            # 返回基本上下文，确保系统可用性
            return cls(
                user_id=user.id,
                username=user.username,
                display_name=getattr(user, 'display_name', None),
                thread_id=thread_id,
                kb_id=kb_id
            )
    
    @classmethod
    def from_user_sync(cls, 
                      user: 'User', 
                      thread_id: str = None,
                      kb_id: str = None,
                      **kwargs) -> 'UserContext':
        """
        从用户对象同步创建上下文（简化版本）
        
        Args:
            user: 用户数据模型对象
            thread_id: 会话线程ID
            kb_id: 当前知识库ID
            **kwargs: 额外的上下文参数
            
        Returns:
            UserContext: 用户上下文对象
        """
        try:
            # 获取用户角色（同步版本）
            roles = []
            if hasattr(user, 'roles') and user.roles:
                if hasattr(user.roles, '__iter__') and not isinstance(user.roles, str):
                    roles = [role.name if hasattr(role, 'name') else str(role) for role in user.roles]
                else:
                    roles = [str(user.roles)]
            
            # 基础权限 - 确保用户可以访问和执行智能体
            permissions = {
                "agent:access", 
                "agent:execute", 
                "agent:read",
                "tool:basic",
                "tool:use",
                "chat:create",
                "chat:read"
            }
            
            # 检查管理员权限
            if hasattr(user, 'is_admin') and user.is_admin:
                permissions.add("*:*")
            elif any(role in ['admin', 'superadmin'] for role in roles):
                permissions.add("*:*")
            
            context = cls(
                user_id=str(user.id),
                username=str(user.username),
                display_name=getattr(user, 'display_name', None),
                roles=roles,
                permissions=permissions,
                thread_id=thread_id,
                kb_id=kb_id,
                **kwargs
            )
            
            logger.debug(f"用户上下文同步创建成功: {user.username} ({user.id})")
            return context
            
        except Exception as e:
            logger.error(f"同步创建用户上下文失败: {e}")
            # 返回最基本的上下文
            return cls(
                user_id=str(getattr(user, 'id', 'unknown')),
                username=str(getattr(user, 'username', 'unknown')),
                display_name=getattr(user, 'display_name', None),
                thread_id=thread_id,
                kb_id=kb_id,
                permissions={"agent:access", "tool:basic"}
            )
    
    @classmethod
    async def from_user_id(cls, 
                          user_id: str,
                          thread_id: str = None,
                          kb_id: str = None,
                          **kwargs) -> 'UserContext':
        """
        从用户ID创建上下文
        
        Args:
            user_id: 用户ID
            thread_id: 会话线程ID
            kb_id: 当前知识库ID
            **kwargs: 额外的上下文参数
            
        Returns:
            UserContext: 用户上下文对象
        """
        try:
            # 通过用户仓储获取用户信息
            from src.agents.dependencies import get_agent_dependencies
            dependencies = get_agent_dependencies()
            db_manager = await dependencies.db_manager
            user_repo = db_manager.get_user_repository()
            
            user = await user_repo.get_by_id(user_id)
            if not user:
                raise ValueError(f"用户不存在: {user_id}")
            
            return await cls.from_user(user, thread_id=thread_id, kb_id=kb_id, **kwargs)
            
        except Exception as e:
            logger.error(f"从用户ID创建上下文失败: {e}")
            # 返回最基本的上下文
            return cls(
                user_id=user_id,
                username=f"user_{user_id[:8]}",
                thread_id=thread_id,
                kb_id=kb_id
            )
    
    @staticmethod
    async def _get_user_permissions(user_id: str) -> List[str]:
        """获取用户权限列表"""
        try:
            from server.auth.rbac_middleware import get_user_permissions
            return await get_user_permissions(user_id)
        except Exception as e:
            logger.warning(f"获取用户权限失败: {e}")
            return []
    
    @staticmethod
    async def _get_accessible_kbs(user_id: str) -> List[str]:
        """获取用户可访问的知识库列表"""
        try:
            from src.agents.dependencies import get_agent_dependencies
            dependencies = get_agent_dependencies()
            kb_manager = await dependencies.kb_manager
            
            accessible_kbs = await kb_manager.get_user_accessible_kbs(user_id)
            
            # 防御性处理，确保对象有db_id属性
            kb_ids = []
            for kb in accessible_kbs:
                if isinstance(kb, str):
                    # 如果是字符串，可能就是kb_id本身
                    kb_ids.append(kb)
                elif hasattr(kb, 'db_id'):
                    kb_ids.append(kb.db_id)
                else:
                    logger.warning(f"无法获取知识库ID，对象类型: {type(kb)}")
                    
            return kb_ids
        except Exception as e:
            logger.warning(f"获取用户可访问知识库失败: {e}")
            return []
    
    @staticmethod
    async def _get_user_preferences(user_id: str) -> Dict[str, Any]:
        """获取用户偏好设置"""
        try:
            from src.agents.dependencies import get_agent_dependencies
            dependencies = get_agent_dependencies()
            db_manager = await dependencies.db_manager
            user_repo = db_manager.get_user_repository()
            
            # 获取用户偏好（如果有相关表结构）
            preferences = await user_repo.get_user_preferences(user_id)
            return preferences or {}
        except Exception as e:
            logger.warning(f"获取用户偏好设置失败: {e}")
            return {}
    
    def has_permission(self, permission: str) -> bool:
        """
        检查是否拥有指定权限
        
        Args:
            permission: 权限字符串，支持通配符(*)
            
        Returns:
            bool: 是否拥有权限
        """
        if not self.permissions:
            return False
        
        # 超级管理员权限
        if "*:*" in self.permissions:
            return True
        
        # 精确匹配
        if permission in self.permissions:
            return True
        
        # 通配符匹配
        for perm in self.permissions:
            if perm.endswith("*"):
                prefix = perm[:-1]
                if permission.startswith(prefix):
                    return True
        
        return False
    
    def has_role(self, role: str) -> bool:
        """
        检查是否拥有指定角色
        
        Args:
            role: 角色名称
            
        Returns:
            bool: 是否拥有角色
        """
        return role in self.roles
    
    def can_access_kb(self, kb_id: str) -> bool:
        """
        检查是否可以访问指定知识库
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            bool: 是否可以访问
        """
        # 超级管理员可访问所有知识库
        if self.has_permission("*:*") or self.has_permission("kb:*"):
            return True
        
        # 检查具体知识库权限
        return kb_id in self.accessible_kbs
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            dict: 上下文字典
        """
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "roles": self.roles,
            "permissions": list(self.permissions),
            "thread_id": self.thread_id,
            "session_id": self.session_id,
            "kb_id": self.kb_id,
            "accessible_kbs": self.accessible_kbs,
            "metadata": self.metadata,
            "user_preferences": self.user_preferences
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserContext':
        """
        从字典创建上下文对象
        
        Args:
            data: 上下文字典
            
        Returns:
            UserContext: 上下文对象
        """
        # 转换permissions为set类型
        if "permissions" in data and isinstance(data["permissions"], list):
            data["permissions"] = set(data["permissions"])
        
        return cls(**data)
    
    def clone(self, **updates) -> 'UserContext':
        """
        克隆上下文对象并更新指定字段
        
        Args:
            **updates: 要更新的字段
            
        Returns:
            UserContext: 新的上下文对象
        """
        data = self.to_dict()
        data.update(updates)
        return self.from_dict(data)
    
    def __repr__(self) -> str:
        return f"UserContext(user_id='{self.user_id}', username='{self.username}', thread_id='{self.thread_id}')"