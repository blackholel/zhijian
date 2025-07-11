"""
MCP 协议处理器

处理 MCP 协议的消息解析、验证和转换
"""

import json
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator
from uuid import uuid4

logger = logging.getLogger(__name__)


class MCPMessageType(str, Enum):
    """MCP 消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"


class MCPMethod(str, Enum):
    """MCP 方法类型"""
    INITIALIZE = "initialize"
    LIST_TOOLS = "tools/list"
    CALL_TOOL = "tools/call"
    LIST_RESOURCES = "resources/list"
    READ_RESOURCE = "resources/read"
    PING = "ping"
    LOG = "logging/setLevel"


class MCPMessage(BaseModel):
    """MCP 消息基类"""
    jsonrpc: str = Field(default="2.0", description="JSON-RPC版本")
    id: Optional[Union[str, int]] = Field(default=None, description="消息ID")
    method: Optional[str] = Field(default=None, description="方法名")
    params: Optional[Dict[str, Any]] = Field(default=None, description="参数")
    result: Optional[Any] = Field(default=None, description="结果")
    error: Optional[Dict[str, Any]] = Field(default=None, description="错误信息")
    
    @validator('jsonrpc')
    def validate_jsonrpc(cls, v):
        if v != "2.0":
            raise ValueError("jsonrpc must be '2.0'")
        return v
    
    @property
    def message_type(self) -> MCPMessageType:
        """获取消息类型"""
        if self.error:
            return MCPMessageType.ERROR
        elif self.result is not None or (self.id is not None and self.method is None):
            return MCPMessageType.RESPONSE
        elif self.method and self.id is not None:
            return MCPMessageType.REQUEST
        elif self.method and self.id is None:
            return MCPMessageType.NOTIFICATION
        else:
            return MCPMessageType.REQUEST
    
    def is_request(self) -> bool:
        """是否为请求消息"""
        return self.message_type == MCPMessageType.REQUEST
    
    def is_response(self) -> bool:
        """是否为响应消息"""
        return self.message_type == MCPMessageType.RESPONSE
    
    def is_notification(self) -> bool:
        """是否为通知消息"""
        return self.message_type == MCPMessageType.NOTIFICATION
    
    def is_error(self) -> bool:
        """是否为错误消息"""
        return self.message_type == MCPMessageType.ERROR


class MCPRequest(MCPMessage):
    """MCP 请求消息"""
    id: Union[str, int] = Field(..., description="请求ID")
    method: str = Field(..., description="方法名")
    params: Optional[Dict[str, Any]] = Field(default=None, description="参数")
    
    @classmethod
    def create(cls, method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[Union[str, int]] = None):
        """创建请求消息"""
        return cls(
            id=request_id or str(uuid4()),
            method=method,
            params=params
        )


class MCPResponse(MCPMessage):
    """MCP 响应消息"""
    id: Union[str, int] = Field(..., description="请求ID")
    result: Optional[Any] = Field(default=None, description="结果")
    error: Optional[Dict[str, Any]] = Field(default=None, description="错误信息")
    
    @classmethod
    def create_success(cls, request_id: Union[str, int], result: Any):
        """创建成功响应"""
        return cls(
            id=request_id,
            result=result
        )
    
    @classmethod
    def create_error(cls, request_id: Union[str, int], error_code: int, error_message: str, error_data: Optional[Any] = None):
        """创建错误响应"""
        error_obj = {
            "code": error_code,
            "message": error_message
        }
        if error_data is not None:
            error_obj["data"] = error_data
        
        return cls(
            id=request_id,
            error=error_obj
        )


class MCPNotification(MCPMessage):
    """MCP 通知消息"""
    method: str = Field(..., description="方法名")
    params: Optional[Dict[str, Any]] = Field(default=None, description="参数")
    
    @classmethod
    def create(cls, method: str, params: Optional[Dict[str, Any]] = None):
        """创建通知消息"""
        return cls(
            method=method,
            params=params
        )


class MCPError:
    """MCP 错误代码"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # MCP 特定错误
    TOOL_NOT_FOUND = -32001
    RESOURCE_NOT_FOUND = -32002
    PERMISSION_DENIED = -32003
    CONNECTION_ERROR = -32004
    TIMEOUT_ERROR = -32005


class MCPProtocolHandler:
    """MCP 协议处理器
    
    负责处理 MCP 协议的消息解析、验证和转换
    """
    
    def __init__(self, server_name: str):
        self.server_name = server_name
        self.pending_requests: Dict[Union[str, int], MCPRequest] = {}
        self.message_handlers: Dict[str, callable] = {}
        self.request_timeout = 30  # 秒
        
        # 统计信息
        self.messages_sent = 0
        self.messages_received = 0
        self.errors_count = 0
        self.last_activity = datetime.now()
        
        logger.info(f"MCP协议处理器已创建: {server_name}")
    
    def parse_message(self, raw_message: Union[str, bytes, Dict[str, Any]]) -> MCPMessage:
        """解析消息"""
        try:
            if isinstance(raw_message, (str, bytes)):
                data = json.loads(raw_message)
            elif isinstance(raw_message, dict):
                data = raw_message
            else:
                raise ValueError(f"不支持的消息类型: {type(raw_message)}")
            
            # 创建适当的消息对象
            message = MCPMessage(**data)
            
            self.messages_received += 1
            self.last_activity = datetime.now()
            
            logger.debug(f"解析MCP消息: {message.message_type.value} - {message.method or 'N/A'}")
            
            return message
            
        except json.JSONDecodeError as e:
            self.errors_count += 1
            logger.error(f"JSON解析错误: {e}")
            raise ValueError(f"消息JSON格式错误: {e}")
        
        except Exception as e:
            self.errors_count += 1
            logger.error(f"消息解析错误: {e}")
            raise ValueError(f"消息解析失败: {e}")
    
    def serialize_message(self, message: MCPMessage) -> str:
        """序列化消息"""
        try:
            data = message.dict(exclude_none=True)
            serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            
            self.messages_sent += 1
            self.last_activity = datetime.now()
            
            logger.debug(f"序列化MCP消息: {message.message_type.value} - {message.method or 'N/A'}")
            
            return serialized
            
        except Exception as e:
            self.errors_count += 1
            logger.error(f"消息序列化错误: {e}")
            raise ValueError(f"消息序列化失败: {e}")
    
    def create_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> MCPRequest:
        """创建请求消息"""
        request = MCPRequest.create(method, params)
        
        # 记录待处理请求
        self.pending_requests[request.id] = request
        
        logger.debug(f"创建MCP请求: {method} (ID: {request.id})")
        
        return request
    
    def create_response(self, request: MCPRequest, result: Any = None, error_code: Optional[int] = None, error_message: Optional[str] = None) -> MCPResponse:
        """创建响应消息"""
        if error_code is not None:
            response = MCPResponse.create_error(request.id, error_code, error_message or "Unknown error")
        else:
            response = MCPResponse.create_success(request.id, result)
        
        # 移除待处理请求
        self.pending_requests.pop(request.id, None)
        
        logger.debug(f"创建MCP响应: {request.method} (ID: {request.id})")
        
        return response
    
    def create_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> MCPNotification:
        """创建通知消息"""
        notification = MCPNotification.create(method, params)
        
        logger.debug(f"创建MCP通知: {method}")
        
        return notification
    
    def validate_message(self, message: MCPMessage) -> bool:
        """验证消息"""
        try:
            # 基本验证
            if message.jsonrpc != "2.0":
                return False
            
            # 请求验证
            if message.is_request():
                if not message.method or message.id is None:
                    return False
            
            # 响应验证
            elif message.is_response():
                if message.id is None:
                    return False
                if message.result is None and message.error is None:
                    return False
            
            # 通知验证
            elif message.is_notification():
                if not message.method:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"消息验证错误: {e}")
            return False
    
    def handle_response(self, response: MCPResponse) -> Optional[MCPRequest]:
        """处理响应消息"""
        request = self.pending_requests.pop(response.id, None)
        
        if request:
            logger.debug(f"处理MCP响应: {request.method} (ID: {response.id})")
        else:
            logger.warning(f"收到未知请求的响应: ID {response.id}")
        
        return request
    
    def register_handler(self, method: str, handler: callable):
        """注册消息处理器"""
        self.message_handlers[method] = handler
        logger.debug(f"注册MCP处理器: {method}")
    
    async def handle_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """处理消息"""
        try:
            if not self.validate_message(message):
                if message.is_request():
                    return MCPResponse.create_error(
                        message.id, 
                        MCPError.INVALID_REQUEST, 
                        "Invalid request format"
                    )
                return None
            
            if message.is_request():
                return await self._handle_request(message)
            elif message.is_response():
                self.handle_response(message)
                return None
            elif message.is_notification():
                await self._handle_notification(message)
                return None
            
        except Exception as e:
            self.errors_count += 1
            logger.error(f"处理MCP消息失败: {e}")
            
            if message.is_request():
                return MCPResponse.create_error(
                    message.id,
                    MCPError.INTERNAL_ERROR,
                    f"Internal error: {str(e)}"
                )
        
        return None
    
    async def _handle_request(self, request: MCPMessage) -> MCPResponse:
        """处理请求消息"""
        method = request.method
        
        # 查找处理器
        handler = self.message_handlers.get(method)
        
        if not handler:
            return MCPResponse.create_error(
                request.id,
                MCPError.METHOD_NOT_FOUND,
                f"Method not found: {method}"
            )
        
        try:
            # 调用处理器
            result = await handler(request.params or {})
            
            return MCPResponse.create_success(request.id, result)
            
        except Exception as e:
            logger.error(f"处理器执行失败: {method} - {e}")
            return MCPResponse.create_error(
                request.id,
                MCPError.INTERNAL_ERROR,
                f"Handler error: {str(e)}"
            )
    
    async def _handle_notification(self, notification: MCPMessage):
        """处理通知消息"""
        method = notification.method
        
        # 查找处理器
        handler = self.message_handlers.get(method)
        
        if handler:
            try:
                await handler(notification.params or {})
            except Exception as e:
                logger.error(f"通知处理器执行失败: {method} - {e}")
        else:
            logger.debug(f"未找到通知处理器: {method}")
    
    def get_pending_requests(self) -> List[MCPRequest]:
        """获取待处理请求"""
        return list(self.pending_requests.values())
    
    def clear_pending_requests(self):
        """清除所有待处理请求"""
        count = len(self.pending_requests)
        self.pending_requests.clear()
        logger.info(f"清除了 {count} 个待处理请求")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "server_name": self.server_name,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "errors_count": self.errors_count,
            "pending_requests": len(self.pending_requests),
            "registered_handlers": len(self.message_handlers),
            "last_activity": self.last_activity.isoformat()
        }
    
    def reset_statistics(self):
        """重置统计信息"""
        self.messages_sent = 0
        self.messages_received = 0
        self.errors_count = 0
        self.last_activity = datetime.now()
        
        logger.info(f"已重置MCP协议处理器统计信息: {self.server_name}")
    
    def __str__(self):
        return f"MCPProtocolHandler({self.server_name})"
    
    def __repr__(self):
        return self.__str__()