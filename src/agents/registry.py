from __future__ import annotations

import os
import yaml
import uuid
from pathlib import Path
from typing import Annotated, TypedDict, TYPE_CHECKING, Optional, Dict, Any
from abc import abstractmethod, ABC
from dataclasses import dataclass, fields, field

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages

from src.utils import logger

if TYPE_CHECKING:
    from src.database.manager import UnifiedDatabaseManager
    from server.auth.permission_framework.engine import PermissionEngine
    from src.knowledge_base.manager import KnowledgeBaseManager
    from src.agents.context import UserContext

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@dataclass(kw_only=True)
class Configuration(dict):
    """
    定义一个基础 Configuration 供各类 graph 继承
    
    集成统一数据库配置管理的配置系统
    
    配置优先级 (从高到低):
    1. 运行时配置(RunnableConfig)：最高优先级，直接从函数参数传入
    2. 文件配置(config.private.yaml)：文件级配置
    3. 知识库级配置：特定知识库的智能体配置  
    4. 用户级配置：用户个性化智能体配置
    5. 数据库系统配置：全局智能体配置
    6. 类默认配置：最低优先级，类中定义的默认值
    """
    
    # 新增集成字段
    user_context: Optional['UserContext'] = field(default=None, metadata={"configurable": False})
    db_config: Optional[Dict[str, Any]] = field(default=None, metadata={"configurable": False})
    permission_context: Optional[Dict[str, Any]] = field(default=None, metadata={"configurable": False})

    @classmethod
    async def from_runnable_config(
        cls, 
        config: RunnableConfig | None = None, 
        agent_name: str | None = None,
        user_context: Optional['UserContext'] = None
    ) -> 'Configuration':
        """Create a Configuration instance from a RunnableConfig object.
        
        集成数据库配置管理器的配置加载
        
        Args:
            config: RunnableConfig object with highest priority
            agent_name: Name of the agent to load config file for
            user_context: User context for personalized configuration
            
        Returns:
            Configuration instance with merged config values
        """
        # 获取类默认配置：创建一个实例获取所有默认值
        instance = cls()
        _fields = {f.name for f in fields(cls) if f.init}
        
        # 多级配置加载
        merged_config = {}
        
        # 级别1: 类默认配置 (最低优先级)
        for config_field in _fields:
            if hasattr(instance, config_field):
                merged_config[config_field] = getattr(instance, config_field)
        
        # 级别2: 数据库系统配置
        try:
            from src.database.config_manager import DatabaseConfigManager
            db_config_manager = DatabaseConfigManager()
            system_config = await db_config_manager.get_agent_config(agent_name)
            if system_config:
                merged_config.update(system_config)
                logger.debug(f"加载智能体系统配置: {agent_name}")
        except Exception as e:
            logger.warning(f"加载智能体系统配置失败: {e}")
        
        # 级别3: 用户级配置
        if user_context and user_context.user_id:
            try:
                from src.database.config_manager import DatabaseConfigManager
                db_config_manager = DatabaseConfigManager()
                user_config = await db_config_manager.get_user_agent_config(
                    user_context.user_id, agent_name
                )
                if user_config:
                    merged_config.update(user_config)
                    logger.debug(f"加载用户智能体配置: {user_context.user_id} - {agent_name}")
            except Exception as e:
                logger.warning(f"加载用户智能体配置失败: {e}")
        
        # 级别4: 知识库级配置
        if user_context and user_context.kb_id:
            try:
                from src.database.config_manager import DatabaseConfigManager
                db_config_manager = DatabaseConfigManager()
                kb_config = await db_config_manager.get_kb_agent_config(
                    user_context.kb_id, agent_name
                )
                if kb_config:
                    merged_config.update(kb_config)
                    logger.debug(f"加载知识库智能体配置: {user_context.kb_id} - {agent_name}")
            except Exception as e:
                logger.warning(f"加载知识库智能体配置失败: {e}")
        
        # 级别5: 文件配置
        if agent_name:
            file_config = cls.from_file(agent_name)
            if file_config:
                merged_config.update(file_config)
        
        # 级别6: 运行时配置 (最高优先级)
        configurable = (config.get("configurable") or {}) if config else {}
        if configurable:
            # 过滤掉非配置字段
            for config_field in _fields:
                if config_field in configurable:
                    merged_config[config_field] = configurable[config_field]
        
        # 添加上下文信息
        merged_config["user_context"] = user_context
        if user_context:
            merged_config["permission_context"] = {
                "user_id": user_context.user_id,
                "permissions": list(user_context.permissions),
                "roles": user_context.roles
            }
        
        # 创建并返回配置实例
        logger.debug(f"智能体配置合并完成: {agent_name}, 用户: {user_context.user_id if user_context else 'None'}")
        return cls(**merged_config)

    @classmethod
    def from_file(cls, agent_name: str) -> Configuration:
        """从文件加载配置"""
        config_file_path = Path(f"src/agents/{agent_name}/config.private.yaml")
        file_config = {}
        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, encoding='utf-8') as f:
                    file_config = yaml.safe_load(f) or {}
                    # logger.info(f"从文件加载智能体 {agent_name} 配置: {file_config}")
            except Exception as e:
                logger.error(f"加载智能体配置文件出错: {e}")

        return file_config

    @classmethod
    def save_to_file(cls, config: dict, agent_name: str) -> bool:
        """Save configuration to a YAML file

        Args:
            config: Configuration dictionary to save
            agent_name: Name of the agent to save config for

        Returns:
            True if saving was successful, False otherwise
        """
        try:
            config_file_path = Path(f"src/agents/{agent_name}/config.private.yaml")
            # 确保目录存在
            os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
            with open(config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, indent=2, allow_unicode=True)

            # logger.info(f"智能体 {agent_name} 配置已保存到 {config_file_path}")
            return True
        except Exception as e:
            logger.error(f"保存智能体配置文件出错: {e}")
            return False

    @classmethod
    def to_dict(cls):
        # 创建一个实例来处理 default_factory
        instance = cls()
        confs = {}
        configurable_items = {}
        for f in fields(cls):
            if f.init and not f.metadata.get("hide", False):
                value = getattr(instance, f.name)
                if callable(value) and hasattr(value, "__call__"):
                    confs[f.name] = value()
                else:
                    confs[f.name] = value

                if f.metadata.get("configurable"):
                    configurable_items[f.name] = {
                        "type": f.type.__name__,
                        "name": f.metadata.get("name", f.name),
                        "options": f.metadata.get("options", []),
                        "default": f.default,
                        "description": f.metadata.get("description", ""),
                    }
        confs["configurable_items"] = configurable_items
        return confs


    thread_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={
            "name": "线程ID",
            "configurable": False,
            "description": "用来描述智能体的角色和行为"
        },
    )

    user_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={
            "name": "用户ID",
            "configurable": False,
            "description": "用来描述智能体的角色和行为"
        },
    )

class BaseAgent(ABC):
    """
    重构后的基础智能体类
    
    集成依赖注入、权限控制和统一数据库管理的企业级智能体基类。
    支持向后兼容，同时提供现代化的架构支持。
    """

    name = "base_agent"
    description = "base_agent"
    config_schema: Configuration = Configuration
    requirements: list[str] = []

    def __init__(self, 
                 db_manager: Optional['UnifiedDatabaseManager'] = None,
                 permission_engine: Optional['PermissionEngine'] = None,
                 kb_manager: Optional['KnowledgeBaseManager'] = None,
                 **legacy_kwargs):
        """
        智能体初始化 - 支持依赖注入和向后兼容
        
        Args:
            db_manager: 统一数据库管理器实例  
            permission_engine: 权限引擎实例
            kb_manager: 知识库管理器实例
            **legacy_kwargs: 保持向后兼容的其他参数
        """
        # 1. 依赖注入或延迟初始化
        from src.agents.dependencies import get_agent_dependencies
        self._dependencies = get_agent_dependencies()
        self._db_manager = db_manager
        self._permission_engine = permission_engine  
        self._kb_manager = kb_manager
        
        # 2. 延迟获取的数据库适配器
        self._pg_adapter = None
        self._redis_adapter = None
        self._neo4j_adapter = None
        
        # 3. 保持现有初始化逻辑
        self.check_requirements()
        
        # 4. 初始化工作目录
        self.working_dir = self.create_working_dir()
        
        # 5. 缓存图实例  
        self.graph = None
        
        logger.debug(f"智能体 {self.name} 初始化完成")
    
    def create_working_dir(self) -> str:
        """
        创建智能体工作目录
        
        Returns:
            str: 工作目录路径
        """
        try:
            working_dir = f"/tmp/agents/{self.name}_{uuid.uuid4().hex[:8]}"
            os.makedirs(working_dir, exist_ok=True)
            return working_dir
        except Exception as e:
            logger.warning(f"创建工作目录失败: {e}")
            return "/tmp"
    
    # === 依赖属性 ===
    
    @property
    async def db_manager(self) -> 'UnifiedDatabaseManager':
        """获取统一数据库管理器实例"""
        if self._db_manager is None:
            self._db_manager = await self._dependencies.db_manager
        return self._db_manager
    
    @property
    async def permission_engine(self) -> 'PermissionEngine':
        """获取权限引擎实例"""
        if self._permission_engine is None:
            self._permission_engine = await self._dependencies.permission_engine
        return self._permission_engine
    
    @property
    async def kb_manager(self) -> 'KnowledgeBaseManager':
        """获取知识库管理器实例"""
        if self._kb_manager is None:
            self._kb_manager = await self._dependencies.kb_manager
        return self._kb_manager
    
    @property
    async def pg_adapter(self):
        """获取PostgreSQL适配器"""
        if self._pg_adapter is None:
            db_manager = await self.db_manager
            self._pg_adapter = await db_manager.get_postgresql_adapter('server_db')
        return self._pg_adapter
    
    @property
    async def redis_adapter(self):
        """获取Redis适配器"""
        if self._redis_adapter is None:
            db_manager = await self.db_manager
            self._redis_adapter = await db_manager.get_redis_adapter()
        return self._redis_adapter
    
    @property
    async def neo4j_adapter(self):
        """获取Neo4j适配器"""
        if self._neo4j_adapter is None:
            db_manager = await self.db_manager
            self._neo4j_adapter = await db_manager.get_neo4j_adapter()
        return self._neo4j_adapter
    
    # === 权限检查方法 ===
    
    async def check_user_permission(self, user_context: 'UserContext', permission: str) -> bool:
        """
        检查用户权限
        
        Args:
            user_context: 用户上下文
            permission: 权限字符串
            
        Returns:
            bool: 是否拥有权限
        """
        try:
            from server.auth.permission_framework.resources import AgentResource
            from server.auth.permission_framework.models import Permission
            
            permission_engine = await self.permission_engine
            result = await permission_engine.check_permission_simple(
                user_id=user_context.user_id,
                resource=AgentResource(self.name),
                permission=Permission(permission)
            )
            return result
        except Exception as e:
            logger.error(f"权限检查失败: {e}")
            return False
    
    async def get_user_tools(self, user_context: 'UserContext') -> Dict[str, Any]:
        """
        获取用户可用工具
        
        Args:
            user_context: 用户上下文
            
        Returns:
            Dict[str, Any]: 用户可用工具字典
        """
        try:
            from src.agents.tools_factory import get_all_tools
            all_tools = get_all_tools()
            
            # 过滤用户有权限的工具
            user_tools = {}
            for tool_name, tool in all_tools.items():
                if await self._check_tool_permission(user_context, tool_name):
                    user_tools[tool_name] = tool
            
            # 添加知识库工具
            kb_tools = await self._get_kb_tools(user_context)
            user_tools.update(kb_tools)
            
            return user_tools
        except Exception as e:
            logger.error(f"获取用户工具失败: {e}")
            return {}
    
    async def _check_tool_permission(self, user_context: 'UserContext', tool_name: str) -> bool:
        """
        检查工具权限
        
        Args:
            user_context: 用户上下文
            tool_name: 工具名称
            
        Returns:
            bool: 是否有权限使用工具
        """
        try:
            # 如果是知识库工具，需要检查知识库权限
            if tool_name.startswith("retrieve_"):
                kb_id = tool_name.replace("retrieve_", "")
                return user_context.can_access_kb(kb_id)
            
            # 其他工具的权限检查
            from server.auth.permission_framework.resources import ToolResource
            from server.auth.permission_framework.models import Permission
            
            permission_engine = await self.permission_engine
            return await permission_engine.check_permission_simple(
                user_id=user_context.user_id,
                resource=ToolResource(tool_name),
                permission=Permission.USE
            )
        except Exception as e:
            logger.warning(f"工具权限检查失败: {e}")
            return False
    
    async def _get_kb_tools(self, user_context: 'UserContext') -> Dict[str, Any]:
        """
        获取知识库工具
        
        Args:
            user_context: 用户上下文
            
        Returns:
            Dict[str, Any]: 知识库工具字典
        """
        tools = {}
        try:
            kb_manager = await self.kb_manager
            
            # 获取用户有权限的知识库
            accessible_kbs = await kb_manager.get_user_accessible_kbs(user_context.user_id)
            
            for kb in accessible_kbs:
                tool_name = f"retrieve_{kb.db_id[:8]}"
                description = f"使用 {kb.name} 知识库进行检索"
                
                # 创建知识库检索工具
                async def kb_retriever(query_text: str, kb_id=kb.db_id):
                    return await kb_manager.query_knowledge_base(
                        kb_id, query_text, user_context.user_id
                    )
                
                from langchain.tools import StructuredTool
                tools[tool_name] = StructuredTool.from_function(
                    coroutine=kb_retriever,
                    name=tool_name,
                    description=description
                )
        except Exception as e:
            logger.warning(f"获取知识库工具失败: {e}")
        
        return tools

    async def get_info(self):
        return {
            "name": self.name if hasattr(self, "name") else "Unknown",
            "description": self.description if hasattr(self, "description") else "Unknown",
            "config_schema": self.config_schema.to_dict(),
            "requirements": self.requirements if hasattr(self, "requirements") else [],
            "all_tools": self.all_tools if hasattr(self, "all_tools") else [],
            "has_checkpointer": await self.check_checkpointer(),
            "met_requirements": self.check_requirements(),
        }

    def check_requirements(self):
        if not hasattr(self, "requirements") or not self.requirements:
            return True
        for requirement in self.requirements:
            if requirement not in os.environ:
                raise ValueError(f"没有配置{requirement} 环境变量，请在 src/.env 文件中配置，并重新启动服务")
        return True

    async def stream_values(self, 
                           messages: list[str], 
                           config_schema: RunnableConfig = None, 
                           user_context: Optional['UserContext'] = None,
                           **kwargs):
        """
        流式处理 - 值模式
        
        Args:
            messages: 消息列表
            config_schema: 运行时配置
            user_context: 用户上下文
            **kwargs: 其他参数
        """
        # 权限检查
        if user_context and not await self.check_user_permission(user_context, "execute"):
            raise PermissionError(f"用户无权执行智能体: {self.name}")
        
        # 获取图实例
        if user_context:
            graph = await self.get_graph(config=config_schema, user_context=user_context, **kwargs)
        else:
            graph = await self.get_graph(config=config_schema, **kwargs)
        
        logger.debug(f"stream_values: {config_schema}")
        
        # 确保配置中包含用户上下文
        if config_schema is None:
            config_schema = RunnableConfig(configurable={})
        if user_context:
            config_schema["configurable"]["user_context"] = user_context
        
        async for event in graph.astream({"messages": messages}, stream_mode="values", config=config_schema):
            yield event["messages"]

    async def stream_messages(self, 
                             messages: list[str], 
                             config_schema: RunnableConfig = None,
                             user_context: Optional['UserContext'] = None,
                             **kwargs):
        """
        流式处理 - 消息模式
        
        Args:
            messages: 消息列表
            config_schema: 运行时配置
            user_context: 用户上下文
            **kwargs: 其他参数
        """
        # 权限检查
        if user_context and not await self.check_user_permission(user_context, "execute"):
            raise PermissionError(f"用户无权执行智能体: {self.name}")
        
        # 获取图实例
        if user_context:
            graph = await self.get_graph(config=config_schema, user_context=user_context, **kwargs)
        else:
            graph = await self.get_graph(config=config_schema, **kwargs)
        
        logger.debug(f"stream_messages: {config_schema}")
        
        # 确保配置中包含用户上下文
        if config_schema is None:
            config_schema = RunnableConfig(configurable={})
        if user_context:
            config_schema["configurable"]["user_context"] = user_context

        async for msg, metadata in graph.astream({"messages": messages}, stream_mode="messages", config=config_schema):
            yield msg, metadata

    async def check_checkpointer(self):
        app = await self.get_graph()
        if not hasattr(app, "checkpointer") or app.checkpointer is None:
            logger.warning(f"智能体 {self.name} 的 Graph 未配置 checkpointer，无法获取历史记录")
            return False
        return True

    async def get_history(self, user_id, thread_id) -> list[dict]:
        """获取历史消息"""
        try:
            app = await self.get_graph()

            if not await self.check_checkpointer():
                return []

            config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
            state = await app.aget_state(config)

            result = []
            if state:
                messages = state.values.get('messages', [])
                for msg in messages:
                    if hasattr(msg, 'model_dump'):
                        msg_dict = msg.model_dump()  # 转换成字典
                    else:
                        msg_dict = dict(msg) if hasattr(msg, '__dict__') else {"content": str(msg)}
                    result.append(msg_dict)

            return result

        except Exception as e:
            logger.error(f"获取智能体 {self.name} 历史消息出错: {e}")
            return []
    
    async def _get_checkpointer(self):
        """
        获取检查点存储器 - 集成统一数据库管理系统
        
        Returns:
            检查点存储器实例
        """
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            
            # 使用统一数据库管理器获取连接
            pg_adapter = await self.pg_adapter
            connection = await pg_adapter.get_connection()
            
            return AsyncSqliteSaver(connection)
        except Exception as e:
            logger.warning(f"获取检查点存储器失败: {e}")
            return None

    @abstractmethod
    async def get_graph(self, config: RunnableConfig = None, user_context: Optional['UserContext'] = None, **kwargs) -> CompiledStateGraph:
        """
        获取并编译对话图实例。
        必须确保在编译时设置 checkpointer，否则将无法获取历史记录。
        例如: graph = workflow.compile(checkpointer=sqlite_checkpointer)
        """
        pass
