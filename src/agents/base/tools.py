"""
智能体工具接口定义

参考 DeerFlow 和 Suna 的工具系统设计
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union, Callable
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import asyncio
import json
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ToolType(str, Enum):
    """工具类型"""
    KNOWLEDGE_BASE = "knowledge_base"    # 知识库工具
    MCP_TOOL = "mcp_tool"               # MCP工具
    SYSTEM_TOOL = "system_tool"         # 系统工具
    CUSTOM_TOOL = "custom_tool"         # 自定义工具


class ToolStatus(str, Enum):
    """工具状态"""
    AVAILABLE = "available"      # 可用
    UNAVAILABLE = "unavailable"  # 不可用
    LOADING = "loading"         # 加载中
    ERROR = "error"             # 错误
    DISABLED = "disabled"       # 禁用


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(default=None, description="执行结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    execution_time: Optional[float] = Field(default=None, description="执行时间(秒)")
    
    @classmethod
    def success_result(cls, result: Any, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """创建成功结果"""
        return cls(
            success=True,
            result=result,
            metadata=metadata or {}
        )
    
    @classmethod
    def error_result(cls, error: str, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """创建错误结果"""
        return cls(
            success=False,
            error=error,
            metadata=metadata or {}
        )


class ToolSchema(BaseModel):
    """工具模式定义"""
    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数模式")
    required_parameters: List[str] = Field(default_factory=list, description="必需参数")
    optional_parameters: List[str] = Field(default_factory=list, description="可选参数")
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """验证参数"""
        # 检查必需参数
        for required_param in self.required_parameters:
            if required_param not in params:
                return False
        
        # 检查参数类型 (简化版本)
        for param_name, param_value in params.items():
            if param_name in self.parameters:
                expected_type = self.parameters[param_name].get("type")
                if expected_type and not self._check_type(param_value, expected_type):
                    return False
        
        return True
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """检查类型"""
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict
        }
        
        expected_python_type = type_mapping.get(expected_type)
        if expected_python_type:
            return isinstance(value, expected_python_type)
        
        return True  # 未知类型默认通过


class ToolInterface(ABC):
    """工具接口基类"""
    
    def __init__(self, name: str, description: str, tool_type: ToolType):
        self.name = name
        self.description = description
        self.tool_type = tool_type
        self.status = ToolStatus.AVAILABLE
        self.schema: Optional[ToolSchema] = None
        self.metadata: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.last_used_at: Optional[datetime] = None
        self.usage_count = 0
        self._lock = asyncio.Lock()
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化工具"""
        pass
    
    @abstractmethod
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        pass
    
    @abstractmethod
    async def cleanup(self):
        """清理工具"""
        pass
    
    async def is_available(self) -> bool:
        """检查工具是否可用"""
        return self.status == ToolStatus.AVAILABLE
    
    async def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """验证参数"""
        if self.schema:
            return self.schema.validate_parameters(parameters)
        return True
    
    async def safe_execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """安全执行工具"""
        async with self._lock:
            try:
                # 检查可用性
                if not await self.is_available():
                    return ToolResult.error_result(f"工具不可用: {self.name}")
                
                # 验证参数
                if not await self.validate_parameters(parameters):
                    return ToolResult.error_result("参数验证失败")
                
                # 记录使用
                start_time = datetime.now()
                self.usage_count += 1
                self.last_used_at = start_time
                
                # 执行工具
                result = await self.execute(parameters)
                
                # 记录执行时间
                execution_time = (datetime.now() - start_time).total_seconds()
                result.execution_time = execution_time
                
                logger.info(f"工具 {self.name} 执行完成，耗时 {execution_time:.2f}s")
                return result
                
            except Exception as e:
                logger.error(f"工具 {self.name} 执行失败: {e}")
                return ToolResult.error_result(f"工具执行异常: {str(e)}")
    
    def set_status(self, status: ToolStatus):
        """设置状态"""
        self.status = status
    
    def get_info(self) -> Dict[str, Any]:
        """获取工具信息"""
        return {
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type.value,
            "status": self.status.value,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }


class KnowledgeBaseTool(ToolInterface):
    """知识库工具"""
    
    def __init__(self, name: str, kb_id: str, description: str = ""):
        super().__init__(name, description or f"知识库工具: {name}", ToolType.KNOWLEDGE_BASE)
        self.kb_id = kb_id
        self.kb_instance = None
        
        # 设置工具模式
        self.schema = ToolSchema(
            name=name,
            description=self.description,
            parameters={
                "query": {"type": "string", "description": "查询内容"},
                "limit": {"type": "integer", "description": "结果数量限制", "default": 10},
                "mode": {"type": "string", "description": "检索模式", "default": "hybrid"}
            },
            required_parameters=["query"],
            optional_parameters=["limit", "mode"]
        )
    
    async def initialize(self) -> bool:
        """初始化知识库连接"""
        try:
            # TODO: 实现知识库连接逻辑
            from src.knowledge_base.services.kb_service import KnowledgeBaseService
            
            kb_service = KnowledgeBaseService()
            self.kb_instance = await kb_service.get_knowledge_base(self.kb_id)
            
            if self.kb_instance:
                self.set_status(ToolStatus.AVAILABLE)
                return True
            else:
                self.set_status(ToolStatus.UNAVAILABLE)
                return False
                
        except Exception as e:
            logger.error(f"知识库工具 {self.name} 初始化失败: {e}")
            self.set_status(ToolStatus.ERROR)
            return False
    
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行知识库查询"""
        try:
            query = parameters["query"]
            limit = parameters.get("limit", 10)
            mode = parameters.get("mode", "hybrid")
            
            # TODO: 实现具体的知识库查询逻辑
            # 这里是示例实现
            results = []
            
            return ToolResult.success_result(
                result=results,
                metadata={
                    "kb_id": self.kb_id,
                    "query": query,
                    "mode": mode,
                    "result_count": len(results)
                }
            )
            
        except Exception as e:
            return ToolResult.error_result(f"知识库查询失败: {str(e)}")
    
    async def cleanup(self):
        """清理知识库连接"""
        self.kb_instance = None
        self.set_status(ToolStatus.UNAVAILABLE)


class MCPTool(ToolInterface):
    """MCP工具"""
    
    def __init__(self, name: str, mcp_tool_name: str, description: str = ""):
        super().__init__(name, description or f"MCP工具: {name}", ToolType.MCP_TOOL)
        self.mcp_tool_name = mcp_tool_name
        self.mcp_client = None
    
    async def initialize(self) -> bool:
        """初始化MCP连接"""
        try:
            # TODO: 实现MCP连接逻辑
            from src.mcp_integration.registry import MCPRegistry
            
            registry = MCPRegistry()
            self.mcp_client = await registry.get_tool(self.mcp_tool_name)
            
            if self.mcp_client:
                self.set_status(ToolStatus.AVAILABLE)
                return True
            else:
                self.set_status(ToolStatus.UNAVAILABLE)
                return False
                
        except Exception as e:
            logger.error(f"MCP工具 {self.name} 初始化失败: {e}")
            self.set_status(ToolStatus.ERROR)
            return False
    
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行MCP工具"""
        try:
            if not self.mcp_client:
                return ToolResult.error_result("MCP客户端未初始化")
            
            # TODO: 实现具体的MCP工具调用逻辑
            result = await self.mcp_client.execute(parameters)
            
            return ToolResult.success_result(
                result=result,
                metadata={
                    "mcp_tool_name": self.mcp_tool_name,
                    "parameters": parameters
                }
            )
            
        except Exception as e:
            return ToolResult.error_result(f"MCP工具执行失败: {str(e)}")
    
    async def cleanup(self):
        """清理MCP连接"""
        self.mcp_client = None
        self.set_status(ToolStatus.UNAVAILABLE)


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, ToolInterface] = {}
        self._tool_groups: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()
    
    async def register_tool(self, tool: ToolInterface) -> bool:
        """注册工具"""
        async with self._lock:
            if tool.name in self._tools:
                logger.warning(f"工具 {tool.name} 已存在，将被覆盖")
            
            # 初始化工具
            if await tool.initialize():
                self._tools[tool.name] = tool
                logger.info(f"工具 {tool.name} 注册成功")
                return True
            else:
                logger.error(f"工具 {tool.name} 初始化失败，注册失败")
                return False
    
    async def unregister_tool(self, tool_name: str) -> bool:
        """注销工具"""
        async with self._lock:
            if tool_name in self._tools:
                tool = self._tools[tool_name]
                await tool.cleanup()
                del self._tools[tool_name]
                
                # 从分组中移除
                for group_tools in self._tool_groups.values():
                    if tool_name in group_tools:
                        group_tools.remove(tool_name)
                
                logger.info(f"工具 {tool_name} 注销成功")
                return True
            return False
    
    async def get_tool(self, tool_name: str) -> Optional[ToolInterface]:
        """获取工具"""
        return self._tools.get(tool_name)
    
    async def list_tools(self, tool_type: Optional[ToolType] = None) -> List[ToolInterface]:
        """列出工具"""
        tools = list(self._tools.values())
        
        if tool_type:
            tools = [tool for tool in tools if tool.tool_type == tool_type]
        
        return tools
    
    async def get_available_tools(self) -> List[ToolInterface]:
        """获取可用工具"""
        return [tool for tool in self._tools.values() if tool.status == ToolStatus.AVAILABLE]
    
    async def create_tool_group(self, group_name: str, tool_names: List[str]):
        """创建工具分组"""
        # 验证工具是否存在
        valid_tools = []
        for tool_name in tool_names:
            if tool_name in self._tools:
                valid_tools.append(tool_name)
            else:
                logger.warning(f"工具 {tool_name} 不存在，跳过")
        
        self._tool_groups[group_name] = valid_tools
        logger.info(f"工具分组 {group_name} 创建成功，包含 {len(valid_tools)} 个工具")
    
    async def get_tool_group(self, group_name: str) -> List[ToolInterface]:
        """获取工具分组"""
        tool_names = self._tool_groups.get(group_name, [])
        return [self._tools[name] for name in tool_names if name in self._tools]
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        tool = await self.get_tool(tool_name)
        if not tool:
            return ToolResult.error_result(f"工具不存在: {tool_name}")
        
        return await tool.safe_execute(parameters)
    
    async def batch_execute(self, tool_calls: List[Dict[str, Any]]) -> List[ToolResult]:
        """批量执行工具"""
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool_name")
            parameters = tool_call.get("parameters", {})
            
            if tool_name:
                result = await self.execute_tool(tool_name, parameters)
                results.append(result)
            else:
                results.append(ToolResult.error_result("缺少工具名称"))
        
        return results
    
    async def get_tools_info(self) -> Dict[str, Dict[str, Any]]:
        """获取所有工具信息"""
        return {
            tool_name: tool.get_info() 
            for tool_name, tool in self._tools.items()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        total_tools = len(self._tools)
        available_tools = len([t for t in self._tools.values() if t.status == ToolStatus.AVAILABLE])
        error_tools = len([t for t in self._tools.values() if t.status == ToolStatus.ERROR])
        
        return {
            "total_tools": total_tools,
            "available_tools": available_tools,
            "error_tools": error_tools,
            "health_percentage": (available_tools / total_tools * 100) if total_tools > 0 else 0
        }
    
    @asynccontextmanager
    async def tool_context(self, tool_names: List[str]):
        """工具上下文管理器"""
        tools = []
        
        try:
            # 获取工具
            for tool_name in tool_names:
                tool = await self.get_tool(tool_name)
                if tool:
                    tools.append(tool)
            
            yield tools
            
        finally:
            # 清理工具
            for tool in tools:
                try:
                    await tool.cleanup()
                except Exception as e:
                    logger.error(f"清理工具 {tool.name} 失败: {e}")


# 全局工具注册表实例
tool_registry = ToolRegistry()