"""
智能体管理器

参考 DeerFlow 和 Suna 的管理模式，提供完整的生命周期管理
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Type
from datetime import datetime
from contextlib import asynccontextmanager

from .base.agent import BaseAgent
from .base.state import StateType, state_manager
from .base.exceptions import (
    AgentError, AgentConfigError, AgentPermissionError,
    AgentInitializationError, AgentExecutionError
)
from .config.agent_config import AgentConfig, AgentType
from src.auth.services.agent_permission_service import AgentPermissionService
from src.auth.models.agent_models import AgentDefinition, AgentSession
# from src.database.repositories.base import BaseRepository  # 暂时注释，避免抽象类实例化问题

logger = logging.getLogger(__name__)


class AgentManager:
    """智能体管理器
    
    提供智能体的完整生命周期管理：
    - 创建和销毁
    - 启动和停止
    - 配置管理
    - 权限验证
    - 状态监控
    """
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_classes: Dict[AgentType, Type[BaseAgent]] = {}
        
        # 初始化数据库管理器
        from src.database.manager import get_database_manager
        self.db_manager = get_database_manager()
        
        # 初始化服务
        self.permission_service = AgentPermissionService(self.db_manager)
        self.user_repo = self.db_manager.get_user_repository()
        self.agent_repo = self.db_manager.get_agent_repository()
        
        # TODO: 实现会话仓储类
        self.session_repo = None
        
        # 状态监控
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # 注册默认智能体类型
        self._register_default_agent_types()
        
        logger.info("智能体管理器初始化完成")
    
    def _register_default_agent_types(self):
        """注册默认智能体类型"""
        # TODO: 在后续实现具体的智能体类时注册
        # from .core.coordinator import CoordinatorAgent
        # from .core.researcher import ResearcherAgent
        # from .core.analyzer import AnalyzerAgent
        # from .core.reporter import ReporterAgent
        
        # self.agent_classes = {
        #     AgentType.COORDINATOR: CoordinatorAgent,
        #     AgentType.RESEARCHER: ResearcherAgent,
        #     AgentType.ANALYZER: AnalyzerAgent,
        #     AgentType.REPORTER: ReporterAgent,
        # }
        
        # 临时使用基类
        from .base.agent import BaseAgent
        for agent_type in AgentType:
            self.agent_classes[agent_type] = BaseAgent
    
    def register_agent_type(self, agent_type: AgentType, agent_class: Type[BaseAgent]):
        """注册智能体类型"""
        if not issubclass(agent_class, BaseAgent):
            raise ValueError(f"智能体类必须继承自 BaseAgent: {agent_class}")
        
        self.agent_classes[agent_type] = agent_class
        logger.info(f"注册智能体类型: {agent_type.value} -> {agent_class.__name__}")
    
    async def create_agent(self, config: AgentConfig) -> BaseAgent:
        """创建智能体"""
        try:
            logger.info(f"开始创建智能体: {config.name} ({config.agent_type.value})")
            
            # 验证配置
            await self._validate_agent_config(config)
            
            # 验证权限
            await self._verify_creation_permissions(config)
            
            # 检查智能体是否已存在
            if config.agent_id in self.agents:
                raise AgentConfigError(f"智能体已存在: {config.agent_id}")
            
            # 获取智能体类
            agent_class = self.agent_classes.get(config.agent_type)
            if not agent_class:
                raise AgentConfigError(f"不支持的智能体类型: {config.agent_type}")
            
            # 创建智能体实例
            agent = agent_class(config)
            
            # 初始化智能体
            await agent.initialize()
            
            # 注册到管理器
            self.agents[config.agent_id] = agent
            
            # 保存到数据库
            await self._save_agent_definition(config)
            
            # 创建权限记录
            await self._create_agent_permissions(config)
            
            logger.info(f"智能体创建成功: {config.agent_id}")
            return agent
            
        except Exception as e:
            logger.error(f"创建智能体失败: {e}")
            if isinstance(e, (AgentError, AgentConfigError, AgentPermissionError)):
                raise
            raise AgentError(f"创建智能体失败: {str(e)}")
    
    async def _validate_agent_config(self, config: AgentConfig):
        """验证智能体配置"""
        # 基础字段验证
        if not config.name or not config.name.strip():
            raise AgentConfigError("智能体名称不能为空")
        
        if not config.description or not config.description.strip():
            raise AgentConfigError("智能体描述不能为空")
        
        if not config.user_id:
            raise AgentConfigError("必须指定用户ID")
        
        # 资源限制验证
        if len(config.selected_knowledge_bases) > config.resource_limits.max_knowledge_bases:
            raise AgentConfigError(
                f"知识库数量超过限制: {len(config.selected_knowledge_bases)} > {config.resource_limits.max_knowledge_bases}"
            )
        
        if len(config.selected_mcp_tools) > config.resource_limits.max_mcp_tools:
            raise AgentConfigError(
                f"MCP工具数量超过限制: {len(config.selected_mcp_tools)} > {config.resource_limits.max_mcp_tools}"
            )
    
    async def _verify_creation_permissions(self, config: AgentConfig):
        """验证创建权限"""
        # 验证用户是否有创建智能体的权限
        can_create = await self.permission_service.verify_agent_creation_permission(config.user_id)
        if not can_create:
            raise AgentPermissionError("用户没有创建智能体的权限")
        
        # 验证知识库权限
        kb_permissions = await self.permission_service.verify_knowledge_base_permissions(
            config.user_id, config.selected_knowledge_bases
        )
        
        for kb_id, has_permission in kb_permissions.items():
            if not has_permission:
                raise AgentPermissionError(f"用户没有访问知识库 {kb_id} 的权限")
        
        # 验证MCP工具权限
        tool_permissions = await self.permission_service.verify_mcp_tool_permissions(
            config.user_id, config.selected_mcp_tools
        )
        
        for tool_name, has_permission in tool_permissions.items():
            if not has_permission:
                raise AgentPermissionError(f"用户没有使用工具 {tool_name} 的权限")
    
    async def _save_agent_definition(self, config: AgentConfig):
        """保存智能体定义到数据库"""
        try:
            from src.database.repositories.agent_repository import AgentInfo
            
            agent_info = AgentInfo(
                agent_id=config.agent_id,
                name=config.name,
                description=config.description,
                agent_type=config.agent_type.value,
                version=config.version,
                user_id=config.user_id,
                organization_id=config.organization_id,
                config_data=config.dict(),
                is_active=True
            )
            
            await self.agent_repo.create(agent_info)
            logger.info(f"智能体定义已保存: {config.agent_id}")
            
        except Exception as e:
            logger.error(f"保存智能体定义失败: {e}")
            raise
    
    async def _create_agent_permissions(self, config: AgentConfig):
        """创建智能体权限"""
        try:
            # 获取数据库中的智能体定义
            agent_info = await self.agent_repo.get_by_field(
                "agent_id", config.agent_id
            )
            
            if not agent_info:
                raise AgentError("智能体定义未找到")
            
            # 创建权限
            success = await self.permission_service.create_agent_permissions(
                agent_info.agent_id,  # 使用agent_id而不是数据库ID
                config.user_id,
                config.selected_knowledge_bases,
                config.selected_mcp_tools
            )
            
            if not success:
                raise AgentError("创建智能体权限失败")
            
            logger.info(f"智能体权限已创建: {config.agent_id}")
            
        except Exception as e:
            logger.error(f"创建智能体权限失败: {e}")
            raise
    
    async def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """获取智能体"""
        return self.agents.get(agent_id)
    
    async def get_agent_by_name(self, name: str, user_id: str) -> Optional[BaseAgent]:
        """根据名称获取智能体"""
        for agent in self.agents.values():
            if agent.config.name == name and agent.config.user_id == user_id:
                return agent
        return None
    
    async def list_agents(self, user_id: Optional[str] = None) -> List[BaseAgent]:
        """列出智能体"""
        agents = list(self.agents.values())
        
        if user_id:
            agents = [agent for agent in agents if agent.config.user_id == user_id]
        
        return agents
    
    async def list_agents_by_type(self, agent_type: AgentType, user_id: Optional[str] = None) -> List[BaseAgent]:
        """根据类型列出智能体"""
        agents = [
            agent for agent in self.agents.values()
            if agent.config.agent_type == agent_type
        ]
        
        if user_id:
            agents = [agent for agent in agents if agent.config.user_id == user_id]
        
        return agents
    
    async def update_agent_config(self, agent_id: str, config_updates: Dict[str, Any]) -> bool:
        """更新智能体配置"""
        try:
            agent = self.agents.get(agent_id)
            if not agent:
                raise AgentError(f"智能体不存在: {agent_id}")
            
            # 更新配置
            old_config = agent.config
            new_config_data = old_config.dict()
            new_config_data.update(config_updates)
            new_config = AgentConfig(**new_config_data)
            
            # 验证新配置
            await self._validate_agent_config(new_config)
            await self._verify_creation_permissions(new_config)
            
            # 停止智能体
            await agent.stop()
            
            # 更新配置
            agent.config = new_config
            
            # 重新初始化
            await agent.initialize()
            
            # 更新数据库
            await self._update_agent_definition(new_config)
            
            # 更新权限
            await self._update_agent_permissions(new_config)
            
            logger.info(f"智能体配置更新成功: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新智能体配置失败: {e}")
            return False
    
    async def _update_agent_definition(self, config: AgentConfig):
        """更新智能体定义"""
        agent_info = await self.agent_repo.get_by_field("agent_id", config.agent_id)
        if agent_info:
            agent_info.name = config.name
            agent_info.description = config.description
            agent_info.config_data = config.dict()
            agent_info.updated_at = datetime.now()
            
            await self.agent_repo.update(agent_info)
    
    async def _update_agent_permissions(self, config: AgentConfig):
        """更新智能体权限"""
        agent_info = await self.agent_repo.get_by_field("agent_id", config.agent_id)
        if agent_info:
            await self.permission_service.update_agent_permissions(
                agent_info.agent_id,  # 使用agent_id
                {
                    "user_id": config.user_id,
                    "knowledge_bases": config.selected_knowledge_bases,
                    "mcp_tools": config.selected_mcp_tools
                }
            )
    
    async def start_agent(self, agent_id: str) -> bool:
        """启动智能体"""
        try:
            agent = self.agents.get(agent_id)
            if not agent:
                raise AgentError(f"智能体不存在: {agent_id}")
            
            await agent.start()
            logger.info(f"智能体启动成功: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"启动智能体失败: {e}")
            return False
    
    async def stop_agent(self, agent_id: str) -> bool:
        """停止智能体"""
        try:
            agent = self.agents.get(agent_id)
            if not agent:
                raise AgentError(f"智能体不存在: {agent_id}")
            
            await agent.stop()
            logger.info(f"智能体停止成功: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"停止智能体失败: {e}")
            return False
    
    async def remove_agent(self, agent_id: str, user_id: str) -> bool:
        """移除智能体"""
        try:
            agent = self.agents.get(agent_id)
            if not agent:
                raise AgentError(f"智能体不存在: {agent_id}")
            
            # 验证权限
            if agent.config.user_id != user_id:
                raise AgentPermissionError("只能删除自己创建的智能体")
            
            # 停止智能体
            await agent.stop()
            
            # 清理资源
            await agent.cleanup()
            
            # 从管理器中移除
            del self.agents[agent_id]
            
            # 软删除数据库记录
            await self._soft_delete_agent_definition(agent_id)
            
            # 删除权限
            agent_info = await self.agent_repo.get_by_field("agent_id", agent_id)
            if agent_info:
                await self.permission_service.delete_agent_permissions(agent_info.agent_id)
            
            logger.info(f"智能体移除成功: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"移除智能体失败: {e}")
            return False
    
    async def _soft_delete_agent_definition(self, agent_id: str):
        """软删除智能体定义"""
        # 使用仓储的删除方法
        await self.agent_repo.delete(agent_id)
    
    async def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取智能体状态"""
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        
        return await agent.get_status()
    
    async def get_all_agent_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有智能体状态"""
        status = {}
        
        for agent_id, agent in self.agents.items():
            try:
                status[agent_id] = await agent.get_status()
            except Exception as e:
                logger.error(f"获取智能体 {agent_id} 状态失败: {e}")
                status[agent_id] = {"error": str(e)}
        
        return status
    
    async def execute_agent_task(
        self, 
        agent_id: str, 
        task: Dict[str, Any], 
        user_id: str
    ) -> Dict[str, Any]:
        """执行智能体任务"""
        try:
            agent = self.agents.get(agent_id)
            if not agent:
                raise AgentError(f"智能体不存在: {agent_id}")
            
            # 验证权限
            if agent.config.user_id != user_id:
                raise AgentPermissionError("只能操作自己的智能体")
            
            # 执行任务
            result = await agent.execute_task(task)
            
            logger.info(f"智能体任务执行成功: {agent_id}")
            return result
            
        except Exception as e:
            logger.error(f"执行智能体任务失败: {e}")
            raise
    
    async def get_available_knowledge_bases(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户可用的知识库"""
        return await self.permission_service._get_available_knowledge_bases(user_id)
    
    async def get_available_mcp_tools(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户可用的MCP工具"""
        return await self.permission_service._get_available_mcp_tools(user_id)
    
    async def start_monitoring(self):
        """启动监控任务"""
        if self._monitoring_task and not self._monitoring_task.done():
            return
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("智能体监控已启动")
    
    async def stop_monitoring(self):
        """停止监控任务"""
        if self._monitoring_task:
            self._shutdown_event.set()
            try:
                await asyncio.wait_for(self._monitoring_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._monitoring_task.cancel()
            
            logger.info("智能体监控已停止")
    
    async def _monitoring_loop(self):
        """监控循环"""
        logger.info("智能体监控循环已启动")
        
        while not self._shutdown_event.is_set():
            try:
                # 检查智能体健康状态
                await self._health_check()
                
                # 清理过期权限
                try:
                    cleaned_count = await self.permission_service.cleanup_expired_permissions()
                    if cleaned_count > 0:
                        logger.info(f"清理了 {cleaned_count} 个过期权限")
                except Exception as perm_error:
                    logger.error(f"清理过期权限失败: {perm_error}")
                
                # 等待下次检查
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), 
                        timeout=60.0  # 每分钟检查一次
                    )
                    # 如果事件被设置，退出循环
                    break
                except asyncio.TimeoutError:
                    # 超时正常，继续下一次检查
                    continue
                    
            except asyncio.CancelledError:
                logger.info("监控循环被取消")
                break
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                # 错误时等待更短的时间
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), 
                        timeout=10.0  # 错误时短暂休眠
                    )
                    break
                except asyncio.TimeoutError:
                    continue
        
        logger.info("智能体监控循环已停止")
    
    async def _health_check(self):
        """健康检查"""
        unhealthy_agents = []
        
        for agent_id, agent in self.agents.items():
            try:
                state = await state_manager.get_state(agent_id)
                if not state or state.state_type == StateType.ERROR:
                    unhealthy_agents.append(agent_id)
            except Exception as e:
                logger.error(f"检查智能体 {agent_id} 健康状态失败: {e}")
                unhealthy_agents.append(agent_id)
        
        if unhealthy_agents:
            logger.warning(f"发现不健康的智能体: {unhealthy_agents}")
    
    @asynccontextmanager
    async def agent_context(self, agent_id: str):
        """智能体上下文管理器"""
        agent = self.agents.get(agent_id)
        if not agent:
            raise AgentError(f"智能体不存在: {agent_id}")
        
        try:
            yield agent
        finally:
            # 可以在这里做一些清理工作
            pass
    
    async def shutdown(self):
        """关闭管理器"""
        logger.info("开始关闭智能体管理器")
        
        # 停止监控
        await self.stop_monitoring()
        
        # 停止所有智能体
        for agent_id in list(self.agents.keys()):
            try:
                await self.stop_agent(agent_id)
            except Exception as e:
                logger.error(f"停止智能体 {agent_id} 失败: {e}")
        
        # 清理所有智能体
        for agent in list(self.agents.values()):
            try:
                await agent.cleanup()
            except Exception as e:
                logger.error(f"清理智能体失败: {e}")
        
        self.agents.clear()
        
        logger.info("智能体管理器已关闭")


# 全局智能体管理器实例
agent_manager = AgentManager()