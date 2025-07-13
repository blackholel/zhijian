"""
企业级智能体管理器
提供统一的智能体管理、权限控制和会话管理功能
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any, Type, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from src.utils import logger
from src.agents.registry import BaseAgent
from src.agents.enterprise_base import (
    EnterpriseAgent, 
    EnterpriseAgentContext, 
    EnterpriseConfiguration
)
from src.agents.enterprise_tools import EnterpriseToolsManager
from src.agents.chatbot.enterprise_chatbot import EnterpriseChatbotAgent
from src.database.manager import UnifiedDatabaseManager
from server.auth.permission_framework.manager import PermissionManager
from server.auth.permission_framework.core import Permission, PermissionContext
from server.auth.permission_framework.concrete_resources import ChatSessionResource
from server.auth.permission_framework.audit import AuditLogger


@dataclass
class AgentSession:
    """智能体会话"""
    session_id: str
    user_id: str
    agent_name: str
    thread_id: str
    created_at: datetime
    last_activity: datetime
    organization_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self, timeout: int = 3600) -> bool:
        """检查会话是否过期"""
        return (datetime.now(timezone.utc) - self.last_activity).seconds > timeout
    
    def update_activity(self):
        """更新活动时间"""
        self.last_activity = datetime.now(timezone.utc)


@dataclass
class AgentMetrics:
    """智能体指标"""
    total_sessions: int = 0
    active_sessions: int = 0
    total_messages: int = 0
    total_errors: int = 0
    average_response_time: float = 0.0
    permission_denials: int = 0
    tool_executions: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "active_sessions": self.active_sessions,
            "total_messages": self.total_messages,
            "total_errors": self.total_errors,
            "average_response_time": self.average_response_time,
            "permission_denials": self.permission_denials,
            "tool_executions": self.tool_executions
        }


class EnterpriseAgentManager:
    """企业级智能体管理器"""
    
    def __init__(self):
        self.agents: Dict[str, EnterpriseAgent] = {}
        self.sessions: Dict[str, AgentSession] = {}
        self.agent_metrics: Dict[str, AgentMetrics] = {}
        self.db_manager: Optional[UnifiedDatabaseManager] = None
        self.permission_manager: Optional[PermissionManager] = None
        self.audit_logger: Optional[AuditLogger] = None
        self.tools_manager: Optional[EnterpriseToolsManager] = None
        self._initialized = False
    
    async def initialize(self):
        """初始化管理器"""
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
            
            # 初始化审计日志
            self.audit_logger = AuditLogger(
                db_manager=self.db_manager
            )
            
            # 初始化工具管理器
            self.tools_manager = EnterpriseToolsManager(self.db_manager)
            await self.tools_manager.initialize()
            
            # 注册默认智能体
            await self.register_default_agents()
            
            self._initialized = True
            logger.info("Enterprise Agent Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Enterprise Agent Manager: {e}")
            raise
    
    async def register_default_agents(self):
        """注册默认智能体"""
        # 注册企业级聊天机器人
        await self.register_agent(EnterpriseChatbotAgent)
        
        # 可以在这里注册更多企业级智能体
        logger.info("Default enterprise agents registered")
    
    async def register_agent(self, agent_class: Type[EnterpriseAgent]):
        """注册智能体"""
        if not self._initialized:
            await self.initialize()
        
        try:
            # 创建智能体实例
            agent = agent_class()
            
            # 初始化企业级组件
            await agent.initialize_enterprise_components()
            
            # 注册到管理器
            self.agents[agent.name] = agent
            self.agent_metrics[agent.name] = AgentMetrics()
            
            logger.info(f"Agent {agent.name} registered successfully")
            
        except Exception as e:
            logger.error(f"Failed to register agent {agent_class.__name__}: {e}")
            raise
    
    async def get_agent(self, agent_name: str) -> Optional[EnterpriseAgent]:
        """获取智能体"""
        if not self._initialized:
            await self.initialize()
        
        return self.agents.get(agent_name)
    
    async def list_agents(self) -> List[str]:
        """列出所有智能体"""
        if not self._initialized:
            await self.initialize()
        
        return list(self.agents.keys())
    
    async def get_agent_info(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """获取智能体信息"""
        agent = await self.get_agent(agent_name)
        if agent:
            info = await agent.get_enterprise_info()
            info["metrics"] = self.agent_metrics[agent_name].to_dict()
            return info
        return None
    
    async def create_session(self, user_id: str, agent_name: str, 
                           organization_id: Optional[str] = None,
                           metadata: Dict[str, Any] = None) -> AgentSession:
        """创建智能体会话"""
        if not self._initialized:
            await self.initialize()
        
        # 检查智能体是否存在
        agent = await self.get_agent(agent_name)
        if not agent:
            raise ValueError(f"Agent {agent_name} not found")
        
        # 创建会话
        session_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        
        session = AgentSession(
            session_id=session_id,
            user_id=user_id,
            agent_name=agent_name,
            thread_id=thread_id,
            created_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            organization_id=organization_id,
            metadata=metadata or {}
        )
        
        # 创建企业级上下文
        context = EnterpriseAgentContext(
            user_id=user_id,
            session_id=session_id,
            thread_id=thread_id,
            organization_id=organization_id,
            request_metadata=metadata
        )
        
        # 检查权限
        config = agent.config_schema()
        if not await agent.validate_permissions(context, config):
            raise PermissionError(f"User {user_id} lacks permissions to use agent {agent_name}")
        
        # 存储会话
        self.sessions[session_id] = session
        
        # 更新指标
        self.agent_metrics[agent_name].total_sessions += 1
        self.agent_metrics[agent_name].active_sessions += 1
        
        # 审计日志
        await self.audit_logger.log_session_created(
            user_id=user_id,
            session_id=session_id,
            agent_name=agent_name
        )
        
        logger.info(f"Session {session_id} created for user {user_id} with agent {agent_name}")
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        """获取会话"""
        session = self.sessions.get(session_id)
        if session and session.is_expired():
            # 清理过期会话
            await self.cleanup_session(session_id)
            return None
        return session
    
    async def cleanup_session(self, session_id: str):
        """清理会话"""
        session = self.sessions.get(session_id)
        if session:
            # 更新指标
            self.agent_metrics[session.agent_name].active_sessions -= 1
            
            # 从存储中删除
            del self.sessions[session_id]
            
            # 审计日志
            await self.audit_logger.log_session_ended(
                user_id=session.user_id,
                session_id=session_id,
                agent_name=session.agent_name
            )
            
            logger.info(f"Session {session_id} cleaned up")
    
    async def send_message(self, session_id: str, message: str, 
                         config: RunnableConfig = None) -> AsyncGenerator[Any, None]:
        """发送消息到智能体"""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found or expired")
        
        # 更新活动时间
        session.update_activity()
        
        # 获取智能体
        agent = await self.get_agent(session.agent_name)
        if not agent:
            raise ValueError(f"Agent {session.agent_name} not found")
        
        # 创建企业级上下文
        context = EnterpriseAgentContext(
            user_id=session.user_id,
            session_id=session.session_id,
            thread_id=session.thread_id,
            organization_id=session.organization_id,
            request_metadata=session.metadata
        )
        
        # 创建消息
        messages = [HumanMessage(content=message)]
        
        # 更新配置
        if not config:
            config = {}
        config.setdefault("configurable", {}).update({
            "thread_id": session.thread_id,
            "user_id": session.user_id
        })
        
        # 更新指标
        self.agent_metrics[session.agent_name].total_messages += 1
        
        try:
            # 发送消息
            async for result in agent.stream_enterprise_messages(messages, context, config):
                yield result
                
        except Exception as e:
            # 更新错误指标
            self.agent_metrics[session.agent_name].total_errors += 1
            
            # 记录错误
            await self.audit_logger.log_message_error(
                user_id=session.user_id,
                session_id=session_id,
                agent_name=session.agent_name,
                error=str(e)
            )
            
            logger.error(f"Error sending message to agent {session.agent_name}: {e}")
            raise
    
    async def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话历史"""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found or expired")
        
        # 获取智能体
        agent = await self.get_agent(session.agent_name)
        if not agent:
            raise ValueError(f"Agent {session.agent_name} not found")
        
        # 创建企业级上下文
        context = EnterpriseAgentContext(
            user_id=session.user_id,
            session_id=session.session_id,
            thread_id=session.thread_id,
            organization_id=session.organization_id,
            request_metadata=session.metadata
        )
        
        # 获取历史记录
        return await agent.get_enterprise_history(context)
    
    async def list_user_sessions(self, user_id: str) -> List[AgentSession]:
        """列出用户会话"""
        user_sessions = []
        for session in self.sessions.values():
            if session.user_id == user_id and not session.is_expired():
                user_sessions.append(session)
        return user_sessions
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        total_sessions = len(self.sessions)
        active_sessions = sum(1 for s in self.sessions.values() if not s.is_expired())
        
        agent_metrics = {}
        for agent_name, metrics in self.agent_metrics.items():
            agent_metrics[agent_name] = metrics.to_dict()
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "total_agents": len(self.agents),
            "agent_metrics": agent_metrics,
            "system_health": await self._get_system_health()
        }
    
    async def _get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        health = {
            "database_manager": "healthy" if self.db_manager else "unhealthy",
            "permission_manager": "healthy" if self.permission_manager else "unhealthy",
            "audit_logger": "healthy" if self.audit_logger else "unhealthy",
            "tools_manager": "healthy" if self.tools_manager else "unhealthy"
        }
        
        # 检查数据库连接
        if self.db_manager:
            try:
                db_health = await self.db_manager.health_check()
                health["databases"] = db_health
            except Exception as e:
                health["databases"] = {"error": str(e)}
        
        return health
    
    async def cleanup_expired_sessions(self):
        """清理过期会话"""
        expired_sessions = []
        for session_id, session in self.sessions.items():
            if session.is_expired():
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.cleanup_session(session_id)
        
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    async def shutdown(self):
        """关闭管理器"""
        # 清理所有会话
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.cleanup_session(session_id)
        
        # 关闭数据库连接
        if self.db_manager:
            await self.db_manager.shutdown()
        
        logger.info("Enterprise Agent Manager shutdown completed")


# 全局管理器实例
enterprise_agent_manager = EnterpriseAgentManager()


async def get_enterprise_agent_manager() -> EnterpriseAgentManager:
    """获取企业级智能体管理器"""
    if not enterprise_agent_manager._initialized:
        await enterprise_agent_manager.initialize()
    return enterprise_agent_manager


# 测试代码
async def test_enterprise_manager():
    """测试企业级智能体管理器"""
    manager = await get_enterprise_agent_manager()
    
    # 创建会话
    session = await manager.create_session("test_user", "enterprise_chatbot")
    print(f"Created session: {session.session_id}")
    
    # 发送消息
    print("Sending message...")
    async for msg, metadata in manager.send_message(session.session_id, "你好"):
        if hasattr(msg, 'content'):
            print(f"Response: {msg.content}")
    
    # 获取历史记录
    history = await manager.get_session_history(session.session_id)
    print(f"History: {len(history)} messages")
    
    # 获取系统指标
    metrics = await manager.get_system_metrics()
    print(f"System metrics: {metrics}")


if __name__ == "__main__":
    asyncio.run(test_enterprise_manager()) 