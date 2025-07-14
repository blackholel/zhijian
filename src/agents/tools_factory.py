import json
import asyncio
from collections.abc import Callable
from typing import Annotated, Any, Dict, Set, TYPE_CHECKING, Optional

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, tool
from langchain_tavily import TavilySearch

from src import config, graph_base, knowledge_base
from src.utils import logger

if TYPE_CHECKING:
    from server.auth.permission_framework.engine import PermissionEngine
    from src.knowledge_base.manager import KnowledgeBaseManager
    from src.agents.context import UserContext


class KnowledgeRetrieverModel(BaseModel):
    query_text: str = Field(
        description=(
            "查询的关键词，查询的时候，应该尽量以可能帮助回答这个问题的关键词进行查询，"
            "不要直接使用用户的原始输入去查询。"
        )
    )

def get_all_tools():
    """获取所有工具"""
    tools = _TOOLS_REGISTRY.copy()

    # 获取所有知识库
    for db_Id, retrieve_info in knowledge_base.get_retrievers().items():
        name = f"retrieve_{db_Id[:8]}" # Deepseek does not support non-alphanumeric characters in tool names
        description = (
            f"使用 {retrieve_info['name']} 知识库进行检索。\n"
            f"下面是这个知识库的描述：\n{retrieve_info['description']}"
        )

        # 创建异步工具，确保正确处理异步检索器
        async def async_retriever_wrapper(query_text: str, db_id=db_Id):
            """异步检索器包装函数"""
            retriever = retrieve_info["retriever"]
            try:
                if asyncio.iscoroutinefunction(retriever):
                    result = await retriever(query_text)
                else:
                    result = retriever(query_text)
                return result
            except Exception as e:
                logger.error(f"Error in retriever {db_id}: {e}")
                return f"检索失败: {str(e)}"

        # 使用 StructuredTool.from_function 创建异步工具
        tools[name] = StructuredTool.from_function(
            coroutine=async_retriever_wrapper,  # 指定为协程
            name=name,
            description=description,
            args_schema=KnowledgeRetrieverModel
        )

    return tools

class BaseToolOutput:
    """
    LLM 要求 Tool 的输出为 str，但 Tool 用在别处时希望它正常返回结构化数据。
    只需要将 Tool 返回值用该类封装，能同时满足两者的需要。
    基类简单的将返回值字符串化，或指定 format="json" 将其转为 json。
    用户也可以继承该类定义自己的转换方法。
    """

    def __init__(
        self,
        data: Any,
        format: str | Callable | None = None,
        data_alias: str = "",
        **extras: Any,
    ) -> None:
        self.data = data
        self.format = format
        self.extras = extras
        if data_alias:
            setattr(self, data_alias, property(lambda obj: obj.data))

    def __str__(self) -> str:
        if self.format == "json":
            return json.dumps(self.data, ensure_ascii=False, indent=2)
        elif callable(self.format):
            return self.format(self)
        else:
            return str(self.data)

@tool
def calculator(a: float, b: float, operation: str) -> float:
    """Calculate two numbers. operation: add, subtract, multiply, divide"""
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        return a / b
    else:
        raise ValueError(f"Invalid operation: {operation}, only support add, subtract, multiply, divide")

@tool
def query_knowledge_graph(query: Annotated[str, "The keyword to query knowledge graph."]):
    """Use this to query knowledge graph."""
    return graph_base.query_node(query, hops=2)




_TOOLS_REGISTRY = {
    "Calculator": calculator,
    "QueryKnowledgeGraph": query_knowledge_graph,
}

if config.enable_web_search:
    _TOOLS_REGISTRY["WebSearchWithTavily"] = TavilySearch(max_results=10)


# === 权限感知工具工厂 ===

class PermissionAwareToolsFactory:
    """
    权限感知的工具工厂
    
    支持基于用户权限的动态工具过滤，集成知识库权限检查和工具缓存机制。
    """
    
    def __init__(self, 
                 permission_engine: 'PermissionEngine',
                 kb_manager: 'KnowledgeBaseManager'):
        """
        初始化权限感知工具工厂
        
        Args:
            permission_engine: 权限引擎实例
            kb_manager: 知识库管理器实例
        """
        self.permission_engine = permission_engine
        self.kb_manager = kb_manager
        self._tool_registry = {}
        self._cache = {}
        self._cache_ttl = 300  # 5分钟缓存
        
        logger.debug("权限感知工具工厂初始化完成")
    
    async def get_user_tools(self, user_context: 'UserContext') -> Dict[str, Any]:
        """
        获取用户可用工具 - 权限过滤
        
        Args:
            user_context: 用户上下文
            
        Returns:
            Dict[str, Any]: 用户可用工具字典
        """
        import time
        start_time = time.time()
        
        # 构建缓存键 - 包含权限哈希以确保权限变更时缓存失效
        permissions_hash = hash(str(sorted(user_context.permissions))) if user_context.permissions else 0
        cache_key = f"user_tools:{user_context.user_id}:{user_context.kb_id or 'all'}:{permissions_hash}"
        
        # 1. 缓存检查
        if cache_key in self._cache:
            cached_tools, timestamp = self._cache[cache_key]
            if asyncio.get_event_loop().time() - timestamp < self._cache_ttl:
                duration = (time.time() - start_time) * 1000
                logger.debug(f"从缓存获取用户工具: {user_context.user_id} (耗时: {duration:.2f}ms)")
                return cached_tools
        
        tools = {}
        
        try:
            # 2. 基础工具权限检查
            base_tools = await self._get_base_tools()
            for tool_name, tool in base_tools.items():
                if await self._check_tool_permission(user_context, tool_name):
                    tools[tool_name] = tool
                    logger.debug(f"用户 {user_context.user_id} 获得工具权限: {tool_name}")
            
            # 3. 知识库工具动态生成
            kb_tools = await self._get_kb_tools(user_context)
            tools.update(kb_tools)
            
            # 4. 缓存结果
            self._cache[cache_key] = (tools, asyncio.get_event_loop().time())
            
            # 5. 性能监控和日志
            duration = (time.time() - start_time) * 1000
            logger.info(f"用户 {user_context.user_id} 可用工具: {list(tools.keys())} (耗时: {duration:.2f}ms, 缓存键: {cache_key[:50]}...)")
            
            # 6. 异步清理过期缓存
            asyncio.create_task(self._cleanup_expired_cache())
            
            return tools
            
        except Exception as e:
            logger.error(f"获取用户工具失败: {e}")
            # 返回基本工具作为降级处理
            return await self._get_base_tools_safe()
    
    async def _get_base_tools(self) -> Dict[str, Any]:
        """
        获取基础工具
        
        Returns:
            Dict[str, Any]: 基础工具字典
        """
        tools = {}
        
        # 1. 数学计算工具
        tools["calculator"] = calculator
        
        # 2. 知识图谱查询工具
        tools["query_knowledge_graph"] = query_knowledge_graph
        
        # 3. 网络搜索工具（如果启用）
        if config.enable_web_search:
            tools["web_search"] = TavilySearch(max_results=10)
        
        return tools
    
    async def _get_base_tools_safe(self) -> Dict[str, Any]:
        """
        安全获取基础工具（降级处理）
        
        Returns:
            Dict[str, Any]: 基础工具字典
        """
        try:
            return {
                "calculator": calculator,
                "query_knowledge_graph": query_knowledge_graph
            }
        except Exception as e:
            logger.error(f"获取基础工具失败: {e}")
            return {}
    
    async def _cleanup_expired_cache(self):
        """异步清理过期缓存"""
        try:
            current_time = asyncio.get_event_loop().time()
            expired_keys = [
                key for key, (_, timestamp) in self._cache.items()
                if current_time - timestamp > self._cache_ttl
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.debug(f"清理了 {len(expired_keys)} 个过期工具缓存项")
        except Exception as e:
            logger.warning(f"缓存清理失败: {e}")
    
    async def _get_kb_tools(self, user_context: 'UserContext') -> Dict[str, Any]:
        """
        获取知识库工具 - 动态生成
        
        Args:
            user_context: 用户上下文
            
        Returns:
            Dict[str, Any]: 知识库工具字典
        """
        tools = {}
        
        try:
            # 获取用户有权限的知识库
            logger.debug(f"获取用户 {user_context.user_id} 的知识库工具...")
            accessible_kbs = await self.kb_manager.get_user_accessible_kbs(user_context.user_id)
            logger.debug(f"获取到 {len(accessible_kbs) if accessible_kbs else 0} 个知识库")
            
            for kb in accessible_kbs:
                # 防御性类型检查和属性提取
                if isinstance(kb, str):
                    # 如果返回的是字符串而不是对象，记录警告并跳过
                    logger.warning(f"知识库对象是字符串类型，跳过: {kb}")
                    continue
                elif not hasattr(kb, 'db_id'):
                    logger.warning(f"知识库对象缺少db_id属性: {type(kb)} - {kb}")
                    continue
                
                # 安全获取知识库属性
                try:
                    kb_id = getattr(kb, 'db_id', None)
                    kb_name = getattr(kb, 'name', 'Unknown')
                    kb_description = getattr(kb, 'description', None)
                    
                    if not kb_id:
                        logger.warning(f"知识库对象db_id为空: {type(kb)}")
                        continue
                        
                except Exception as attr_e:
                    logger.error(f"获取知识库属性失败: {attr_e}, 对象类型: {type(kb)}")
                    continue
                
                # 检查特定知识库的读取权限
                if await self._check_kb_permission(user_context, kb_id, "read"):
                    tool_name = f"retrieve_{kb_id[:8]}"
                    description = f"检索 {kb_name} 知识库内容\n知识库描述: {kb_description or '无描述'}"
                    
                    # 创建异步检索函数
                    async def kb_retriever(query_text: str, kb_id=kb_id):
                        try:
                            return await self.kb_manager.query_knowledge_base(
                                kb_id, query_text, user_context.user_id
                            )
                        except Exception as e:
                            logger.error(f"知识库检索失败 {kb_id}: {e}")
                            return f"检索失败: {str(e)}"
                    
                    tools[tool_name] = StructuredTool.from_function(
                        coroutine=kb_retriever,
                        name=tool_name,
                        description=description,
                        args_schema=KnowledgeRetrieverModel
                    )
                    
                    logger.debug(f"为用户 {user_context.user_id} 生成知识库工具: {tool_name}")
        
        except Exception as e:
            logger.warning(f"获取知识库工具失败: {e}")
        
        return tools
    
    async def _check_tool_permission(self, user_context: 'UserContext', tool_name: str) -> bool:
        """
        检查工具使用权限
        
        Args:
            user_context: 用户上下文
            tool_name: 工具名称
            
        Returns:
            bool: 是否有权限使用工具
        """
        try:
            # 超级管理员拥有所有工具权限
            if user_context.has_permission("*:*"):
                return True
            
            # 检查具体工具权限
            tool_permission = f"tool:{tool_name}"
            if user_context.has_permission(tool_permission):
                return True
            
            # 基础工具权限检查
            basic_tools = {"calculator", "query_knowledge_graph"}
            if tool_name in basic_tools and user_context.has_permission("tool:basic"):
                return True
            
            # 网络搜索工具权限
            if tool_name == "web_search" and user_context.has_permission("tool:web_search"):
                return True
            
            # 通过权限引擎进行详细检查
            from server.auth.permission_framework.resources import ToolResource
            from server.auth.permission_framework.core import Permission
            
            return await self.permission_engine.check_permission_simple(
                user_id=user_context.user_id,
                resource=ToolResource(tool_name),
                permission=Permission.USE
            )
            
        except Exception as e:
            logger.warning(f"工具权限检查失败 {tool_name}: {e}")
            # 默认允许基础工具
            return tool_name in {"calculator", "query_knowledge_graph"}
    
    async def _check_kb_permission(self, user_context: 'UserContext', kb_id: str, permission: str) -> bool:
        """
        检查知识库权限
        
        Args:
            user_context: 用户上下文
            kb_id: 知识库ID
            permission: 权限类型
            
        Returns:
            bool: 是否有权限
        """
        try:
            # 检查用户上下文中的知识库权限
            if user_context.can_access_kb(kb_id):
                return True
            
            # 通过知识库管理器检查权限
            return await self.kb_manager.check_kb_permission(
                user_context.user_id, kb_id, permission
            )
            
        except Exception as e:
            logger.warning(f"知识库权限检查失败 {kb_id}: {e}")
            return False
    
    def clear_cache(self, user_id: str = None):
        """
        清除工具缓存
        
        Args:
            user_id: 用户ID，如果指定则只清除该用户的缓存
        """
        if user_id:
            # 清除特定用户的缓存
            keys_to_remove = [key for key in self._cache.keys() if key.startswith(f"user_tools:{user_id}:")]
            for key in keys_to_remove:
                del self._cache[key]
            logger.debug(f"已清除用户 {user_id} 的工具缓存")
        else:
            # 清除所有缓存
            self._cache.clear()
            logger.debug("已清除所有工具缓存")
    
    def get_tool_stats(self) -> Dict[str, Any]:
        """
        获取工具使用统计
        
        Returns:
            Dict[str, Any]: 工具统计信息
        """
        return {
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl,
            "available_base_tools": ["calculator", "query_knowledge_graph", "web_search"],
            "permission_engine_status": bool(self.permission_engine),
            "kb_manager_status": bool(self.kb_manager)
        }


# === 向后兼容的全局函数 ===

def get_all_tools_legacy():
    """
    获取所有工具 - 向后兼容的旧版本实现
    
    注意：此函数不包含权限检查，建议使用 PermissionAwareToolsFactory
    """
    logger.warning("使用旧版工具获取函数，建议升级到权限感知工具工厂")
    return get_all_tools()


# 保持向后兼容的函数别名
get_all_tools_without_permission = get_all_tools
