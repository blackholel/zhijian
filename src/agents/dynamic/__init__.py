"""动态智能体 - 基于数据库配置运行"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src import config as sys_config
from src.agents.common import BaseAgent, BaseContext, load_chat_model
from src.agents.common.middlewares import UserMCPToolsMiddleware, inject_attachment_context
from src.agents.common.tools import get_kb_based_tools
from src.agents.chatbot.tools import get_tools as get_chatbot_tools
from src.storage.db.models import Agent as AgentModel
from src.utils import logger


@dataclass(kw_only=True)
class DynamicContext(BaseContext):
    """动态智能体的上下文，从数据库配置初始化"""

    tools: list[str] = field(default_factory=list)
    mcps: list[str] = field(default_factory=list)
    knowledges: list[str] = field(default_factory=list)


class DynamicAgent(BaseAgent):
    """
    动态智能体 - 基于数据库配置运行

    采用委托模式：
    1. 使用 base_agent_id 指定的底层智能体的图结构
    2. 运行时注入数据库中的配置（system_prompt, tools, mcps, knowledges）
    3. 复用现有中间件系统
    """

    def __init__(self, db_agent: AgentModel):
        self._db_agent = db_agent
        self.name = db_agent.name
        self.description = db_agent.description or ""
        self.capabilities = db_agent.capabilities or []
        self.context_schema = DynamicContext
        self._module_name = db_agent.agent_id

        # 调用父类初始化
        super().__init__()

    @property
    def module_name(self) -> str:
        return self._module_name

    @property
    def id(self) -> str:
        return self._db_agent.agent_id

    async def get_info(self):
        """返回智能体信息"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "examples": self._db_agent.examples or [],
            "configurable_items": {},  # 动态智能体的配置在数据库中
            "has_checkpointer": await self.check_checkpointer(),
            "capabilities": self.capabilities,
            "agent_type": self._db_agent.agent_type,
            "base_agent_id": self._db_agent.base_agent_id,
        }

    async def get_config(self):
        """返回数据库中的配置"""
        return DynamicContext(
            system_prompt=self._db_agent.system_prompt or "You are a helpful assistant.",
            model=self._db_agent.model or sys_config.default_model,
            tools=self._db_agent.tools or [],
            mcps=self._db_agent.mcps or [],
            knowledges=self._db_agent.knowledges or [],
        )

    async def get_tools(self):
        """根据数据库配置获取工具"""
        selected_tools = []

        # 1. 基础工具
        if self._db_agent.tools:
            all_basic_tools = get_chatbot_tools()
            tools_map = {t.name: t for t in all_basic_tools}
            for tool_name in self._db_agent.tools:
                if tool_name in tools_map:
                    selected_tools.append(tools_map[tool_name])

        # 2. 知识库工具
        if self._db_agent.knowledges:
            kb_tools = get_kb_based_tools(db_names=self._db_agent.knowledges)
            selected_tools.extend(kb_tools)

        return selected_tools

    async def get_graph(self, **kwargs):
        """构建图 - 基于数据库配置"""
        if self.graph:
            return self.graph

        # 从数据库配置获取参数
        system_prompt = self._db_agent.system_prompt or "You are a helpful assistant."
        model_name = self._db_agent.model or sys_config.default_model

        # 构建中间件列表
        middleware = [
            UserMCPToolsMiddleware(),  # 运行时 MCP 工具注入
            inject_attachment_context,  # 附件上下文注入
            ModelRetryMiddleware(),
        ]

        # 使用 create_agent 创建智能体
        graph = create_agent(
            model=load_chat_model(model_name),
            tools=await self.get_tools(),
            system_prompt=system_prompt,
            middleware=middleware,
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        logger.info(f"DynamicAgent {self.id} graph built successfully")
        return graph

    async def stream_messages(self, messages, input_context=None, **kwargs):
        """流式消息处理 - 注入数据库配置"""
        # 合并数据库配置和运行时配置
        db_context = {
            "tools": self._db_agent.tools or [],
            "mcps": self._db_agent.mcps or [],
            "knowledges": self._db_agent.knowledges or [],
        }

        merged_context = {**db_context, **(input_context or {})}

        async for msg, metadata in super().stream_messages(messages, input_context=merged_context, **kwargs):
            yield msg, metadata

    def load_metadata(self) -> dict:
        """动态智能体从数据库加载元数据"""
        return {
            "name": self.name,
            "description": self.description,
            "examples": self._db_agent.examples or [],
        }
