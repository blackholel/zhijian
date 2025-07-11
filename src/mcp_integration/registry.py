"""
MCP 工具注册表

管理所有 MCP 工具的注册、发现和权限控制
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from .client import MCPClient, MCPConnectionConfig, MCPToolInfo
from ..agents.base.tools import ToolInterface, ToolResult, ToolType
from src.auth.services.permission_service import PermissionService

logger = logging.getLogger(__name__)


class MCPTool(ToolInterface):
    """MCP 工具包装器
    
    将 MCP 工具包装为标准的工具接口
    """
    
    def __init__(self, name: str, tool_info: MCPToolInfo, client: MCPClient):
        super().__init__(
            name=name,
            description=tool_info.description,
            tool_type=ToolType.MCP_TOOL
        )
        
        self.tool_info = tool_info
        self.client = client
        self.original_name = tool_info.name
        self.required_permissions = ["mcp_tool:use", f"mcp_tool:{self.original_name}"]
        
        # 设置工具模式
        from ..agents.base.tools import ToolSchema
        self.schema = ToolSchema(
            name=name,
            description=tool_info.description,
            parameters=tool_info.input_schema.get("properties", {}),
            required_parameters=tool_info.required_params,
            optional_parameters=tool_info.optional_params
        )
    
    async def initialize(self) -> bool:
        """初始化工具"""
        try:
            # 确保客户端连接
            if not self.client.is_connected:
                await self.client.connect()
            
            self.set_status(ToolStatus.AVAILABLE)
            return True
            
        except Exception as e:
            logger.error(f"MCP工具初始化失败: {self.name} - {e}")
            self.set_status(ToolStatus.ERROR)
            return False
    
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        try:
            # 调用 MCP 客户端
            result = await self.client.call_tool(self.original_name, parameters)
            
            if result.get("success"):
                return ToolResult.success_result(
                    result=result.get("result"),
                    metadata={
                        "tool_name": self.original_name,
                        "client_name": self.client.config.name,
                        "execution_time": result.get("execution_time")
                    }
                )
            else:
                return ToolResult.error_result(
                    error=result.get("error", "MCP工具执行失败"),
                    metadata={
                        "tool_name": self.original_name,
                        "client_name": self.client.config.name
                    }
                )
                
        except Exception as e:
            return ToolResult.error_result(
                error=f"MCP工具执行异常: {str(e)}",
                metadata={
                    "tool_name": self.original_name,
                    "client_name": self.client.config.name
                }
            )
    
    async def cleanup(self):
        """清理工具"""
        # MCP 工具通常由客户端管理，这里不需要特别清理
        self.set_status(ToolStatus.UNAVAILABLE)


class MCPRegistry:
    """MCP 工具注册表
    
    负责管理所有 MCP 服务器和工具
    """
    
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
        self.tools: Dict[str, MCPTool] = {}
        self.server_configs: Dict[str, MCPConnectionConfig] = {}
        
        # 权限服务
        # TODO: 正确初始化权限服务，暂时设为None
        self.permission_service = None  # PermissionService()
        
        # 健康检查
        self.health_check_interval = 300  # 5分钟
        self.last_health_check: Optional[datetime] = None
        self._health_check_task: Optional[asyncio.Task] = None
        
        # 统计信息
        self.total_registrations = 0
        self.active_connections = 0
        self.failed_connections = 0
        
        logger.info("MCP注册表初始化完成")
    
    async def register_server(self, config: MCPConnectionConfig) -> bool:
        """注册 MCP 服务器"""
        try:
            logger.info(f"注册MCP服务器: {config.name}")
            
            # 检查是否已存在
            if config.name in self.clients:
                logger.warning(f"MCP服务器已存在，将更新配置: {config.name}")
                await self.unregister_server(config.name)
            
            # 创建客户端
            client = MCPClient(config)
            
            # 尝试连接
            if await client.connect():
                self.clients[config.name] = client
                self.server_configs[config.name] = config
                
                # 注册工具
                await self._register_tools_from_client(config.name, client)
                
                self.total_registrations += 1
                self.active_connections += 1
                
                logger.info(f"MCP服务器注册成功: {config.name}")
                return True
            else:
                self.failed_connections += 1
                logger.error(f"MCP服务器连接失败: {config.name}")
                return False
                
        except Exception as e:
            self.failed_connections += 1
            logger.error(f"注册MCP服务器失败: {config.name} - {e}")
            return False
    
    async def _register_tools_from_client(self, server_name: str, client: MCPClient):
        """从客户端注册工具"""
        try:
            tools = await client.list_tools()
            
            for tool_info in tools:
                # 生成唯一的工具名称
                tool_name = f"mcp_{server_name}_{tool_info.name}"
                
                # 创建工具包装器
                mcp_tool = MCPTool(tool_name, tool_info, client)
                
                # 初始化工具
                if await mcp_tool.initialize():
                    self.tools[tool_name] = mcp_tool
                    logger.debug(f"注册MCP工具: {tool_name}")
                else:
                    logger.warning(f"MCP工具初始化失败: {tool_name}")
            
            logger.info(f"从服务器 {server_name} 注册了 {len(tools)} 个工具")
            
        except Exception as e:
            logger.error(f"注册工具失败: {server_name} - {e}")
    
    async def unregister_server(self, server_name: str) -> bool:
        """注销 MCP 服务器"""
        try:
            if server_name not in self.clients:
                logger.warning(f"MCP服务器不存在: {server_name}")
                return False
            
            # 断开客户端连接
            client = self.clients[server_name]
            await client.disconnect()
            
            # 移除工具
            tools_to_remove = [
                tool_name for tool_name in self.tools.keys()
                if tool_name.startswith(f"mcp_{server_name}_")
            ]
            
            for tool_name in tools_to_remove:
                tool = self.tools[tool_name]
                await tool.cleanup()
                del self.tools[tool_name]
            
            # 移除客户端和配置
            del self.clients[server_name]
            del self.server_configs[server_name]
            
            self.active_connections -= 1
            
            logger.info(f"MCP服务器注销成功: {server_name}")
            return True
            
        except Exception as e:
            logger.error(f"注销MCP服务器失败: {server_name} - {e}")
            return False
    
    async def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """获取工具"""
        return self.tools.get(tool_name)
    
    async def list_tools(self) -> List[MCPTool]:
        """列出所有工具"""
        return list(self.tools.values())
    
    async def list_tools_by_server(self, server_name: str) -> List[MCPTool]:
        """按服务器列出工具"""
        prefix = f"mcp_{server_name}_"
        return [
            tool for tool_name, tool in self.tools.items()
            if tool_name.startswith(prefix)
        ]
    
    async def get_user_tools(self, user_id: str) -> List[MCPTool]:
        """获取用户可用的工具"""
        user_tools = []
        
        for tool in self.tools.values():
            # 检查权限
            has_permission = True
            for required_permission in tool.required_permissions:
                if not await self.permission_service.has_permission(user_id, required_permission):
                    has_permission = False
                    break
            
            if has_permission:
                user_tools.append(tool)
        
        return user_tools
    
    async def call_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any], 
        user_id: str
    ) -> ToolResult:
        """调用工具"""
        # 获取工具
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult.error_result(f"工具不存在: {tool_name}")
        
        # 权限检查
        for required_permission in tool.required_permissions:
            if not await self.permission_service.has_permission(user_id, required_permission):
                return ToolResult.error_result(
                    f"权限不足: {required_permission}",
                    metadata={"required_permission": required_permission}
                )
        
        # 执行工具
        return await tool.safe_execute(arguments)
    
    async def get_server_info(self, server_name: str) -> Optional[Dict[str, Any]]:
        """获取服务器信息"""
        if server_name not in self.clients:
            return None
        
        client = self.clients[server_name]
        config = self.server_configs[server_name]
        
        return {
            "name": server_name,
            "config": config.dict(),
            "statistics": await client.get_statistics(),
            "tools": [
                tool.name for tool in await self.list_tools_by_server(server_name)
            ]
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        self.last_health_check = datetime.now()
        
        total_servers = len(self.clients)
        healthy_servers = 0
        unhealthy_servers = []
        
        # 检查每个服务器
        for server_name, client in self.clients.items():
            try:
                if await client.health_check():
                    healthy_servers += 1
                else:
                    unhealthy_servers.append(server_name)
            except Exception as e:
                logger.error(f"服务器健康检查失败: {server_name} - {e}")
                unhealthy_servers.append(server_name)
        
        health_info = {
            "total_servers": total_servers,
            "healthy_servers": healthy_servers,
            "unhealthy_servers": unhealthy_servers,
            "total_tools": len(self.tools),
            "health_percentage": (healthy_servers / total_servers * 100) if total_servers > 0 else 100,
            "last_check": self.last_health_check.isoformat(),
            "statistics": {
                "total_registrations": self.total_registrations,
                "active_connections": self.active_connections,
                "failed_connections": self.failed_connections
            }
        }
        
        return health_info
    
    async def start_health_monitoring(self):
        """启动健康监控"""
        if self._health_check_task and not self._health_check_task.done():
            return
        
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("MCP健康监控已启动")
    
    async def stop_health_monitoring(self):
        """停止健康监控"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            
            logger.info("MCP健康监控已停止")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await self.health_check()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")
                await asyncio.sleep(60)  # 错误时短暂休眠
    
    async def reload_server(self, server_name: str) -> bool:
        """重新加载服务器"""
        if server_name not in self.server_configs:
            return False
        
        config = self.server_configs[server_name]
        
        # 注销后重新注册
        await self.unregister_server(server_name)
        return await self.register_server(config)
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_servers": len(self.clients),
            "active_connections": self.active_connections,
            "failed_connections": self.failed_connections,
            "total_tools": len(self.tools),
            "total_registrations": self.total_registrations,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None
        }
    
    @asynccontextmanager
    async def tool_context(self, tool_names: List[str], user_id: str):
        """工具上下文管理器"""
        tools = []
        
        try:
            # 获取并验证工具
            for tool_name in tool_names:
                tool = await self.get_tool(tool_name)
                if tool:
                    # 检查权限
                    has_permission = True
                    for required_permission in tool.required_permissions:
                        if not await self.permission_service.has_permission(user_id, required_permission):
                            has_permission = False
                            break
                    
                    if has_permission:
                        tools.append(tool)
                    else:
                        logger.warning(f"用户 {user_id} 没有工具 {tool_name} 的权限")
            
            yield tools
            
        finally:
            # 清理工作（如果需要）
            pass
    
    async def shutdown(self):
        """关闭注册表"""
        logger.info("正在关闭MCP注册表...")
        
        # 停止健康监控
        await self.stop_health_monitoring()
        
        # 断开所有连接
        for server_name in list(self.clients.keys()):
            await self.unregister_server(server_name)
        
        self.clients.clear()
        self.tools.clear()
        self.server_configs.clear()
        
        logger.info("MCP注册表已关闭")


# 全局 MCP 注册表实例
mcp_registry = MCPRegistry()