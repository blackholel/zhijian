"""
MCP 管理器

提供 MCP 服务器和工具的集中管理功能
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager

from .client import MCPClient, MCPConnectionConfig
from .registry import MCPRegistry, MCPTool, mcp_registry
from .protocol import MCPProtocolHandler

logger = logging.getLogger(__name__)


class MCPServerStatus(str, Enum):
    """MCP 服务器状态"""
    UNKNOWN = "unknown"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class MCPServerInfo:
    """MCP 服务器信息"""
    name: str
    config: MCPConnectionConfig
    status: MCPServerStatus = MCPServerStatus.UNKNOWN
    client: Optional[MCPClient] = None
    tools: List[str] = field(default_factory=list)
    last_connected: Optional[datetime] = None
    last_error: Optional[str] = None
    connection_count: int = 0
    tool_calls: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "status": self.status.value,
            "config": self.config.dict(),
            "tools": self.tools,
            "last_connected": self.last_connected.isoformat() if self.last_connected else None,
            "last_error": self.last_error,
            "connection_count": self.connection_count,
            "tool_calls": self.tool_calls
        }


class MCPManager:
    """MCP 管理器
    
    提供 MCP 服务器和工具的集中管理功能
    """
    
    def __init__(self, registry: Optional[MCPRegistry] = None):
        self.registry = registry or mcp_registry
        self.servers: Dict[str, MCPServerInfo] = {}
        self.protocol_handlers: Dict[str, MCPProtocolHandler] = {}
        
        # 管理器状态
        self.is_initialized = False
        self.is_running = False
        
        # 配置
        self.auto_reconnect = True
        self.reconnect_interval = 60  # 秒
        self.max_reconnect_attempts = 5
        
        # 后台任务
        self._monitoring_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        
        logger.info("MCP管理器已创建")
    
    async def initialize(self):
        """初始化管理器"""
        if self.is_initialized:
            return
        
        try:
            # 启动注册表健康监控
            await self.registry.start_health_monitoring()
            
            # 启动监控任务
            await self._start_monitoring()
            
            self.is_initialized = True
            self.is_running = True
            
            logger.info("MCP管理器初始化完成")
            
        except Exception as e:
            logger.error(f"MCP管理器初始化失败: {e}")
            raise
    
    async def shutdown(self):
        """关闭管理器"""
        if not self.is_running:
            return
        
        logger.info("正在关闭MCP管理器...")
        
        self.is_running = False
        
        # 停止后台任务
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        
        # 断开所有服务器
        for server_name in list(self.servers.keys()):
            await self.disconnect_server(server_name)
        
        # 关闭注册表
        await self.registry.shutdown()
        
        self.is_initialized = False
        
        logger.info("MCP管理器已关闭")
    
    async def add_server(self, config: MCPConnectionConfig) -> bool:
        """添加MCP服务器"""
        try:
            server_info = MCPServerInfo(
                name=config.name,
                config=config,
                status=MCPServerStatus.UNKNOWN
            )
            
            # 注册到注册表
            success = await self.registry.register_server(config)
            
            if success:
                server_info.status = MCPServerStatus.CONNECTED
                server_info.last_connected = datetime.now()
                server_info.connection_count += 1
                
                # 获取客户端
                client = self.registry.clients.get(config.name)
                if client:
                    server_info.client = client
                    
                    # 获取工具列表
                    tools = await client.list_tools()
                    server_info.tools = [tool.name for tool in tools]
                
                logger.info(f"MCP服务器添加成功: {config.name}")
            else:
                server_info.status = MCPServerStatus.ERROR
                server_info.last_error = f"连接失败: {config.name}"
                logger.error(f"MCP服务器添加失败: {config.name}")
            
            self.servers[config.name] = server_info
            return success
            
        except Exception as e:
            error_msg = f"添加MCP服务器失败: {config.name} - {str(e)}"
            logger.error(error_msg)
            
            # 创建错误状态的服务器信息
            server_info = MCPServerInfo(
                name=config.name,
                config=config,
                status=MCPServerStatus.ERROR,
                last_error=error_msg
            )
            self.servers[config.name] = server_info
            
            return False
    
    async def remove_server(self, server_name: str) -> bool:
        """移除MCP服务器"""
        try:
            if server_name not in self.servers:
                logger.warning(f"MCP服务器不存在: {server_name}")
                return False
            
            # 从注册表注销
            success = await self.registry.unregister_server(server_name)
            
            # 移除服务器信息
            del self.servers[server_name]
            
            # 移除协议处理器
            if server_name in self.protocol_handlers:
                del self.protocol_handlers[server_name]
            
            logger.info(f"MCP服务器移除成功: {server_name}")
            return success
            
        except Exception as e:
            logger.error(f"移除MCP服务器失败: {server_name} - {e}")
            return False
    
    async def connect_server(self, server_name: str) -> bool:
        """连接MCP服务器"""
        server_info = self.servers.get(server_name)
        if not server_info:
            logger.error(f"MCP服务器不存在: {server_name}")
            return False
        
        try:
            server_info.status = MCPServerStatus.CONNECTING
            
            # 重新注册服务器
            success = await self.registry.register_server(server_info.config)
            
            if success:
                server_info.status = MCPServerStatus.CONNECTED
                server_info.last_connected = datetime.now()
                server_info.connection_count += 1
                server_info.last_error = None
                
                # 更新客户端和工具信息
                client = self.registry.clients.get(server_name)
                if client:
                    server_info.client = client
                    tools = await client.list_tools()
                    server_info.tools = [tool.name for tool in tools]
                
                logger.info(f"MCP服务器连接成功: {server_name}")
            else:
                server_info.status = MCPServerStatus.ERROR
                server_info.last_error = "连接失败"
                logger.error(f"MCP服务器连接失败: {server_name}")
            
            return success
            
        except Exception as e:
            error_msg = f"连接MCP服务器失败: {server_name} - {str(e)}"
            logger.error(error_msg)
            
            server_info.status = MCPServerStatus.ERROR
            server_info.last_error = error_msg
            
            return False
    
    async def disconnect_server(self, server_name: str) -> bool:
        """断开MCP服务器"""
        server_info = self.servers.get(server_name)
        if not server_info:
            return False
        
        try:
            # 从注册表注销
            success = await self.registry.unregister_server(server_name)
            
            server_info.status = MCPServerStatus.DISCONNECTED
            server_info.client = None
            server_info.tools = []
            
            logger.info(f"MCP服务器断开成功: {server_name}")
            return success
            
        except Exception as e:
            logger.error(f"断开MCP服务器失败: {server_name} - {e}")
            return False
    
    async def get_server_info(self, server_name: str) -> Optional[MCPServerInfo]:
        """获取服务器信息"""
        return self.servers.get(server_name)
    
    async def list_servers(self) -> List[MCPServerInfo]:
        """列出所有服务器"""
        return list(self.servers.values())
    
    async def list_tools(self, server_name: Optional[str] = None) -> List[MCPTool]:
        """列出工具"""
        if server_name:
            return await self.registry.list_tools_by_server(server_name)
        else:
            return await self.registry.list_tools()
    
    async def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """获取工具"""
        return await self.registry.get_tool(tool_name)
    
    async def call_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any], 
        user_id: str
    ) -> Dict[str, Any]:
        """调用工具"""
        try:
            # 更新工具调用统计
            for server_info in self.servers.values():
                if any(tool.startswith(f"mcp_{server_info.name}_") for tool in [tool_name]):
                    server_info.tool_calls += 1
                    break
            
            # 调用工具
            result = await self.registry.call_tool(tool_name, arguments, user_id)
            
            return {
                "success": result.success,
                "result": result.result,
                "error": result.error if not result.success else None,
                "metadata": result.metadata
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": None,
                "metadata": {}
            }
    
    async def get_user_tools(self, user_id: str) -> List[MCPTool]:
        """获取用户可用的工具"""
        return await self.registry.get_user_tools(user_id)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        registry_health = await self.registry.health_check()
        
        # 服务器状态统计
        server_stats = {
            "total": len(self.servers),
            "connected": sum(1 for s in self.servers.values() if s.status == MCPServerStatus.CONNECTED),
            "disconnected": sum(1 for s in self.servers.values() if s.status == MCPServerStatus.DISCONNECTED),
            "error": sum(1 for s in self.servers.values() if s.status == MCPServerStatus.ERROR),
            "connecting": sum(1 for s in self.servers.values() if s.status == MCPServerStatus.CONNECTING)
        }
        
        return {
            "manager_status": "healthy" if self.is_running else "stopped",
            "is_initialized": self.is_initialized,
            "is_running": self.is_running,
            "server_stats": server_stats,
            "registry_health": registry_health,
            "servers": {
                name: info.to_dict() 
                for name, info in self.servers.items()
            }
        }
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        registry_stats = await self.registry.get_statistics()
        
        total_tool_calls = sum(info.tool_calls for info in self.servers.values())
        total_connections = sum(info.connection_count for info in self.servers.values())
        
        return {
            "manager": {
                "is_initialized": self.is_initialized,
                "is_running": self.is_running,
                "total_servers": len(self.servers),
                "total_tool_calls": total_tool_calls,
                "total_connections": total_connections
            },
            "registry": registry_stats
        }
    
    async def reload_server(self, server_name: str) -> bool:
        """重新加载服务器"""
        return await self.registry.reload_server(server_name)
    
    async def _start_monitoring(self):
        """启动监控任务"""
        if self._monitoring_task and not self._monitoring_task.done():
            return
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        if self.auto_reconnect:
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        
        logger.info("MCP监控任务已启动")
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                # 更新服务器状态
                await self._update_server_status()
                
                # 休眠一段时间
                await asyncio.sleep(30)  # 30秒监控一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(60)  # 错误时休眠更长时间
    
    async def _reconnect_loop(self):
        """重连循环"""
        while self.is_running:
            try:
                await self._attempt_reconnections()
                await asyncio.sleep(self.reconnect_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"重连循环错误: {e}")
                await asyncio.sleep(self.reconnect_interval)
    
    async def _update_server_status(self):
        """更新服务器状态"""
        for server_name, server_info in self.servers.items():
            if server_info.status == MCPServerStatus.CONNECTED:
                # 检查连接状态
                client = self.registry.clients.get(server_name)
                if client:
                    is_healthy = await client.health_check()
                    if not is_healthy:
                        server_info.status = MCPServerStatus.ERROR
                        server_info.last_error = "健康检查失败"
                        logger.warning(f"服务器健康检查失败: {server_name}")
                else:
                    server_info.status = MCPServerStatus.DISCONNECTED
                    logger.warning(f"服务器客户端丢失: {server_name}")
    
    async def _attempt_reconnections(self):
        """尝试重新连接"""
        for server_name, server_info in self.servers.items():
            if server_info.status in [MCPServerStatus.ERROR, MCPServerStatus.DISCONNECTED]:
                try:
                    logger.info(f"尝试重新连接服务器: {server_name}")
                    success = await self.connect_server(server_name)
                    
                    if success:
                        logger.info(f"服务器重连成功: {server_name}")
                    else:
                        logger.warning(f"服务器重连失败: {server_name}")
                        
                except Exception as e:
                    logger.error(f"重连服务器时发生错误: {server_name} - {e}")
    
    @asynccontextmanager
    async def server_context(self, server_names: List[str]):
        """服务器上下文管理器"""
        servers = []
        
        try:
            for server_name in server_names:
                server_info = self.servers.get(server_name)
                if server_info and server_info.status == MCPServerStatus.CONNECTED:
                    servers.append(server_info)
            
            yield servers
            
        finally:
            # 清理工作（如果需要）
            pass
    
    def __str__(self):
        return f"MCPManager(servers={len(self.servers)}, running={self.is_running})"
    
    def __repr__(self):
        return self.__str__()


# 全局 MCP 管理器实例
mcp_manager = MCPManager()