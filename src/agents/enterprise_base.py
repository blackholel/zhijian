"""
企业级智能体基类
集成权限系统、统一数据库管理和知识库系统
"""

import uuid
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph

from src.utils import logger
from src.agents.registry import BaseAgent, Configuration, State
from src.database.manager import UnifiedDatabaseManager
from server.auth.permission_framework.manager import PermissionManager
from server.auth.permission_framework.core import Permission, PermissionContext
from server.auth.permission_framework.concrete_resources import (
    KnowledgeBaseResource, 
    ChatSessionResource,
    MCPToolResource
)
from server.auth.permission_framework.decorators import (
    require_permission,
    require_kb_permission,
    require_any_permission
)
from server.auth.permission_framework.audit import AuditLogger
from src.database.managers.knowledge_manager import KnowledgeBaseManager
from src.database.managers.kb_collection_manager import KnowledgeBaseCollectionManager


@dataclass
class EnterpriseAgentContext:
    """企业级智能体上下文"""
    user_id: str
    session_id: str
    thread_id: str
    organization_id: Optional[str] = None
    request_metadata: Optional[Dict[str, Any]] = None
    
    def to_permission_context(self, resource, permission: Permission) -> PermissionContext:
        """转换为权限上下文"""
        return PermissionContext(
            user_id=self.user_id,
            resource=resource,
            permission=permission,
            request_metadata=self.request_metadata or {}
        )


@dataclass(kw_only=True)
class EnterpriseConfiguration(Configuration):
    """企业级智能体配置"""
    
    # 权限配置
    required_permissions: List[str] = field(
        default_factory=list,
        metadata={
            "name": "必需权限",
            "configurable": False,
            "description": "智能体运行所需的权限列表"
        }
    )
    
    # 知识库配置
    accessible_knowledge_bases: List[str] = field(
        default_factory=list,
        metadata={
            "name": "可访问知识库",
            "configurable": True,
            "description": "智能体可以访问的知识库ID列表"
        }
    )
    
    # 审计配置
    enable_audit: bool = field(
        default=True,
        metadata={
            "name": "启用审计",
            "configurable": False,
            "description": "是否启用操作审计"
        }
    )
    
    # 缓存配置
    enable_cache: bool = field(
        default=True,
        metadata={
            "name": "启用缓存",
            "configurable": False,
            "description": "是否启用权限和数据缓存"
        }
    )
    
    # 会话配置
    session_timeout: int = field(
        default=3600,
        metadata={
            "name": "会话超时时间",
            "configurable": True,
            "description": "会话超时时间（秒）"
        }
    )


class EnterpriseAgent(BaseAgent, ABC):
    """企业级智能体基类"""
    
    config_schema = EnterpriseConfiguration
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db_manager: Optional[UnifiedDatabaseManager] = None
        self.permission_manager: Optional[PermissionManager] = None
        self.kb_manager: Optional[KnowledgeBaseManager] = None
        self.audit_logger: Optional[AuditLogger] = None
        self._initialized = False
    
    async def initialize_enterprise_components(self):
        """初始化企业级组件"""
        if self._initialized:
            return
            
        try:
            # 初始化数据库管理器
            self.db_manager = UnifiedDatabaseManager()
            await self.db_manager.initialize()
            
            # 初始化权限管理器
            self.permission_manager = PermissionManager(
                db_manager=self.db_manager,
                enable_cache=True
            )
            
            # 初始化知识库管理器
            self.kb_manager = KnowledgeBaseManager(
                connection_manager=self.db_manager.connection_manager
            )
            
            # 初始化审计日志
            self.audit_logger = AuditLogger(
                db_manager=self.db_manager
            )
            
            self._initialized = True
            logger.info(f"Enterprise Agent {self.name} initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Enterprise Agent {self.name}: {e}")
            raise
    
    async def validate_permissions(self, context: EnterpriseAgentContext, 
                                 config: EnterpriseConfiguration) -> bool:
        """验证用户权限"""
        if not self.permission_manager:
            await self.initialize_enterprise_components()
        
        # 检查必需权限
        for permission_str in config.required_permissions:
            permission = Permission(permission_str)
            # 这里可以根据需要创建不同的资源类型
            # 暂时使用系统权限检查
            if not await self.permission_manager.check_system_permission(
                context.user_id, permission
            ):
                await self.audit_logger.log_permission_denied(
                    context.user_id, f"agent:{self.name}", permission_str
                )
                return False
        
        return True
    
    async def get_accessible_knowledge_bases(self, 
                                           context: EnterpriseAgentContext,
                                           config: EnterpriseConfiguration) -> List[str]:
        """获取用户可访问的知识库列表"""
        if not self.kb_manager:
            await self.initialize_enterprise_components()
        
        accessible_kbs = []
        
        # 如果配置中指定了知识库，检查权限
        if config.accessible_knowledge_bases:
            for kb_id in config.accessible_knowledge_bases:
                kb_resource = KnowledgeBaseResource(kb_id)
                permission_context = context.to_permission_context(
                    kb_resource, Permission.READ
                )
                
                if await self.permission_manager.check_permission(permission_context):
                    accessible_kbs.append(kb_id)
        else:
            # 获取用户所有可访问的知识库
            accessible_kbs = await self.kb_manager.get_user_accessible_knowledge_bases(
                context.user_id
            )
        
        return accessible_kbs
    
    async def create_secure_session(self, context: EnterpriseAgentContext) -> Dict[str, Any]:
        """创建安全会话"""
        if not self.db_manager:
            await self.initialize_enterprise_components()
        
        session_data = {
            "session_id": context.session_id,
            "user_id": context.user_id,
            "thread_id": context.thread_id,
            "agent_name": self.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "organization_id": context.organization_id,
            "metadata": context.request_metadata or {}
        }
        
        # 存储会话信息到Redis
        redis_adapter = await self.db_manager.get_adapter('redis')
        session_key = f"agent_session:{context.session_id}"
        await redis_adapter.set(session_key, session_data, ex=3600)  # 1小时过期
        
        return session_data
    
    async def log_agent_action(self, context: EnterpriseAgentContext, 
                             action: str, details: Dict[str, Any]):
        """记录智能体操作"""
        if not self.audit_logger:
            await self.initialize_enterprise_components()
        
        await self.audit_logger.log_agent_action(
            user_id=context.user_id,
            agent_name=self.name,
            action=action,
            details=details,
            session_id=context.session_id
        )
    
    async def stream_with_permissions(self, messages: List[BaseMessage], 
                                    context: EnterpriseAgentContext,
                                    config: RunnableConfig = None):
        """带权限检查的流式处理"""
        # 解析配置
        enterprise_config = self.config_schema.from_runnable_config(
            config, agent_name=self.name
        )
        
        # 初始化企业级组件
        await self.initialize_enterprise_components()
        
        # 验证权限
        if not await self.validate_permissions(context, enterprise_config):
            raise PermissionError(f"User {context.user_id} lacks required permissions for agent {self.name}")
        
        # 创建会话
        session_data = await self.create_secure_session(context)
        
        # 记录开始操作
        await self.log_agent_action(context, "stream_started", {
            "message_count": len(messages),
            "session_data": session_data
        })
        
        try:
            # 调用原有的流式处理方法
            async for result in self.stream_messages(messages, config):
                yield result
                
        except Exception as e:
            # 记录错误
            await self.log_agent_action(context, "stream_error", {
                "error": str(e),
                "session_id": context.session_id
            })
            raise
        finally:
            # 记录结束操作
            await self.log_agent_action(context, "stream_completed", {
                "session_id": context.session_id
            })
    
    async def get_enterprise_info(self) -> Dict[str, Any]:
        """获取企业级智能体信息"""
        base_info = await self.get_info()
        
        # 添加企业级信息
        enterprise_info = {
            **base_info,
            "enterprise_features": {
                "permission_integration": True,
                "database_integration": True,
                "knowledge_base_integration": True,
                "audit_logging": True,
                "session_management": True
            },
            "required_permissions": getattr(self.config_schema(), 'required_permissions', []),
            "supports_multi_kb": True,
            "supports_secure_sessions": True
        }
        
        return enterprise_info
    
    @abstractmethod
    async def get_enterprise_graph(self, context: EnterpriseAgentContext,
                                 config: RunnableConfig = None) -> CompiledStateGraph:
        """获取企业级智能体图"""
        pass
    
    async def get_graph(self, **kwargs) -> CompiledStateGraph:
        """重写基类方法，提供企业级图"""
        # 如果提供了企业级上下文，使用企业级图
        if 'context' in kwargs and isinstance(kwargs['context'], EnterpriseAgentContext):
            return await self.get_enterprise_graph(kwargs['context'], kwargs.get('config'))
        
        # 否则使用默认图（兼容性）
        return await self.get_enterprise_graph(
            EnterpriseAgentContext(
                user_id="anonymous",
                session_id=str(uuid.uuid4()),
                thread_id=str(uuid.uuid4())
            ),
            kwargs.get('config')
        ) 