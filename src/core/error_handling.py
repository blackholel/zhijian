"""
错误处理和重试机制
提供统一的错误处理、重试策略和优雅降级功能
"""
import asyncio
import logging
import traceback
from typing import Dict, List, Any, Optional, Callable, Union, Type
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from functools import wraps
import random
import json

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """错误类型"""
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    AUTHENTICATION_ERROR = "authentication_error"
    PERMISSION_ERROR = "permission_error"
    VALIDATION_ERROR = "validation_error"
    RESOURCE_ERROR = "resource_error"
    LLM_ERROR = "llm_error"
    AGENT_ERROR = "agent_error"
    WORKFLOW_ERROR = "workflow_error"
    SYSTEM_ERROR = "system_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(Enum):
    """错误严重性"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RetryStrategy(Enum):
    """重试策略"""
    NO_RETRY = "no_retry"
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    JITTERED_BACKOFF = "jittered_backoff"


@dataclass
class ErrorInfo:
    """错误信息"""
    error_id: str
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    is_recoverable: bool = True


@dataclass
class RetryConfig:
    """重试配置"""
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_errors: List[ErrorType] = field(default_factory=lambda: [
        ErrorType.NETWORK_ERROR,
        ErrorType.TIMEOUT_ERROR,
        ErrorType.LLM_ERROR,
        ErrorType.SYSTEM_ERROR
    ])


class YuxiKnowError(Exception):
    """Yuxi-Know 基础异常类"""
    
    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        is_recoverable: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.severity = severity
        self.details = details or {}
        self.context = context or {}
        self.is_recoverable = is_recoverable
        self.timestamp = datetime.now()
        self.error_id = f"err_{int(self.timestamp.timestamp())}_{id(self)}"


class AgentError(YuxiKnowError):
    """Agent相关错误"""
    
    def __init__(self, message: str, agent_id: str = "", **kwargs):
        super().__init__(message, ErrorType.AGENT_ERROR, **kwargs)
        self.agent_id = agent_id
        self.context["agent_id"] = agent_id


class WorkflowError(YuxiKnowError):
    """工作流相关错误"""
    
    def __init__(self, message: str, workflow_id: str = "", execution_id: str = "", **kwargs):
        super().__init__(message, ErrorType.WORKFLOW_ERROR, **kwargs)
        self.workflow_id = workflow_id
        self.execution_id = execution_id
        self.context.update({
            "workflow_id": workflow_id,
            "execution_id": execution_id
        })


class LLMError(YuxiKnowError):
    """LLM服务相关错误"""
    
    def __init__(self, message: str, provider: str = "", model: str = "", **kwargs):
        super().__init__(message, ErrorType.LLM_ERROR, **kwargs)
        self.provider = provider
        self.model = model
        self.context.update({
            "provider": provider,
            "model": model
        })


class KnowledgeBaseError(YuxiKnowError):
    """知识库相关错误"""
    
    def __init__(self, message: str, kb_id: str = "", **kwargs):
        super().__init__(message, ErrorType.RESOURCE_ERROR, **kwargs)
        self.kb_id = kb_id
        self.context["kb_id"] = kb_id


class MCPError(YuxiKnowError):
    """MCP工具相关错误"""
    
    def __init__(self, message: str, tool_name: str = "", server_name: str = "", **kwargs):
        super().__init__(message, ErrorType.RESOURCE_ERROR, **kwargs)
        self.tool_name = tool_name
        self.server_name = server_name
        self.context.update({
            "tool_name": tool_name,
            "server_name": server_name
        })


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self):
        self.error_history: List[ErrorInfo] = []
        self.error_callbacks: Dict[ErrorType, List[Callable]] = {}
        self.global_callbacks: List[Callable] = []
        self.circuit_breakers: Dict[str, 'CircuitBreaker'] = {}
        
    def register_callback(
        self, 
        callback: Callable, 
        error_types: Optional[List[ErrorType]] = None
    ):
        """注册错误回调"""
        if error_types:
            for error_type in error_types:
                if error_type not in self.error_callbacks:
                    self.error_callbacks[error_type] = []
                self.error_callbacks[error_type].append(callback)
        else:
            self.global_callbacks.append(callback)
    
    async def handle_error(self, error: Union[Exception, YuxiKnowError]) -> ErrorInfo:
        """处理错误"""
        
        # 转换为ErrorInfo
        if isinstance(error, YuxiKnowError):
            error_info = ErrorInfo(
                error_id=error.error_id,
                error_type=error.error_type,
                severity=error.severity,
                message=error.message,
                details=error.details,
                timestamp=error.timestamp,
                stack_trace=traceback.format_exc(),
                context=error.context,
                is_recoverable=error.is_recoverable
            )
        else:
            error_info = ErrorInfo(
                error_id=f"err_{int(datetime.now().timestamp())}_{id(error)}",
                error_type=self._classify_error(error),
                severity=ErrorSeverity.MEDIUM,
                message=str(error),
                stack_trace=traceback.format_exc(),
                is_recoverable=True
            )
        
        # 记录错误
        self.error_history.append(error_info)
        logger.error(f"Error handled: {error_info.error_id} - {error_info.message}")
        
        # 触发回调
        await self._trigger_callbacks(error_info)
        
        return error_info
    
    def _classify_error(self, error: Exception) -> ErrorType:
        """分类错误"""
        error_name = type(error).__name__.lower()
        
        if "network" in error_name or "connection" in error_name:
            return ErrorType.NETWORK_ERROR
        elif "timeout" in error_name:
            return ErrorType.TIMEOUT_ERROR
        elif "auth" in error_name or "permission" in error_name:
            return ErrorType.AUTHENTICATION_ERROR
        elif "validation" in error_name or "value" in error_name:
            return ErrorType.VALIDATION_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR
    
    async def _trigger_callbacks(self, error_info: ErrorInfo):
        """触发错误回调"""
        
        # 触发特定错误类型的回调
        if error_info.error_type in self.error_callbacks:
            for callback in self.error_callbacks[error_info.error_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(error_info)
                    else:
                        callback(error_info)
                except Exception as e:
                    logger.error(f"Error callback failed: {e}")
        
        # 触发全局回调
        for callback in self.global_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error_info)
                else:
                    callback(error_info)
            except Exception as e:
                logger.error(f"Global error callback failed: {e}")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计"""
        if not self.error_history:
            return {"total_errors": 0}
        
        # 按类型统计
        type_counts = {}
        severity_counts = {}
        recent_errors = 0
        
        recent_threshold = datetime.now() - timedelta(hours=1)
        
        for error in self.error_history:
            # 类型统计
            error_type = error.error_type.value
            type_counts[error_type] = type_counts.get(error_type, 0) + 1
            
            # 严重性统计
            severity = error.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            # 最近错误统计
            if error.timestamp > recent_threshold:
                recent_errors += 1
        
        return {
            "total_errors": len(self.error_history),
            "error_types": type_counts,
            "error_severities": severity_counts,
            "recent_errors": recent_errors,
            "error_rate": recent_errors / 60  # 每分钟错误数
        }


class RetryManager:
    """重试管理器"""
    
    def __init__(self, default_config: Optional[RetryConfig] = None):
        self.default_config = default_config or RetryConfig()
        self.retry_history: Dict[str, List[datetime]] = {}
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        config: Optional[RetryConfig] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """带重试的执行函数"""
        
        retry_config = config or self.default_config
        operation_id = f"{func.__name__}_{id(func)}"
        
        for attempt in range(retry_config.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # 成功执行，清理重试历史
                if operation_id in self.retry_history:
                    del self.retry_history[operation_id]
                
                return result
                
            except Exception as e:
                # 记录重试历史
                if operation_id not in self.retry_history:
                    self.retry_history[operation_id] = []
                self.retry_history[operation_id].append(datetime.now())
                
                # 判断是否应该重试
                if attempt >= retry_config.max_retries:
                    logger.error(f"Operation {operation_id} failed after {attempt + 1} attempts: {e}")
                    raise e
                
                # 检查是否为可重试错误
                error_type = self._get_error_type(e)
                if error_type not in retry_config.retryable_errors:
                    logger.error(f"Non-retryable error in {operation_id}: {e}")
                    raise e
                
                # 计算延迟时间
                delay = self._calculate_delay(retry_config, attempt)
                
                logger.warning(f"Operation {operation_id} failed (attempt {attempt + 1}/{retry_config.max_retries + 1}), retrying in {delay:.2f}s: {e}")
                
                await asyncio.sleep(delay)
    
    def _get_error_type(self, error: Exception) -> ErrorType:
        """获取错误类型"""
        if isinstance(error, YuxiKnowError):
            return error.error_type
        
        # 根据异常类型推断
        error_name = type(error).__name__.lower()
        
        if "network" in error_name or "connection" in error_name:
            return ErrorType.NETWORK_ERROR
        elif "timeout" in error_name:
            return ErrorType.TIMEOUT_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR
    
    def _calculate_delay(self, config: RetryConfig, attempt: int) -> float:
        """计算重试延迟"""
        
        if config.strategy == RetryStrategy.NO_RETRY:
            return 0
        
        elif config.strategy == RetryStrategy.FIXED_DELAY:
            delay = config.base_delay
        
        elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = config.base_delay * (attempt + 1)
        
        elif config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = config.base_delay * (config.backoff_factor ** attempt)
        
        elif config.strategy == RetryStrategy.JITTERED_BACKOFF:
            base_delay = config.base_delay * (config.backoff_factor ** attempt)
            jitter = random.uniform(0, base_delay * 0.1)
            delay = base_delay + jitter
        
        else:
            delay = config.base_delay
        
        # 应用最大延迟限制
        delay = min(delay, config.max_delay)
        
        # 应用抖动
        if config.jitter and config.strategy != RetryStrategy.JITTERED_BACKOFF:
            jitter = random.uniform(-delay * 0.1, delay * 0.1)
            delay += jitter
        
        return max(0, delay)


class CircuitBreaker:
    """熔断器"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """通过熔断器调用函数"""
        
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
            else:
                raise YuxiKnowError(
                    "Circuit breaker is open",
                    ErrorType.SYSTEM_ERROR,
                    ErrorSeverity.HIGH,
                    is_recoverable=False
                )
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置"""
        return (
            self.last_failure_time and 
            datetime.now().timestamp() - self.last_failure_time > self.recovery_timeout
        )
    
    def _on_success(self):
        """成功时的处理"""
        self.failure_count = 0
        self.state = "closed"
    
    def _on_failure(self):
        """失败时的处理"""
        self.failure_count += 1
        self.last_failure_time = datetime.now().timestamp()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class GracefulDegradation:
    """优雅降级"""
    
    def __init__(self):
        self.fallback_handlers: Dict[str, Callable] = {}
        self.degradation_rules: List[Dict[str, Any]] = []
    
    def register_fallback(self, service_name: str, fallback_handler: Callable):
        """注册降级处理器"""
        self.fallback_handlers[service_name] = fallback_handler
    
    def add_degradation_rule(
        self,
        condition: Callable,
        action: str,
        params: Optional[Dict[str, Any]] = None
    ):
        """添加降级规则"""
        self.degradation_rules.append({
            "condition": condition,
            "action": action,
            "params": params or {}
        })
    
    async def execute_with_fallback(
        self,
        service_name: str,
        primary_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """带降级的执行"""
        
        try:
            # 检查降级规则
            for rule in self.degradation_rules:
                if rule["condition"]():
                    if rule["action"] == "fallback":
                        return await self._execute_fallback(service_name, *args, **kwargs)
                    elif rule["action"] == "skip":
                        return None
                    elif rule["action"] == "cache":
                        return await self._get_cached_result(service_name, *args, **kwargs)
            
            # 执行主要功能
            if asyncio.iscoroutinefunction(primary_func):
                return await primary_func(*args, **kwargs)
            else:
                return primary_func(*args, **kwargs)
                
        except Exception as e:
            logger.warning(f"Primary function failed for {service_name}, using fallback: {e}")
            return await self._execute_fallback(service_name, *args, **kwargs)
    
    async def _execute_fallback(self, service_name: str, *args, **kwargs) -> Any:
        """执行降级处理"""
        if service_name in self.fallback_handlers:
            fallback = self.fallback_handlers[service_name]
            if asyncio.iscoroutinefunction(fallback):
                return await fallback(*args, **kwargs)
            else:
                return fallback(*args, **kwargs)
        else:
            logger.error(f"No fallback handler for service: {service_name}")
            return None
    
    async def _get_cached_result(self, service_name: str, *args, **kwargs) -> Any:
        """获取缓存结果"""
        # 这里应该实现缓存逻辑
        return None


# 装饰器
def retry(config: Optional[RetryConfig] = None):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retry_manager = RetryManager()
            return await retry_manager.execute_with_retry(func, *args, config=config, **kwargs)
        return wrapper
    return decorator


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: Type[Exception] = Exception
):
    """熔断器装饰器"""
    def decorator(func):
        breaker = CircuitBreaker(failure_threshold, recovery_timeout, expected_exception)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator


def handle_errors(error_handler: Optional[ErrorHandler] = None):
    """错误处理装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                if error_handler:
                    await error_handler.handle_error(e)
                raise
        return wrapper
    return decorator


# 全局实例
global_error_handler = ErrorHandler()
global_retry_manager = RetryManager()
global_graceful_degradation = GracefulDegradation()


# 工具函数
async def safe_execute(
    func: Callable,
    *args,
    fallback_result: Any = None,
    log_errors: bool = True,
    **kwargs
) -> Any:
    """安全执行函数"""
    try:
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"Safe execution failed: {e}")
        return fallback_result


def create_error_context(
    operation: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """创建错误上下文"""
    context = {
        "operation": operation,
        "timestamp": datetime.now().isoformat()
    }
    
    if user_id:
        context["user_id"] = user_id
    if session_id:
        context["session_id"] = session_id
    if additional_context:
        context.update(additional_context)
    
    return context


# 配置默认的降级处理器
async def default_llm_fallback(*args, **kwargs):
    """LLM服务降级处理"""
    return {
        "success": False,
        "result": "LLM服务暂时不可用，请稍后重试",
        "fallback": True
    }


async def default_kb_fallback(*args, **kwargs):
    """知识库服务降级处理"""
    return {
        "success": False,
        "results": [],
        "message": "知识库服务暂时不可用",
        "fallback": True
    }


async def default_mcp_fallback(*args, **kwargs):
    """MCP工具降级处理"""
    return {
        "success": False,
        "result": "工具服务暂时不可用",
        "fallback": True
    }


# 注册默认降级处理器
global_graceful_degradation.register_fallback("llm_service", default_llm_fallback)
global_graceful_degradation.register_fallback("knowledge_base", default_kb_fallback)
global_graceful_degradation.register_fallback("mcp_tools", default_mcp_fallback)