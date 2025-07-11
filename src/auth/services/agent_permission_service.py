"""
智能体权限服务

扩展现有权限系统以支持智能体权限管理
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

# from src.database.repositories.base import BaseRepository  # 暂时注释，避免抽象类实例化问题
from src.auth.models.agent_models import AgentDefinition, AgentPermission, AgentSession
from src.auth.models.user_models import User, Permission
from src.auth.services.permission_service import PermissionService
from src.agents.base.exceptions import AgentPermissionError

logger = logging.getLogger(__name__)


class AgentPermissionService:
    """智能体权限服务"""
    
    def __init__(self):
        # 暂时简化实现，不依赖复杂的数据库操作
        pass
    
    async def verify_agent_creation_permission(self, user_id: str) -> bool:
        """验证用户是否有创建智能体的权限"""
        try:
            # TODO: 集成完整的权限检查
            # 暂时允许所有用户创建智能体（开发阶段）
            return True
            
        except Exception as e:
            logger.error(f"验证智能体创建权限失败: {e}")
            return False
    
    async def verify_knowledge_base_permissions(
        self, 
        user_id: str, 
        kb_ids: List[str]
    ) -> Dict[str, bool]:
        """验证知识库权限"""
        results = {}
        
        for kb_id in kb_ids:
            try:
                # TODO: 集成完整的权限检查
                # 暂时允许访问所有知识库（开发阶段）
                results[kb_id] = True
                
            except Exception as e:
                logger.error(f"验证知识库 {kb_id} 权限失败: {e}")
                results[kb_id] = False
        
        return results
    
    async def verify_mcp_tool_permissions(
        self, 
        user_id: str, 
        tool_names: List[str]
    ) -> Dict[str, bool]:
        """验证MCP工具权限"""
        results = {}
        
        for tool_name in tool_names:
            try:
                # TODO: 集成完整的权限检查
                # 暂时允许使用所有MCP工具（开发阶段）
                results[tool_name] = True
                    
            except Exception as e:
                logger.error(f"验证MCP工具 {tool_name} 权限失败: {e}")
                results[tool_name] = False
        
        return results
    
    async def create_agent_permissions(
        self,
        agent_definition_id: str,
        user_id: str,
        knowledge_bases: List[str],
        mcp_tools: List[str],
        additional_permissions: Optional[List[str]] = None
    ) -> bool:
        """创建智能体权限"""
        try:
            session = self.permission_repo.get_session()
            
            # 创建知识库权限
            for kb_id in knowledge_bases:
                permission = AgentPermission(
                    agent_definition_id=agent_definition_id,
                    user_id=user_id,
                    permission_type="knowledge_base",
                    resource_id=kb_id,
                    permission_level="read",
                    permissions=["kb:read", "kb:query"],
                    is_active=True
                )
                session.add(permission)
            
            # 创建MCP工具权限
            for tool_name in mcp_tools:
                permission = AgentPermission(
                    agent_definition_id=agent_definition_id,
                    user_id=user_id,
                    permission_type="mcp_tool",
                    resource_id=tool_name,
                    permission_level="use",
                    permissions=["mcp_tool:use", f"mcp_tool:{tool_name}"],
                    is_active=True
                )
                session.add(permission)
            
            # 创建额外权限
            if additional_permissions:
                permission = AgentPermission(
                    agent_definition_id=agent_definition_id,
                    user_id=user_id,
                    permission_type="system",
                    permission_level="custom",
                    permissions=additional_permissions,
                    is_active=True
                )
                session.add(permission)
            
            session.commit()
            logger.info(f"智能体 {agent_definition_id} 权限创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建智能体权限失败: {e}")
            session.rollback()
            return False
        finally:
            session.close()
    
    async def get_agent_permissions(
        self, 
        agent_definition_id: str
    ) -> Dict[str, List[AgentPermission]]:
        """获取智能体权限"""
        try:
            # TODO: 实现完整的权限获取逻辑
            logger.warning("get_agent_permissions 暂未完全实现")
            return {"knowledge_base": [], "mcp_tool": [], "system": []}
            # session = self.permission_repo.get_session()  # 暂时注释
            
            permissions = session.query(AgentPermission).filter(
                and_(
                    AgentPermission.agent_definition_id == agent_definition_id,
                    AgentPermission.is_active == True
                )
            ).all()
            
            # 按类型分组
            grouped_permissions = {
                "knowledge_base": [],
                "mcp_tool": [],
                "system": []
            }
            
            for permission in permissions:
                perm_type = permission.permission_type
                if perm_type in grouped_permissions:
                    grouped_permissions[perm_type].append(permission)
            
            return grouped_permissions
            
        except Exception as e:
            logger.error(f"获取智能体权限失败: {e}")
            return {}
        finally:
            session.close()
    
    async def update_agent_permissions(
        self,
        agent_definition_id: str,
        permission_updates: Dict[str, Any]
    ) -> bool:
        """更新智能体权限"""
        try:
            # TODO: 实现完整的权限更新逻辑
            logger.warning("update_agent_permissions 暂未完全实现")
            return True
            # session = self.permission_repo.get_session()  # 暂时注释
            
            # 获取现有权限
            existing_permissions = session.query(AgentPermission).filter(
                AgentPermission.agent_definition_id == agent_definition_id
            ).all()
            
            # 先禁用所有现有权限
            for permission in existing_permissions:
                permission.is_active = False
            
            # 创建新权限
            user_id = permission_updates.get("user_id")
            knowledge_bases = permission_updates.get("knowledge_bases", [])
            mcp_tools = permission_updates.get("mcp_tools", [])
            
            await self.create_agent_permissions(
                agent_definition_id, user_id, knowledge_bases, mcp_tools
            )
            
            session.commit()
            logger.info(f"智能体 {agent_definition_id} 权限更新成功")
            return True
            
        except Exception as e:
            logger.error(f"更新智能体权限失败: {e}")
            session.rollback()
            return False
        finally:
            session.close()
    
    async def delete_agent_permissions(self, agent_definition_id: str) -> bool:
        """删除智能体权限"""
        try:
            session = self.permission_repo.get_session()
            
            # 软删除：设置为不活跃
            permissions = session.query(AgentPermission).filter(
                AgentPermission.agent_definition_id == agent_definition_id
            ).all()
            
            for permission in permissions:
                permission.is_active = False
            
            session.commit()
            logger.info(f"智能体 {agent_definition_id} 权限删除成功")
            return True
            
        except Exception as e:
            logger.error(f"删除智能体权限失败: {e}")
            session.rollback()
            return False
        finally:
            session.close()
    
    async def check_agent_resource_permission(
        self,
        agent_definition_id: str,
        resource_type: str,
        resource_id: str,
        permission_level: str = "read"
    ) -> bool:
        """检查智能体资源权限"""
        try:
            session = self.permission_repo.get_session()
            
            permission = session.query(AgentPermission).filter(
                and_(
                    AgentPermission.agent_definition_id == agent_definition_id,
                    AgentPermission.permission_type == resource_type,
                    AgentPermission.resource_id == resource_id,
                    AgentPermission.is_active == True
                )
            ).first()
            
            if not permission:
                return False
            
            # 检查权限级别
            if permission.permission_level == "admin":
                return True
            elif permission.permission_level == "write" and permission_level in ["read", "write"]:
                return True
            elif permission.permission_level == "read" and permission_level == "read":
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查智能体资源权限失败: {e}")
            return False
        finally:
            session.close()
    
    async def get_user_agent_permissions(self, user_id: str) -> Dict[str, Any]:
        """获取用户的智能体权限汇总"""
        try:
            # 基础权限
            can_create_agent = await self.verify_agent_creation_permission(user_id)
            
            # 获取用户的智能体
            session = self.agent_repo.get_session()
            user_agents = session.query(AgentDefinition).filter(
                and_(
                    AgentDefinition.user_id == user_id,
                    AgentDefinition.is_active == True
                )
            ).all()
            
            # 汇总权限信息
            permission_summary = {
                "can_create_agent": can_create_agent,
                "agent_count": len(user_agents),
                "max_agents": await self._get_user_max_agents(user_id),
                "available_knowledge_bases": await self._get_available_knowledge_bases(user_id),
                "available_mcp_tools": await self._get_available_mcp_tools(user_id),
                "agents": []
            }
            
            # 添加每个智能体的详细权限
            for agent in user_agents:
                agent_permissions = await self.get_agent_permissions(str(agent.id))
                permission_summary["agents"].append({
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "type": agent.agent_type,
                    "permissions": agent_permissions
                })
            
            return permission_summary
            
        except Exception as e:
            logger.error(f"获取用户智能体权限失败: {e}")
            return {}
        finally:
            session.close()
    
    async def _get_user_max_agents(self, user_id: str) -> int:
        """获取用户最大智能体数量"""
        # 根据用户角色确定最大智能体数量
        user_roles = await self.permission_service.get_user_roles(user_id)
        
        role_limits = {
            "superadmin": 1000,
            "admin": 100,
            "power_user": 10,
            "user": 3
        }
        
        max_agents = 1  # 默认值
        for role in user_roles:
            if role.name in role_limits:
                max_agents = max(max_agents, role_limits[role.name])
        
        return max_agents
    
    async def _get_available_knowledge_bases(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户可用的知识库"""
        try:
            from src.knowledge_base.services.kb_service import KnowledgeBaseService
            
            kb_service = KnowledgeBaseService()
            user_kbs = await kb_service.get_user_knowledge_bases(user_id)
            
            return [
                {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "type": getattr(kb, 'type', 'unknown')
                }
                for kb in user_kbs
            ]
            
        except Exception as e:
            logger.error(f"获取可用知识库失败: {e}")
            return []
    
    async def _get_available_mcp_tools(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户可用的MCP工具"""
        try:
            from src.mcp_integration.registry import MCPRegistry
            
            registry = MCPRegistry()
            all_tools = await registry.list_tools()
            
            available_tools = []
            for tool in all_tools:
                if await self.permission_service.has_tool_permission(user_id, tool.name):
                    available_tools.append({
                        "name": tool.name,
                        "description": getattr(tool, 'description', ''),
                        "type": getattr(tool, 'type', 'mcp')
                    })
            
            return available_tools
            
        except Exception as e:
            logger.error(f"获取可用MCP工具失败: {e}")
            return []
    
    async def grant_temporary_permission(
        self,
        agent_definition_id: str,
        user_id: str,
        permission_type: str,
        resource_id: str,
        duration_hours: int = 24
    ) -> bool:
        """授予临时权限"""
        try:
            session = self.permission_repo.get_session()
            
            expires_at = datetime.now() + timedelta(hours=duration_hours)
            
            permission = AgentPermission(
                agent_definition_id=agent_definition_id,
                user_id=user_id,
                permission_type=permission_type,
                resource_id=resource_id,
                permission_level="read",
                expires_at=expires_at,
                is_active=True
            )
            
            session.add(permission)
            session.commit()
            
            logger.info(f"临时权限授予成功: {permission_type}:{resource_id}, 过期时间: {expires_at}")
            return True
            
        except Exception as e:
            logger.error(f"授予临时权限失败: {e}")
            session.rollback()
            return False
        finally:
            session.close()
    
    async def cleanup_expired_permissions(self) -> int:
        """清理过期权限"""
        try:
            session = self.permission_repo.get_session()
            
            expired_permissions = session.query(AgentPermission).filter(
                and_(
                    AgentPermission.expires_at <= datetime.now(),
                    AgentPermission.is_active == True
                )
            ).all()
            
            count = len(expired_permissions)
            
            for permission in expired_permissions:
                permission.is_active = False
            
            session.commit()
            
            logger.info(f"清理了 {count} 个过期权限")
            return count
            
        except Exception as e:
            logger.error(f"清理过期权限失败: {e}")
            return 0
        finally:
            session.close()