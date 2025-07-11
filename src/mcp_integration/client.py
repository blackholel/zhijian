"""
MCP 客户端实现

参考 Suna 的 MCP 集成设计，支持多种连接协议
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# 根据实际的 MCP 库调整导入
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client  
    from mcp.client.http import http_client
except ImportError:
    # 如果没有 MCP 库，使用模拟实现
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    sse_client = None
    http_client = None

logger = logging.getLogger(__name__)


class MCPConnectionType(str, Enum):
    """MCP 连接类型"""
    STDIO = "stdio"
    HTTP = "http"
    WEBSOCKET = "websocket"
    SSE = "sse"


class MCPConnectionConfig(BaseModel):
    """MCP 连接配置"""
    name: str = Field(..., description="连接名称")
    connection_type: MCPConnectionType = Field(..., description="连接类型")
    
    # 通用配置
    timeout: int = Field(default=30, description="连接超时时间")
    retry_attempts: int = Field(default=3, description="重试次数")
    
    # STDIO 配置
    command: Optional[str] = Field(default=None, description="命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    
    # HTTP/WebSocket 配置
    url: Optional[str] = Field(default=None, description="服务器URL")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP头")
    
    # 认证配置
    api_key: Optional[str] = Field(default=None, description="API密钥")
    auth_token: Optional[str] = Field(default=None, description="认证令牌")
    
    # 高级配置
    max_connections: int = Field(default=5, description="最大连接数")
    health_check_interval: int = Field(default=60, description="健康检查间隔")


class MCPToolInfo(BaseModel):
    """MCP 工具信息"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    required_params: List[str] = Field(default_factory=list)
    optional_params: List[str] = Field(default_factory=list)


class MCPClient:
    """MCP 客户端
    
    支持多种连接协议，参考 Suna 的设计
    """
    
    def __init__(self, config: MCPConnectionConfig):
        self.config = config
        self.connection_type = config.connection_type
        
        # 连接状态
        self.session: Optional[Any] = None
        self.is_connected = False
        self.last_error: Optional[str] = None
        
        # 工具信息
        self.tools: Dict[str, MCPToolInfo] = {}
        
        # 统计信息
        self.connection_count = 0
        self.last_connection_time: Optional[datetime] = None
        self.total_calls = 0
        self.successful_calls = 0
        
        # 并发控制
        self._lock = asyncio.Lock()
        
        logger.info(f"MCP客户端创建: {config.name} ({config.connection_type})")
    
    async def connect(self) -> bool:
        """建立连接"""
        if self.is_connected:
            return True
        
        async with self._lock:
            if self.is_connected:
                return True
            
            try:
                logger.info(f"连接MCP服务器: {self.config.name}")
                
                if self.connection_type == MCPConnectionType.STDIO:
                    success = await self._connect_stdio()
                elif self.connection_type == MCPConnectionType.HTTP:
                    success = await self._connect_http()
                elif self.connection_type == MCPConnectionType.SSE:
                    success = await self._connect_sse()
                elif self.connection_type == MCPConnectionType.WEBSOCKET:
                    success = await self._connect_websocket()
                else:
                    raise ValueError(f"不支持的连接类型: {self.connection_type}")
                
                if success:
                    # 加载工具信息
                    await self._load_tools()
                    
                    self.is_connected = True
                    self.connection_count += 1
                    self.last_connection_time = datetime.now()
                    self.last_error = None
                    
                    logger.info(f"MCP连接成功: {self.config.name}")
                    return True
                else:
                    return False
                
            except Exception as e:
                error_msg = f"MCP连接失败: {self.config.name} - {str(e)}"
                logger.error(error_msg)
                self.last_error = error_msg
                return False
    
    async def _connect_stdio(self) -> bool:
        """STDIO 连接"""
        if not stdio_client or not StdioServerParameters:
            logger.error("MCP STDIO 客户端不可用")
            return False
        
        try:
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env
            )
            
            # 创建 STDIO 连接
            async with stdio_client(server_params) as (read, write):
                self.session = ClientSession(read, write)
                await self.session.initialize()
                return True
                
        except Exception as e:
            logger.error(f"STDIO连接失败: {e}")
            return False
    
    async def _connect_http(self) -> bool:
        """HTTP 连接"""
        if not http_client:
            logger.error("MCP HTTP 客户端不可用")
            return False
        
        try:
            # 创建 HTTP 连接
            async with http_client(
                url=self.config.url,
                headers=self.config.headers,
                timeout=self.config.timeout
            ) as client:
                self.session = client
                return True
                
        except Exception as e:
            logger.error(f"HTTP连接失败: {e}")
            return False
    
    async def _connect_sse(self) -> bool:
        """SSE 连接"""
        if not sse_client:
            logger.error("MCP SSE 客户端不可用")
            return False
        
        try:
            # 创建 SSE 连接
            async with sse_client(
                url=self.config.url,
                headers=self.config.headers
            ) as client:
                self.session = client
                return True
                
        except Exception as e:
            logger.error(f"SSE连接失败: {e}")
            return False
    
    async def _connect_websocket(self) -> bool:
        """WebSocket 连接"""
        try:
            # WebSocket 连接实现
            # 这里需要根据实际的 WebSocket 库实现
            logger.warning("WebSocket 连接暂未实现")
            return False
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False
    
    async def _load_tools(self):
        """加载工具信息"""
        if not self.session:
            return
        
        try:
            # 获取工具列表
            tools_response = await self.session.list_tools()
            
            self.tools.clear()
            for tool in tools_response.tools:
                tool_info = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    required_params=self._extract_required_params(tool.inputSchema),
                    optional_params=self._extract_optional_params(tool.inputSchema)
                )
                
                self.tools[tool.name] = tool_info
            
            logger.info(f"加载了 {len(self.tools)} 个MCP工具")
            
        except Exception as e:
            logger.error(f"加载MCP工具失败: {e}")
    
    def _extract_required_params(self, schema: Dict[str, Any]) -> List[str]:
        """提取必需参数"""
        if not schema:
            return []
        
        return schema.get("required", [])
    
    def _extract_optional_params(self, schema: Dict[str, Any]) -> List[str]:
        """提取可选参数"""
        if not schema:
            return []
        
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        
        return [name for name in properties.keys() if name not in required]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        if not self.is_connected:
            await self.connect()
        
        if not self.session:
            raise RuntimeError("MCP会话未建立")
        
        if tool_name not in self.tools:
            raise ValueError(f"工具不存在: {tool_name}")
        
        try:
            self.total_calls += 1
            start_time = datetime.now()
            
            # 验证参数
            self._validate_arguments(tool_name, arguments)
            
            # 调用工具
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments),
                timeout=self.config.timeout
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            self.successful_calls += 1
            
            logger.debug(f"MCP工具调用成功: {tool_name}, 耗时: {execution_time:.2f}s")
            
            return {
                "success": True,
                "result": result.content if hasattr(result, 'content') else result,
                "tool_name": tool_name,
                "arguments": arguments,
                "execution_time": execution_time
            }
            
        except asyncio.TimeoutError:
            error_msg = f"MCP工具调用超时: {tool_name}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "tool_name": tool_name,
                "arguments": arguments
            }
            
        except Exception as e:
            error_msg = f"MCP工具调用失败: {tool_name} - {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "tool_name": tool_name,
                "arguments": arguments
            }
    
    def _validate_arguments(self, tool_name: str, arguments: Dict[str, Any]):
        """验证参数"""
        tool_info = self.tools[tool_name]
        
        # 检查必需参数
        for required_param in tool_info.required_params:
            if required_param not in arguments:
                raise ValueError(f"缺少必需参数: {required_param}")
        
        # 检查未知参数
        known_params = set(tool_info.required_params + tool_info.optional_params)
        for param in arguments.keys():
            if param not in known_params:
                logger.warning(f"未知参数: {param}")
    
    async def list_tools(self) -> List[MCPToolInfo]:
        """列出工具"""
        if not self.is_connected:
            await self.connect()
        
        return list(self.tools.values())
    
    async def get_tool_info(self, tool_name: str) -> Optional[MCPToolInfo]:
        """获取工具信息"""
        return self.tools.get(tool_name)
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self.is_connected:
                return False
            
            # 尝试列出工具作为健康检查
            await self.list_tools()
            return True
            
        except Exception as e:
            logger.error(f"MCP健康检查失败: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """断开连接"""
        if not self.is_connected:
            return
        
        try:
            if self.session:
                # 根据连接类型进行清理
                if hasattr(self.session, 'close'):
                    await self.session.close()
                elif hasattr(self.session, 'disconnect'):
                    await self.session.disconnect()
            
            self.is_connected = False
            self.session = None
            
            logger.info(f"MCP连接已断开: {self.config.name}")
            
        except Exception as e:
            logger.error(f"断开MCP连接失败: {e}")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        success_rate = (
            self.successful_calls / self.total_calls 
            if self.total_calls > 0 else 0.0
        )
        
        return {
            "name": self.config.name,
            "connection_type": self.connection_type.value,
            "is_connected": self.is_connected,
            "connection_count": self.connection_count,
            "last_connection_time": self.last_connection_time.isoformat() if self.last_connection_time else None,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "success_rate": success_rate,
            "tool_count": len(self.tools),
            "last_error": self.last_error
        }
    
    @asynccontextmanager
    async def connection_context(self):
        """连接上下文管理器"""
        try:
            await self.connect()
            yield self
        finally:
            # 可以选择保持连接或断开
            pass  # 保持连接以便复用
    
    def __str__(self):
        return f"MCPClient({self.config.name}, {self.connection_type.value})"
    
    def __repr__(self):
        return self.__str__()