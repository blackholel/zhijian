"""
文件状态监控和可观测性服务

单一职责：专门管理性能监控和指标收集
清晰边界：与业务逻辑分离，专注于可观测性
可扩展接口：支持多种监控指标和告警
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict, deque

from ..database.connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    operation: str
    duration: float
    timestamp: str
    success: bool
    error_message: Optional[str] = None
    kb_id: Optional[str] = None
    file_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemMetrics:
    """系统指标数据类"""
    memory_cache_size: int
    redis_connections: int
    active_subscriptions: int
    total_requests: int
    error_rate: float
    average_response_time: float
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PerformanceMonitor:
    """性能监控器 - 可观测性核心"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        self.connection_manager = connection_manager
        
        # 指标存储 (内存中保留最近的指标)
        self.metrics_buffer = deque(maxlen=1000)  # 最多保留1000条指标
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.response_times = defaultdict(list)
        
        # 系统状态
        self.start_time = time.time()
        self.last_cleanup = time.time()
        
        # 配置
        self.cleanup_interval = 300  # 5分钟清理一次
        self.metrics_retention = 3600  # 保留1小时的指标
        
    def record_operation(self, operation: str, duration: float, 
                        success: bool = True, error_message: str = None,
                        kb_id: str = None, file_id: str = None):
        """记录操作指标"""
        try:
            metric = PerformanceMetrics(
                operation=operation,
                duration=duration,
                timestamp=datetime.now().isoformat(),
                success=success,
                error_message=error_message,
                kb_id=kb_id,
                file_id=file_id
            )
            
            self.metrics_buffer.append(metric)
            
            # 更新统计计数
            self.request_counts[operation] += 1
            if not success:
                self.error_counts[operation] += 1
            
            # 记录响应时间
            self.response_times[operation].append(duration)
            # 保持响应时间列表大小
            if len(self.response_times[operation]) > 100:
                self.response_times[operation] = self.response_times[operation][-100:]
            
            # 定期清理
            self._cleanup_if_needed()
            
        except Exception as e:
            logger.warning(f"记录性能指标失败: {e}")
    
    def get_metrics_summary(self, operation: str = None, 
                          time_window: int = 3600) -> Dict[str, Any]:
        """获取指标摘要"""
        try:
            now = time.time()
            cutoff_time = datetime.fromtimestamp(now - time_window)
            
            # 过滤时间窗口内的指标
            filtered_metrics = [
                m for m in self.metrics_buffer
                if datetime.fromisoformat(m.timestamp) > cutoff_time
                and (operation is None or m.operation == operation)
            ]
            
            if not filtered_metrics:
                return {
                    "operation": operation or "all",
                    "total_requests": 0,
                    "error_rate": 0.0,
                    "average_response_time": 0.0,
                    "time_window_minutes": time_window // 60
                }
            
            # 计算统计信息
            total_requests = len(filtered_metrics)
            error_count = sum(1 for m in filtered_metrics if not m.success)
            error_rate = (error_count / total_requests) * 100 if total_requests > 0 else 0.0
            
            response_times = [m.duration for m in filtered_metrics]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
            
            return {
                "operation": operation or "all",
                "total_requests": total_requests,
                "error_count": error_count,
                "error_rate": round(error_rate, 2),
                "average_response_time": round(avg_response_time, 3),
                "min_response_time": round(min(response_times), 3) if response_times else 0.0,
                "max_response_time": round(max(response_times), 3) if response_times else 0.0,
                "time_window_minutes": time_window // 60,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取指标摘要失败: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_system_metrics(self) -> SystemMetrics:
        """获取系统指标"""
        try:
            # 计算总体错误率
            total_requests = sum(self.request_counts.values())
            total_errors = sum(self.error_counts.values())
            error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0.0
            
            # 计算平均响应时间
            all_response_times = []
            for times in self.response_times.values():
                all_response_times.extend(times)
            avg_response_time = sum(all_response_times) / len(all_response_times) if all_response_times else 0.0
            
            return SystemMetrics(
                memory_cache_size=len(self.metrics_buffer),
                redis_connections=self._get_redis_connection_count(),
                active_subscriptions=0,  # 需要从Redis适配器获取
                total_requests=total_requests,
                error_rate=round(error_rate, 2),
                average_response_time=round(avg_response_time, 3),
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"获取系统指标失败: {e}")
            return SystemMetrics(
                memory_cache_size=0,
                redis_connections=0,
                active_subscriptions=0,
                total_requests=0,
                error_rate=0.0,
                average_response_time=0.0,
                timestamp=datetime.now().isoformat()
            )
    
    def get_operation_breakdown(self) -> Dict[str, Any]:
        """获取操作分解统计"""
        try:
            breakdown = {}
            
            for operation in self.request_counts.keys():
                summary = self.get_metrics_summary(operation, 3600)  # 1小时窗口
                breakdown[operation] = summary
            
            return {
                "operations": breakdown,
                "total_operations": len(breakdown),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取操作分解失败: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_error_analysis(self) -> Dict[str, Any]:
        """获取错误分析"""
        try:
            # 获取最近的错误
            error_metrics = [m for m in self.metrics_buffer if not m.success]
            recent_errors = error_metrics[-50:]  # 最近50个错误
            
            # 按错误类型分组
            error_types = defaultdict(list)
            for error in recent_errors:
                error_type = error.error_message or "unknown_error"
                error_types[error_type].append(error)
            
            # 构造错误分析
            analysis = {
                "total_errors": len(error_metrics),
                "recent_errors_count": len(recent_errors),
                "error_types": {},
                "top_error_operations": [],
                "timestamp": datetime.now().isoformat()
            }
            
            # 错误类型统计
            for error_type, errors in error_types.items():
                analysis["error_types"][error_type] = {
                    "count": len(errors),
                    "operations": list(set(e.operation for e in errors)),
                    "latest_occurrence": max(e.timestamp for e in errors)
                }
            
            # 错误最多的操作
            operation_errors = defaultdict(int)
            for error in recent_errors:
                operation_errors[error.operation] += 1
            
            analysis["top_error_operations"] = [
                {"operation": op, "error_count": count}
                for op, count in sorted(operation_errors.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
            
            return analysis
            
        except Exception as e:
            logger.error(f"错误分析失败: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def _cleanup_if_needed(self):
        """定期清理过期数据"""
        now = time.time()
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_data()
            self.last_cleanup = now
    
    def _cleanup_old_data(self):
        """清理过期数据"""
        try:
            # 清理过期的响应时间数据
            for operation in list(self.response_times.keys()):
                if len(self.response_times[operation]) > 100:
                    self.response_times[operation] = self.response_times[operation][-100:]
            
            logger.debug("性能数据清理完成")
            
        except Exception as e:
            logger.warning(f"性能数据清理失败: {e}")
    
    def _get_redis_connection_count(self) -> int:
        """获取Redis连接数"""
        try:
            # 这里可以从Redis适配器获取连接信息
            return 1  # 简化实现
        except Exception:
            return 0
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            uptime = time.time() - self.start_time
            
            return {
                "status": "healthy",
                "uptime_seconds": round(uptime, 2),
                "metrics_buffer_size": len(self.metrics_buffer),
                "total_operations_tracked": len(self.request_counts),
                "memory_usage_mb": self._estimate_memory_usage(),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def _estimate_memory_usage(self) -> float:
        """估计内存使用量(MB)"""
        try:
            import sys
            
            # 估算指标缓冲区大小
            buffer_size = sys.getsizeof(self.metrics_buffer)
            for metric in self.metrics_buffer:
                buffer_size += sys.getsizeof(metric)
            
            # 估算其他数据结构大小
            other_size = (
                sys.getsizeof(self.request_counts) +
                sys.getsizeof(self.error_counts) +
                sys.getsizeof(self.response_times)
            )
            
            total_bytes = buffer_size + other_size
            return round(total_bytes / (1024 * 1024), 2)
            
        except Exception:
            return 0.0


def monitor_performance(operation: str):
    """性能监控装饰器"""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                error_message = None
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error_message = str(e)
                    raise
                finally:
                    duration = time.time() - start_time
                    # 这里需要访问监控器实例，可以通过全局变量或依赖注入
                    logger.debug(f"{operation} 耗时: {duration:.3f}s, 成功: {success}")
            
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                error_message = None
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error_message = str(e)
                    raise
                finally:
                    duration = time.time() - start_time
                    logger.debug(f"{operation} 耗时: {duration:.3f}s, 成功: {success}")
            
            return sync_wrapper
    
    return decorator


class AlertManager:
    """告警管理器"""
    
    def __init__(self, monitor: PerformanceMonitor):
        self.monitor = monitor
        self.alert_thresholds = {
            "error_rate": 10.0,  # 错误率超过10%
            "response_time": 5.0,  # 响应时间超过5秒
            "memory_usage": 100.0  # 内存使用超过100MB
        }
        self.alert_history = deque(maxlen=100)
    
    def check_alerts(self) -> List[Dict[str, Any]]:
        """检查告警条件"""
        alerts = []
        
        try:
            # 检查错误率
            system_metrics = self.monitor.get_system_metrics()
            
            if system_metrics.error_rate > self.alert_thresholds["error_rate"]:
                alerts.append({
                    "type": "error_rate",
                    "severity": "warning",
                    "message": f"错误率过高: {system_metrics.error_rate}%",
                    "threshold": self.alert_thresholds["error_rate"],
                    "current_value": system_metrics.error_rate,
                    "timestamp": datetime.now().isoformat()
                })
            
            if system_metrics.average_response_time > self.alert_thresholds["response_time"]:
                alerts.append({
                    "type": "response_time",
                    "severity": "warning",
                    "message": f"响应时间过长: {system_metrics.average_response_time}s",
                    "threshold": self.alert_thresholds["response_time"],
                    "current_value": system_metrics.average_response_time,
                    "timestamp": datetime.now().isoformat()
                })
            
            # 记录告警历史
            for alert in alerts:
                self.alert_history.append(alert)
            
        except Exception as e:
            logger.error(f"告警检查失败: {e}")
        
        return alerts
    
    def get_alert_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取告警历史"""
        return list(self.alert_history)[-limit:]