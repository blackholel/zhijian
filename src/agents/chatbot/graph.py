import os
import uuid
from typing import Any, TYPE_CHECKING, Optional
from pathlib import Path
from datetime import datetime, timezone

import sqlite3
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver, aiosqlite

from src import config as sys_config
from src.utils import logger
from src.agents.registry import State, BaseAgent
from src.agents.utils import load_chat_model, get_cur_time_with_utc
from src.agents.chatbot.configuration import ChatbotConfiguration
from src.agents.tools_factory import get_all_tools

if TYPE_CHECKING:
    from src.agents.context import UserContext

class ChatbotAgent(BaseAgent):
    """
    重构后的聊天机器人智能体
    
    集成权限控制、用户上下文和统一数据库管理的企业级聊天机器人。
    支持动态工具加载、权限过滤和个性化配置。
    """
    
    name = "chatbot"
    description = "权限感知的聊天机器人智能体，支持多轮对话、工具调用和个性化配置"
    requirements = ["TAVILY_API_KEY", "ZHIPUAI_API_KEY"]
    config_schema = ChatbotConfiguration

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 图实例缓存在父类中管理
        self.workdir = Path(sys_config.save_dir) / "agents" / self.name
        self.workdir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"ChatbotAgent 初始化完成，工作目录: {self.workdir}")

    async def _get_user_tools(self, user_context: Optional['UserContext'] = None):
        """
        获取用户可用工具 - 权限感知
        
        Args:
            user_context: 用户上下文，用于权限过滤
            
        Returns:
            list: 用户可用工具列表
        """
        if user_context:
            # 使用权限感知的工具获取
            try:
                user_tools = await self.get_user_tools(user_context)
                tool_list = list(user_tools.values())
                logger.info(f"用户 {user_context.user_id} 可用工具: {list(user_tools.keys())}")
                return tool_list
            except Exception as e:
                logger.warning(f"获取用户工具失败，使用降级方案: {e}")
                return self._get_tools_legacy([])
        else:
            # 降级到旧版本工具获取（向后兼容）
            return self._get_tools_legacy([])
    
    def _get_tools_legacy(self, tools: list[str]):
        """
        旧版本工具获取 - 向后兼容
        
        Args:
            tools: 工具名称列表
            
        Returns:
            list: 工具实例列表
        """
        platform_tools = get_all_tools()
        if tools is None or not isinstance(tools, list) or len(tools) == 0:
            # 默认不使用任何工具
            logger.info("未配置工具或配置为空，不使用任何工具")
            return []
        else:
            # 使用配置中指定的工具
            tool_names = [tool for tool in platform_tools.keys() if tool in tools]
            logger.info(f"使用工具: {tool_names}")
            return [platform_tools[tool] for tool in tool_names]

    async def llm_call(self, state: State, config: RunnableConfig = None) -> dict[str, Any]:
        """
        调用 LLM 模型 - 权限感知版本
        
        Args:
            state: 对话状态
            config: 运行时配置
            
        Returns:
            dict: 包含响应消息的状态更新
        """
        # 获取用户上下文
        user_context = config.get("configurable", {}).get("user_context") if config else None
        
        # 权限检查
        if user_context and not await self.check_user_permission(user_context, "execute"):
            raise PermissionError(f"用户无权执行智能体: {self.name}")
        
        # 获取配置（支持用户上下文）
        conf = await self.config_schema.from_runnable_config(
            config, agent_name=self.name, user_context=user_context
        )

        # 构建系统提示
        system_prompt = f"{conf.system_prompt} 当前时间: {get_cur_time_with_utc()}"
        
        # 加载模型
        model = load_chat_model(conf.model)

        # 获取用户可用工具
        user_tools = await self._get_user_tools(user_context)
        if user_tools:
            model = model.bind_tools(user_tools)
            logger.debug(f"为用户 {user_context.user_id if user_context else 'anonymous'} 绑定了 {len(user_tools)} 个工具")

        # 调用模型
        try:
            res = await model.ainvoke(
                [{"role": "system", "content": system_prompt}, *state["messages"]]
            )
            return {"messages": [res]}
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            # 返回错误响应
            from langchain_core.messages import AIMessage
            error_msg = AIMessage(content=f"抱歉，处理您的请求时出现了错误: {str(e)}")
            return {"messages": [error_msg]}

    async def get_graph(self, 
                       config: RunnableConfig = None, 
                       user_context: Optional['UserContext'] = None, 
                       **kwargs):
        """
        获取聊天机器人图 - 权限上下文感知
        
        Args:
            config: 运行时配置
            user_context: 用户上下文
            **kwargs: 其他参数
            
        Returns:
            CompiledStateGraph: 编译后的状态图
        """
        # 权限检查
        if user_context and not await self.check_user_permission(user_context, "access"):
            raise PermissionError(f"用户无权访问智能体: {self.name}")
        
        # 检查是否需要重新构建图（基于用户上下文）
        cache_key = f"graph_{user_context.user_id if user_context else 'default'}"
        if hasattr(self, '_graph_cache') and cache_key in self._graph_cache:
            return self._graph_cache[cache_key]
        
        # 初始化图缓存
        if not hasattr(self, '_graph_cache'):
            self._graph_cache = {}

        # 创建状态图
        workflow = StateGraph(State, config_schema=self.config_schema)
        workflow.add_node("chatbot", self.llm_call)
        
        # 获取用户可用工具
        user_tools = await self._get_user_tools(user_context)
        
        if user_tools:
            # 只有当用户有可用工具时才添加工具节点
            workflow.add_node("tools", ToolNode(tools=user_tools))
            
            # 设置条件边
            workflow.add_edge(START, "chatbot")
            workflow.add_conditional_edges("chatbot", tools_condition)
            workflow.add_edge("tools", "chatbot")
        else:
            # 无工具的简单流程
            workflow.add_edge(START, "chatbot")
        
        workflow.add_edge("chatbot", END)

        # 创建检查点存储器
        try:
            # 使用统一数据库管理器获取检查点
            checkpointer = await self._get_checkpointer()
            if checkpointer:
                graph = workflow.compile(checkpointer=checkpointer)
            else:
                # 降级处理：使用本地SQLite
                sqlite_checkpointer = AsyncSqliteSaver(await self.get_async_conn())
                graph = workflow.compile(checkpointer=sqlite_checkpointer)
            
            # 缓存图实例
            self._graph_cache[cache_key] = graph
            
            logger.debug(f"成功构建聊天机器人图，用户: {user_context.user_id if user_context else 'anonymous'}，工具数量: {len(user_tools)}")
            
            return graph
            
        except Exception as e:
            logger.error(f"构建图时出错: {e}")
            # 降级处理：返回无检查点的图
            graph = workflow.compile()
            self._graph_cache[cache_key] = graph
            
            logger.warning(f"使用降级模式构建图（无历史记录功能）")
            return graph

    async def get_async_conn(self) -> aiosqlite.Connection:
        """获取异步数据库连接"""
        return await aiosqlite.connect(os.path.join(self.workdir, "aio_history.db"))

    async def get_aio_memory(self) -> AsyncSqliteSaver:
        """获取异步存储实例"""
        return AsyncSqliteSaver(await self.get_async_conn())

def main():
    agent = ChatbotAgent(ChatbotConfiguration())

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents.utils import agent_cli
    agent_cli(agent, config)


if __name__ == "__main__":
    main()
    # asyncio.run(main())
