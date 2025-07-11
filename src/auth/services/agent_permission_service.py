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
    
    def __init__(self, db_manager=None):
        # 初始化数据库管理器和仓储
        if db_manager is None:
            from src.database.manager import get_database_manager
            self.db_manager = get_database_manager()
        else:
            self.db_manager = db_manager
        
        # 初始化仓储
        self.user_repo = self.db_manager.get_user_repository()
        self.permission_repo = self.db_manager.get_user_repository()  # 权限相关操作使用用户仓储
        self.agent_repo = None  # 将在需要时初始化
        
        # 暂时不初始化权限服务，避免循环依赖
        self.permission_service = None
        
        logger.info("智能体权限服务初始化完成")
    
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
            # 使用项目标准的execute_query方法
            adapter = await self.db_manager.connection_manager.ensure_connection('server_db')
            
            # 创建知识库权限
            for kb_id in knowledge_bases:
                kb_query = """
                    INSERT INTO agent_permissions (
                        agent_definition_id, user_id, permission_type, resource_id,
                        permission_level, permissions, is_active, created_at
                    ) VALUES (
                        :agent_id, :user_id, 'knowledge_base', :resource_id,
                        'read', :permissions, true, NOW()
                    )
                """
                
                await adapter.execute_query(kb_query, {
                    'agent_id': agent_definition_id,
                    'user_id': user_id,
                    'resource_id': kb_id,
                    'permissions': '["kb:read", "kb:query"]'
                })
            
            # 创建MCP工具权限
            for tool_name in mcp_tools:
                tool_query = """
                    INSERT INTO agent_permissions (
                        agent_definition_id, user_id, permission_type, resource_id,
                        permission_level, permissions, is_active, created_at
                    ) VALUES (
                        :agent_id, :user_id, 'mcp_tool', :resource_id,
                        'use', :permissions, true, NOW()
                    )
                """
                
                await adapter.execute_query(tool_query, {
                    'agent_id': agent_definition_id,
                    'user_id': user_id,
                    'resource_id': tool_name,
                    'permissions': f'["mcp_tool:use", "mcp_tool:{tool_name}"]'
                })
            
            # 创建额外权限
            if additional_permissions:
                system_query = """
                    INSERT INTO agent_permissions (
                        agent_definition_id, user_id, permission_type,
                        permission_level, permissions, is_active, created_at
                    ) VALUES (
                        :agent_id, :user_id, 'system',
                        'custom', :permissions, true, NOW()
                    )
                """
                
                await adapter.execute_query(system_query, {
                    'agent_id': agent_definition_id,
                    'user_id': user_id,
                    'permissions': str(additional_permissions)
                })
            
            logger.info(f"智能体 {agent_definition_id} 权限创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建智能体权限失败: {e}")
            return False
    
    async def get_agent_permissions(
        self, 
        agent_definition_id: str
    ) -> Dict[str, List[AgentPermission]]:
        """获取智能体权限"""
        try:
            # 暂时返回空结果，后续实现完整的权限获取逻辑
            logger.warning("get_agent_permissions 暂未完全实现")
            return {"knowledge_base": [], "mcp_tool": [], "system": []}
            
        except Exception as e:
            logger.error(f"获取智能体权限失败: {e}")
            return {"knowledge_base": [], "mcp_tool": [], "system": []}
    
    async def update_agent_permissions(
        self,
        agent_definition_id: str,
        permission_updates: Dict[str, Any]
    ) -> bool:
        """更新智能体权限"""
        try:
            # 暂时简化实现，后续实现完整的权限更新逻辑
            logger.warning("update_agent_permissions 暂未完全实现")
            return True
            
        except Exception as e:
            logger.error(f"更新智能体权限失败: {e}")
            return False
    
    async def delete_agent_permissions(self, agent_definition_id: str) -> bool:
        """删除智能体权限"""
        try:
            # 使用项目标准的execute_query方法
            adapter = await self.db_manager.connection_manager.ensure_connection('server_db')
            
            query = """
                UPDATE agent_permissions 
                SET is_active = false 
                WHERE agent_definition_id = :agent_id
            """
            
            result = await adapter.execute_query(query, {'agent_id': agent_definition_id})
            
            logger.info(f"智能体 {agent_definition_id} 权限删除成功")
            return True
            
        except Exception as e:
            logger.error(f"删除智能体权限失败: {e}")
            return False
    
    async def check_agent_resource_permission(
        self,
        agent_definition_id: str,
        resource_type: str,
        resource_id: str,
        permission_level: str = "read"
    ) -> bool:
        """检查智能体资源权限"""
        try:
            # 暂时允许所有资源访问，后续实现完整的权限检查
            logger.debug(f"检查权限: agent={agent_definition_id}, resource={resource_type}:{resource_id}, level={permission_level}")
            return True
            
        except Exception as e:
            logger.error(f"检查智能体资源权限失败: {e}")
            return False
    
    async def get_user_agent_permissions(self, user_id: str) -> Dict[str, Any]:
        """获取用户的智能体权限汇总"""
        try:
            # 基础权限
            can_create_agent = await self.verify_agent_creation_permission(user_id)
            
            # 暂时返回简化的权限信息
            permission_summary = {
                "can_create_agent": can_create_agent,
                "agent_count": 0,
                "max_agents": await self._get_user_max_agents(user_id),
                "available_knowledge_bases": await self._get_available_knowledge_bases(user_id),
                "available_mcp_tools": await self._get_available_mcp_tools(user_id),
                "agents": []
            }
            
            return permission_summary
            
        except Exception as e:
            logger.error(f"获取用户智能体权限失败: {e}")
            return {
                "can_create_agent": True,
                "agent_count": 0,
                "max_agents": 3,
                "available_knowledge_bases": [],
                "available_mcp_tools": [],
                "agents": []
            }
    
    async def _get_user_max_agents(self, user_id: str) -> int:
        """获取用户最大智能体数量"""
        try:
            # 根据用户角色确定最大智能体数量
            if self.permission_service:
                user_roles = await self.permission_service.get_user_roles(user_id)
            else:
                user_roles = []  # 暂时返回空角色列表
        except Exception as e:
            logger.warning(f"获取用户角色失败: {e}")
            user_roles = []
        
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
                try:
                    if self.permission_service and await self.permission_service.has_tool_permission(user_id, tool.name):
                        available_tools.append({
                            "name": tool.name,
                            "description": getattr(tool, 'description', ''),
                            "type": getattr(tool, 'type', 'mcp')
                        })
                    else:
                        # 如果没有权限服务或检查失败，暂时允许所有工具
                        available_tools.append({
                            "name": tool.name,
                            "description": getattr(tool, 'description', ''),
                            "type": getattr(tool, 'type', 'mcp')
                        })
                except Exception as tool_error:
                    logger.warning(f"检查工具权限失败: {tool_error}")
                    # 暂时允许所有工具
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
            # 使用项目标准的execute_query方法
            adapter = await self.db_manager.connection_manager.ensure_connection('server_db')
            
            expires_at = datetime.now() + timedelta(hours=duration_hours)
            
            query = """
                INSERT INTO agent_permissions (
                    agent_definition_id, user_id, permission_type, resource_id,
                    permission_level, expires_at, is_active, created_at
                ) VALUES (
                    :agent_id, :user_id, :permission_type, :resource_id,
                    'read', :expires_at, true, NOW()
                )
            """
            
            await adapter.execute_query(query, {
                'agent_id': agent_definition_id,
                'user_id': user_id,
                'permission_type': permission_type,
                'resource_id': resource_id,
                'expires_at': expires_at
            })
            
            logger.info(f"临时权限授予成功: {permission_type}:{resource_id}, 过期时间: {expires_at}")
            return True
            
        except Exception as e:
            logger.error(f"授予临时权限失败: {e}")
            return False
    
    async def cleanup_expired_permissions(self) -> int:
        """清理过期权限"""
        try:
            # 使用项目标准的execute_query方法
            adapter = await self.db_manager.connection_manager.ensure_connection('server_db')
            
            # 查询过期权限数量
            count_query = """
                SELECT COUNT(*) as count FROM agent_permissions 
                WHERE expires_at <= NOW() AND is_active = true
            """
            result = await adapter.execute_query(count_query)
            # execute_query返回的是行的列表，每行是tuple
            count = result[0][0] if result and len(result) > 0 else 0
            
            if count > 0:
                # 更新为不活跃状态
                update_query = """
                    UPDATE agent_permissions 
                    SET is_active = false 
                    WHERE expires_at <= NOW() AND is_active = true
                """
                await adapter.execute_query(update_query)
            
            logger.info(f"清理了 {count} 个过期权限")
            return count
                
        except Exception as e:
            logger.error(f"清理过期权限失败: {e}")
            return 0