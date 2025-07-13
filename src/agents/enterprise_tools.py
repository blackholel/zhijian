"""
权限感知工具系统
为智能体提供安全的工具访问能力
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Callable, Annotated
from dataclasses import dataclass
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, tool
from langchain_tavily import TavilySearch

from src.utils import logger
from src.agents.enterprise_base import EnterpriseAgentContext
from src.database.manager import UnifiedDatabaseManager
from server.auth.permission_framework.manager import PermissionManager
from server.auth.permission_framework.core import Permission, PermissionContext
from server.auth.permission_framework.concrete_resources import (
    KnowledgeBaseResource,
    MCPToolResource
)
from server.auth.permission_framework.audit import AuditLogger
from src.database.managers.knowledge_manager import KnowledgeBaseManager


@dataclass
class ToolExecutionContext:
    """工具执行上下文"""
    agent_context: EnterpriseAgentContext
    tool_name: str
    parameters: Dict[str, Any]
    permission_manager: PermissionManager
    audit_logger: AuditLogger


class PermissionAwareTool(ABC):
    """权限感知工具基类"""
    
    def __init__(self, name: str, description: str, required_permissions: List[str] = None):
        self.name = name
        self.description = description
        self.required_permissions = required_permissions or []
    
    @abstractmethod
    async def execute(self, context: ToolExecutionContext, **kwargs) -> Any:
        """执行工具"""
        pass
    
    async def check_permissions(self, context: ToolExecutionContext) -> bool:
        """检查权限"""
        for permission_str in self.required_permissions:
            permission = Permission(permission_str)
            tool_resource = MCPToolResource(self.name)
            
            permission_context = context.agent_context.to_permission_context(
                tool_resource, permission
            )
            
            if not await context.permission_manager.check_permission(permission_context):
                await context.audit_logger.log_permission_denied(
                    context.agent_context.user_id,
                    f"tool:{self.name}",
                    permission_str
                )
                return False
        
        return True
    
    async def execute_with_permissions(self, context: ToolExecutionContext, **kwargs) -> Any:
        """带权限检查的执行"""
        # 检查权限
        if not await self.check_permissions(context):
            raise PermissionError(f"User {context.agent_context.user_id} lacks permissions for tool {self.name}")
        
        # 记录工具调用
        await context.audit_logger.log_tool_execution(
            user_id=context.agent_context.user_id,
            tool_name=self.name,
            parameters=context.parameters,
            session_id=context.agent_context.session_id
        )
        
        try:
            # 执行工具
            result = await self.execute(context, **kwargs)
            
            # 记录成功
            await context.audit_logger.log_tool_success(
                user_id=context.agent_context.user_id,
                tool_name=self.name,
                result_summary=str(result)[:500],  # 限制日志长度
                session_id=context.agent_context.session_id
            )
            
            return result
            
        except Exception as e:
            # 记录错误
            await context.audit_logger.log_tool_error(
                user_id=context.agent_context.user_id,
                tool_name=self.name,
                error=str(e),
                session_id=context.agent_context.session_id
            )
            raise


class KnowledgeRetrievalTool(PermissionAwareTool):
    """知识检索工具"""
    
    def __init__(self):
        super().__init__(
            name="knowledge_retrieval",
            description="从知识库中检索相关信息",
            required_permissions=["read"]
        )
    
    async def execute(self, context: ToolExecutionContext, **kwargs) -> str:
        """执行知识检索"""
        query = kwargs.get('query', '')
        kb_ids = kwargs.get('kb_ids', [])
        
        if not query:
            return "查询内容不能为空"
        
        # 获取知识库管理器
        db_manager = UnifiedDatabaseManager()
        await db_manager.initialize()
        
        kb_manager = KnowledgeBaseManager(
            connection_manager=db_manager.connection_manager
        )
        
        results = []
        
        # 如果没有指定知识库，获取用户可访问的所有知识库
        if not kb_ids:
            kb_ids = await kb_manager.get_user_accessible_knowledge_bases(
                context.agent_context.user_id
            )
        
        # 对每个知识库进行权限检查和检索
        for kb_id in kb_ids:
            # 检查知识库访问权限
            kb_resource = KnowledgeBaseResource(kb_id)
            permission_context = context.agent_context.to_permission_context(
                kb_resource, Permission.READ
            )
            
            if await context.permission_manager.check_permission(permission_context):
                try:
                    # 执行检索
                    kb_result = await kb_manager.query_knowledge_base(
                        kb_id, query, context.agent_context.user_id
                    )
                    results.append({
                        "kb_id": kb_id,
                        "result": kb_result
                    })
                except Exception as e:
                    logger.error(f"Error querying knowledge base {kb_id}: {e}")
                    results.append({
                        "kb_id": kb_id,
                        "error": str(e)
                    })
        
        if not results:
            return "没有找到相关信息或没有访问权限"
        
        # 格式化结果
        formatted_results = []
        for result in results:
            if "error" in result:
                formatted_results.append(f"知识库 {result['kb_id']}: 查询失败 - {result['error']}")
            else:
                formatted_results.append(f"知识库 {result['kb_id']}: {result['result']}")
        
        return "\n\n".join(formatted_results)


class DatabaseQueryTool(PermissionAwareTool):
    """数据库查询工具"""
    
    def __init__(self):
        super().__init__(
            name="database_query",
            description="查询数据库信息",
            required_permissions=["read", "database_access"]
        )
    
    async def execute(self, context: ToolExecutionContext, **kwargs) -> str:
        """执行数据库查询"""
        query_type = kwargs.get('query_type', 'knowledge_base_list')
        
        # 获取数据库管理器
        db_manager = UnifiedDatabaseManager()
        await db_manager.initialize()
        
        if query_type == 'knowledge_base_list':
            # 获取用户可访问的知识库列表
            kb_manager = KnowledgeBaseManager(
                connection_manager=db_manager.connection_manager
            )
            
            kb_list = await kb_manager.get_user_accessible_knowledge_bases(
                context.agent_context.user_id
            )
            
            return f"可访问的知识库: {', '.join(kb_list)}"
        
        elif query_type == 'session_info':
            # 获取会话信息
            redis_adapter = await db_manager.get_adapter('redis')
            session_key = f"agent_session:{context.agent_context.session_id}"
            session_data = await redis_adapter.get(session_key)
            
            if session_data:
                return f"会话信息: {json.dumps(session_data, ensure_ascii=False, indent=2)}"
            else:
                return "会话信息不存在或已过期"
        
        else:
            return f"不支持的查询类型: {query_type}"


class FileOperationTool(PermissionAwareTool):
    """文件操作工具"""
    
    def __init__(self):
        super().__init__(
            name="file_operation",
            description="文件操作工具",
            required_permissions=["read", "write", "file_access"]
        )
    
    async def execute(self, context: ToolExecutionContext, **kwargs) -> str:
        """执行文件操作"""
        operation = kwargs.get('operation', 'list')
        kb_id = kwargs.get('kb_id')
        
        if not kb_id:
            return "需要指定知识库ID"
        
        # 检查知识库访问权限
        kb_resource = KnowledgeBaseResource(kb_id)
        permission_context = context.agent_context.to_permission_context(
            kb_resource, Permission.READ
        )
        
        if not await context.permission_manager.check_permission(permission_context):
            return "没有访问此知识库的权限"
        
        # 获取数据库管理器
        db_manager = UnifiedDatabaseManager()
        await db_manager.initialize()
        
        kb_manager = KnowledgeBaseManager(
            connection_manager=db_manager.connection_manager
        )
        
        if operation == 'list':
            # 列出知识库中的文件
            files = await kb_manager.get_knowledge_base_files(kb_id)
            if files:
                file_list = [f"- {file['filename']} ({file['file_type']})" for file in files]
                return f"知识库 {kb_id} 中的文件:\n" + "\n".join(file_list)
            else:
                return f"知识库 {kb_id} 中没有文件"
        
        else:
            return f"不支持的操作: {operation}"


class GraphQueryTool(PermissionAwareTool):
    """图查询工具"""
    
    def __init__(self):
        super().__init__(
            name="graph_query",
            description="查询知识图谱",
            required_permissions=["read", "graph_access"]
        )
    
    async def execute(self, context: ToolExecutionContext, **kwargs) -> str:
        """执行图查询"""
        query = kwargs.get('query', '')
        kb_id = kwargs.get('kb_id')
        hops = kwargs.get('hops', 2)
        
        if not query:
            return "查询内容不能为空"
        
        if not kb_id:
            return "需要指定知识库ID"
        
        # 检查知识库访问权限
        kb_resource = KnowledgeBaseResource(kb_id)
        permission_context = context.agent_context.to_permission_context(
            kb_resource, Permission.READ
        )
        
        if not await context.permission_manager.check_permission(permission_context):
            return "没有访问此知识库的权限"
        
        # 获取数据库管理器
        db_manager = UnifiedDatabaseManager()
        await db_manager.initialize()
        
        # 执行图查询
        graph_repo = await db_manager.get_repository('graph')
        result = await graph_repo.query_user_entities(
            context.agent_context.user_id, kb_id, query, hops=hops
        )
        
        if result:
            return f"图查询结果: {json.dumps(result, ensure_ascii=False, indent=2)}"
        else:
            return "没有找到相关的图谱信息"


class EnterpriseToolsManager:
    """企业级工具管理器"""
    
    def __init__(self, db_manager: UnifiedDatabaseManager = None):
        self.db_manager = db_manager
        self.permission_manager: Optional[PermissionManager] = None
        self.audit_logger: Optional[AuditLogger] = None
        self.tools: Dict[str, PermissionAwareTool] = {}
        self._initialize_default_tools()
    
    def _initialize_default_tools(self):
        """初始化默认工具"""
        self.tools = {
            "knowledge_retrieval": KnowledgeRetrievalTool(),
            "database_query": DatabaseQueryTool(),
            "file_operation": FileOperationTool(),
            "graph_query": GraphQueryTool()
        }
    
    async def initialize(self):
        """初始化工具管理器"""
        if not self.db_manager:
            self.db_manager = UnifiedDatabaseManager()
            await self.db_manager.initialize()
        
        self.permission_manager = PermissionManager(
            db_manager=self.db_manager,
            enable_cache=True
        )
        
        self.audit_logger = AuditLogger(
            db_manager=self.db_manager
        )
    
    async def get_available_tools(self, context: EnterpriseAgentContext) -> List[str]:
        """获取用户可用的工具列表"""
        if not self.permission_manager:
            await self.initialize()
        
        available_tools = []
        
        for tool_name, tool in self.tools.items():
            # 检查工具权限
            for permission_str in tool.required_permissions:
                permission = Permission(permission_str)
                tool_resource = MCPToolResource(tool_name)
                
                permission_context = context.to_permission_context(
                    tool_resource, permission
                )
                
                if await self.permission_manager.check_permission(permission_context):
                    available_tools.append(tool_name)
                    break
        
        return available_tools
    
    async def execute_tool(self, tool_name: str, context: EnterpriseAgentContext, 
                          **kwargs) -> Any:
        """执行工具"""
        if not self.permission_manager:
            await self.initialize()
        
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        tool = self.tools[tool_name]
        
        execution_context = ToolExecutionContext(
            agent_context=context,
            tool_name=tool_name,
            parameters=kwargs,
            permission_manager=self.permission_manager,
            audit_logger=self.audit_logger
        )
        
        return await tool.execute_with_permissions(execution_context, **kwargs)
    
    def get_langchain_tools(self, context: EnterpriseAgentContext) -> List[StructuredTool]:
        """获取LangChain兼容的工具"""
        langchain_tools = []
        
        # 知识检索工具
        class KnowledgeRetrievalModel(BaseModel):
            query: str = Field(description="查询内容")
            kb_ids: List[str] = Field(default_factory=list, description="知识库ID列表")
        
        async def knowledge_retrieval_wrapper(query: str, kb_ids: List[str] = None):
            return await self.execute_tool(
                "knowledge_retrieval", 
                context, 
                query=query, 
                kb_ids=kb_ids or []
            )
        
        langchain_tools.append(
            StructuredTool.from_function(
                coroutine=knowledge_retrieval_wrapper,
                name="knowledge_retrieval",
                description="从知识库中检索相关信息",
                args_schema=KnowledgeRetrievalModel
            )
        )
        
        # 数据库查询工具
        class DatabaseQueryModel(BaseModel):
            query_type: str = Field(description="查询类型")
        
        async def database_query_wrapper(query_type: str):
            return await self.execute_tool(
                "database_query",
                context,
                query_type=query_type
            )
        
        langchain_tools.append(
            StructuredTool.from_function(
                coroutine=database_query_wrapper,
                name="database_query",
                description="查询数据库信息",
                args_schema=DatabaseQueryModel
            )
        )
        
        # 文件操作工具
        class FileOperationModel(BaseModel):
            operation: str = Field(description="操作类型")
            kb_id: str = Field(description="知识库ID")
        
        async def file_operation_wrapper(operation: str, kb_id: str):
            return await self.execute_tool(
                "file_operation",
                context,
                operation=operation,
                kb_id=kb_id
            )
        
        langchain_tools.append(
            StructuredTool.from_function(
                coroutine=file_operation_wrapper,
                name="file_operation",
                description="文件操作工具",
                args_schema=FileOperationModel
            )
        )
        
        # 图查询工具
        class GraphQueryModel(BaseModel):
            query: str = Field(description="查询内容")
            kb_id: str = Field(description="知识库ID")
            hops: int = Field(default=2, description="查询跳数")
        
        async def graph_query_wrapper(query: str, kb_id: str, hops: int = 2):
            return await self.execute_tool(
                "graph_query",
                context,
                query=query,
                kb_id=kb_id,
                hops=hops
            )
        
        langchain_tools.append(
            StructuredTool.from_function(
                coroutine=graph_query_wrapper,
                name="graph_query",
                description="查询知识图谱",
                args_schema=GraphQueryModel
            )
        )
        
        return langchain_tools
    
    def register_tool(self, tool: PermissionAwareTool):
        """注册新工具"""
        self.tools[tool.name] = tool
    
    def get_tool_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            tool_name: {
                "name": tool.name,
                "description": tool.description,
                "required_permissions": tool.required_permissions
            }
            for tool_name, tool in self.tools.items()
        } 