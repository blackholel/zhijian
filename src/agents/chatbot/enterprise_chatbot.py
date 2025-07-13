"""
企业级聊天机器人智能体
集成权限系统、数据库管理和知识库系统
"""

import os
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver, aiosqlite

from src import config as sys_config
from src.utils import logger
from src.agents.registry import State
from src.agents.utils import load_chat_model, get_cur_time_with_utc
from src.agents.enterprise_base import (
    EnterpriseAgent, 
    EnterpriseAgentContext, 
    EnterpriseConfiguration
)
from src.agents.enterprise_tools import EnterpriseToolsManager
from src.agents.chatbot.configuration import ChatbotConfiguration


@dataclass(kw_only=True)
class EnterpriseChatbotConfiguration(EnterpriseConfiguration):
    """企业级聊天机器人配置"""
    
    system_prompt: str = field(
        default="你是一个企业级智能助手，可以帮助用户处理各种问题。你拥有访问知识库、数据库查询、文件操作等多种能力。",
        metadata={
            "name": "系统提示词",
            "configurable": True,
            "description": "用来描述智能体的角色和行为"
        }
    )
    
    model: str = field(
        default="zhipu/glm-4-plus",
        metadata={
            "name": "智能体模型",
            "configurable": True,
            "options": [],
            "description": "智能体的驱动模型"
        }
    )
    
    enable_knowledge_retrieval: bool = field(
        default=True,
        metadata={
            "name": "启用知识检索",
            "configurable": True,
            "description": "是否启用知识库检索功能"
        }
    )
    
    enable_database_query: bool = field(
        default=False,
        metadata={
            "name": "启用数据库查询",
            "configurable": True,
            "description": "是否启用数据库查询功能"
        }
    )
    
    enable_file_operations: bool = field(
        default=False,
        metadata={
            "name": "启用文件操作",
            "configurable": True,
            "description": "是否启用文件操作功能"
        }
    )
    
    enable_graph_query: bool = field(
        default=False,
        metadata={
            "name": "启用图查询",
            "configurable": True,
            "description": "是否启用知识图谱查询功能"
        }
    )
    
    max_knowledge_bases: int = field(
        default=10,
        metadata={
            "name": "最大知识库数量",
            "configurable": True,
            "description": "单次查询时最大的知识库数量"
        }
    )
    
    # 继承基类的必需权限
    required_permissions: List[str] = field(
        default_factory=lambda: ["chat", "read"],
        metadata={
            "name": "必需权限",
            "configurable": False,
            "description": "智能体运行所需的权限列表"
        }
    )


class EnterpriseChatbotAgent(EnterpriseAgent):
    """企业级聊天机器人智能体"""
    
    name = "enterprise_chatbot"
    description = "企业级聊天机器人，集成权限控制、知识库检索、数据库查询等功能"
    requirements = ["ZHIPUAI_API_KEY"]
    config_schema = EnterpriseChatbotConfiguration
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.workdir = Path(sys_config.save_dir) / "agents" / self.name
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.tools_manager: Optional[EnterpriseToolsManager] = None
    
    async def initialize_tools_manager(self, context: EnterpriseAgentContext):
        """初始化工具管理器"""
        if not self.tools_manager:
            self.tools_manager = EnterpriseToolsManager(self.db_manager)
            await self.tools_manager.initialize()
    
    async def get_available_tools(self, context: EnterpriseAgentContext, 
                                config: EnterpriseChatbotConfiguration):
        """获取可用工具列表"""
        if not self.tools_manager:
            await self.initialize_tools_manager(context)
        
        # 根据配置和权限过滤工具
        available_tools = []
        
        # 获取用户可用的工具
        user_tools = await self.tools_manager.get_available_tools(context)
        
        # 根据配置启用相应工具
        if config.enable_knowledge_retrieval and "knowledge_retrieval" in user_tools:
            available_tools.extend(
                self.tools_manager.get_langchain_tools(context)
            )
        
        if config.enable_database_query and "database_query" in user_tools:
            # 数据库查询工具已包含在get_langchain_tools中
            pass
        
        if config.enable_file_operations and "file_operation" in user_tools:
            # 文件操作工具已包含在get_langchain_tools中
            pass
        
        if config.enable_graph_query and "graph_query" in user_tools:
            # 图查询工具已包含在get_langchain_tools中
            pass
        
        return available_tools
    
    async def create_system_prompt(self, context: EnterpriseAgentContext,
                                 config: EnterpriseChatbotConfiguration) -> str:
        """创建系统提示词"""
        base_prompt = config.system_prompt
        
        # 添加当前时间
        time_info = f"当前时间: {get_cur_time_with_utc()}"
        
        # 获取用户可访问的知识库
        accessible_kbs = await self.get_accessible_knowledge_bases(context, config)
        
        # 构建知识库信息
        kb_info = ""
        if accessible_kbs:
            kb_info = f"\n\n你可以访问以下知识库: {', '.join(accessible_kbs)}"
            if config.enable_knowledge_retrieval:
                kb_info += "\n你可以使用knowledge_retrieval工具从这些知识库中检索信息。"
        
        # 构建工具信息
        tool_info = ""
        if config.enable_database_query:
            tool_info += "\n- 数据库查询: 可以查询系统信息"
        if config.enable_file_operations:
            tool_info += "\n- 文件操作: 可以查看知识库中的文件"
        if config.enable_graph_query:
            tool_info += "\n- 图查询: 可以查询知识图谱"
        
        if tool_info:
            tool_info = f"\n\n你拥有以下工具能力:{tool_info}"
        
        # 安全提示
        security_info = f"""

安全提示:
- 你正在为用户 {context.user_id} 提供服务
- 所有操作都会被审计记录
- 请遵循权限控制，只访问用户有权限的资源
- 保护用户隐私和数据安全"""
        
        return f"{base_prompt}\n\n{time_info}{kb_info}{tool_info}{security_info}"
    
    async def llm_call(self, state: State, config: RunnableConfig = None,
                      context: EnterpriseAgentContext = None) -> dict[str, Any]:
        """LLM调用节点"""
        if not context:
            # 如果没有提供context，创建一个默认的
            context = EnterpriseAgentContext(
                user_id="anonymous",
                session_id=str(uuid.uuid4()),
                thread_id=str(uuid.uuid4())
            )
        
        # 解析配置
        conf = self.config_schema.from_runnable_config(config, agent_name=self.name)
        
        # 初始化企业级组件
        await self.initialize_enterprise_components()
        
        # 创建系统提示词
        system_prompt = await self.create_system_prompt(context, conf)
        
        # 加载模型
        model = load_chat_model(conf.model)
        
        # 获取可用工具
        tools = await self.get_available_tools(context, conf)
        
        if tools:
            model = model.bind_tools(tools)
        
        # 记录LLM调用
        await self.log_agent_action(context, "llm_call", {
            "message_count": len(state["messages"]),
            "tools_count": len(tools),
            "model": conf.model
        })
        
        try:
            # 调用模型
            messages = [{"role": "system", "content": system_prompt}] + state["messages"]
            response = await model.ainvoke(messages)
            
            # 记录响应
            await self.log_agent_action(context, "llm_response", {
                "response_type": type(response).__name__,
                "has_tool_calls": bool(getattr(response, 'tool_calls', None))
            })
            
            return {"messages": [response]}
            
        except Exception as e:
            # 记录错误
            await self.log_agent_action(context, "llm_error", {
                "error": str(e)
            })
            raise
    
    async def get_enterprise_graph(self, context: EnterpriseAgentContext,
                                 config: RunnableConfig = None):
        """获取企业级图"""
        if self.graph:
            return self.graph
        
        # 初始化企业级组件
        await self.initialize_enterprise_components()
        await self.initialize_tools_manager(context)
        
        # 创建状态图
        workflow = StateGraph(State, config_schema=self.config_schema)
        
        # 添加LLM节点
        async def llm_node(state: State):
            return await self.llm_call(state, config, context)
        
        workflow.add_node("chatbot", llm_node)
        
        # 添加工具节点
        conf = self.config_schema.from_runnable_config(config, agent_name=self.name)
        tools = await self.get_available_tools(context, conf)
        
        if tools:
            workflow.add_node("tools", ToolNode(tools))
        
        # 添加边
        workflow.add_edge(START, "chatbot")
        
        if tools:
            workflow.add_conditional_edges(
                "chatbot",
                tools_condition,
            )
            workflow.add_edge("tools", "chatbot")
        
        workflow.add_edge("chatbot", END)
        
        # 设置检查点
        try:
            sqlite_checkpointer = AsyncSqliteSaver(await self.get_async_conn())
            graph = workflow.compile(checkpointer=sqlite_checkpointer)
            self.graph = graph
            return graph
        except Exception as e:
            logger.error(f"设置检查点时出错: {e}")
            graph = workflow.compile()
            self.graph = graph
            return graph
    
    async def get_async_conn(self) -> aiosqlite.Connection:
        """获取异步数据库连接"""
        return await aiosqlite.connect(os.path.join(self.workdir, "enterprise_history.db"))
    
    async def get_enterprise_history(self, context: EnterpriseAgentContext) -> List[Dict]:
        """获取企业级历史记录"""
        try:
            # 检查权限
            if not await self.validate_permissions(context, self.config_schema()):
                return []
            
            # 获取历史记录
            app = await self.get_enterprise_graph(context)
            
            if not await self.check_checkpointer():
                return []
            
            config = {
                "configurable": {
                    "thread_id": context.thread_id,
                    "user_id": context.user_id
                }
            }
            
            state = await app.aget_state(config)
            
            result = []
            if state:
                messages = state.values.get('messages', [])
                for msg in messages:
                    if hasattr(msg, 'model_dump'):
                        msg_dict = msg.model_dump()
                    else:
                        msg_dict = dict(msg) if hasattr(msg, '__dict__') else {"content": str(msg)}
                    result.append(msg_dict)
            
            # 记录历史查询
            await self.log_agent_action(context, "history_query", {
                "message_count": len(result)
            })
            
            return result
            
        except Exception as e:
            logger.error(f"获取企业级历史记录出错: {e}")
            return []
    
    async def stream_enterprise_messages(self, messages: List[BaseMessage],
                                       context: EnterpriseAgentContext,
                                       config: RunnableConfig = None):
        """企业级消息流式处理"""
        # 验证权限
        conf = self.config_schema.from_runnable_config(config, agent_name=self.name)
        if not await self.validate_permissions(context, conf):
            raise PermissionError(f"用户 {context.user_id} 没有使用智能体 {self.name} 的权限")
        
        # 创建会话
        session_data = await self.create_secure_session(context)
        
        # 获取图
        graph = await self.get_enterprise_graph(context, config)
        
        # 记录开始流式处理
        await self.log_agent_action(context, "stream_started", {
            "message_count": len(messages),
            "session_id": context.session_id
        })
        
        try:
            # 流式处理
            async for msg, metadata in graph.astream(
                {"messages": messages}, 
                stream_mode="messages",
                config={
                    "configurable": {
                        "thread_id": context.thread_id,
                        "user_id": context.user_id
                    }
                }
            ):
                yield msg, metadata
                
        except Exception as e:
            # 记录错误
            await self.log_agent_action(context, "stream_error", {
                "error": str(e),
                "session_id": context.session_id
            })
            raise
        finally:
            # 记录结束
            await self.log_agent_action(context, "stream_completed", {
                "session_id": context.session_id
            })
    
    async def get_enterprise_info(self) -> Dict[str, Any]:
        """获取企业级智能体信息"""
        base_info = await super().get_enterprise_info()
        
        # 添加聊天机器人特有信息
        chatbot_info = {
            **base_info,
            "agent_type": "enterprise_chatbot",
            "supported_tools": [
                "knowledge_retrieval",
                "database_query", 
                "file_operation",
                "graph_query"
            ],
            "configurable_features": [
                "enable_knowledge_retrieval",
                "enable_database_query",
                "enable_file_operations",
                "enable_graph_query"
            ]
        }
        
        return chatbot_info


def main():
    """测试函数"""
    import asyncio
    
    async def test_enterprise_chatbot():
        # 创建智能体
        agent = EnterpriseChatbotAgent()
        
        # 创建上下文
        context = EnterpriseAgentContext(
            user_id="test_user",
            session_id=str(uuid.uuid4()),
            thread_id=str(uuid.uuid4())
        )
        
        # 获取信息
        info = await agent.get_enterprise_info()
        print(f"智能体信息: {info}")
        
        # 测试消息处理
        messages = [HumanMessage(content="你好，请介绍一下你的功能")]
        
        config = {
            "configurable": {
                "thread_id": context.thread_id,
                "user_id": context.user_id
            }
        }
        
        print("开始流式处理...")
        async for msg, metadata in agent.stream_enterprise_messages(
            messages, context, config
        ):
            if hasattr(msg, 'content'):
                print(f"消息: {msg.content}")
    
    asyncio.run(test_enterprise_chatbot())


if __name__ == "__main__":
    main() 