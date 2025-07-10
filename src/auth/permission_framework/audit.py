"""
权限审计系统
记录和监控权限检查活动
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import asyncio
from collections import defaultdict

from .core import PermissionContext, PermissionResult
from src.database.manager import get_database_manager
from sqlalchemy import text

logger = logging.getLogger(__name__)

@dataclass
class PermissionAuditLog:
    """权限审计日志"""
    id: str
    timestamp: datetime
    user_id: str
    resource_uri: Optional[str]
    permission: str
    result: bool
    strategy_used: str
    reason: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    session_id: Optional[str]
    request_metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data

class PermissionAuditLogger:
    """权限审计日志记录器"""
    
    def __init__(self, enable_db_logging: bool = True, enable_file_logging: bool = True):
        self.enable_db_logging = enable_db_logging
        self.enable_file_logging = enable_file_logging
        self.log_queue = asyncio.Queue()
        self.stats = defaultdict(int)
        self._running = False
        
        # 设置文件日志
        if enable_file_logging:
            # 确保日志目录存在
            import os
            os.makedirs('logs', exist_ok=True)
            
            self.file_logger = logging.getLogger('permission_audit')
            handler = logging.FileHandler('logs/permission_audit.log')
            formatter = logging.Formatter('%(asctime)s - %(message)s')
            handler.setFormatter(formatter)
            self.file_logger.addHandler(handler)
            self.file_logger.setLevel(logging.INFO)
    
    async def start(self):
        """启动审计日志处理"""
        if not self._running:
            self._running = True
            asyncio.create_task(self._process_log_queue())
            logger.info("Permission audit logger started")
    
    async def stop(self):
        """停止审计日志处理"""
        self._running = False
        logger.info("Permission audit logger stopped")
    
    async def log_permission_check(self, context: PermissionContext, result: PermissionResult):
        """记录权限检查"""
        audit_log = PermissionAuditLog(
            id=f"{context.user_id}_{int(context.timestamp.timestamp() * 1000)}",
            timestamp=context.timestamp,
            user_id=context.user_id,
            resource_uri=context.resource.uri if context.resource else None,
            permission=context.permission.value,
            result=result.allowed,
            strategy_used=result.strategy_used,
            reason=result.reason,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            session_id=context.session_id,
            request_metadata=context.request_metadata
        )
        
        # 异步处理日志
        await self.log_queue.put(audit_log)
        
        # 更新统计
        self.stats['total_checks'] += 1
        if result.allowed:
            self.stats['allowed_checks'] += 1
        else:
            self.stats['denied_checks'] += 1
        self.stats[f'strategy_{result.strategy_used}'] += 1
    
    async def _process_log_queue(self):
        """处理日志队列"""
        while self._running:
            try:
                audit_log = await asyncio.wait_for(self.log_queue.get(), timeout=1.0)
                await self._write_log(audit_log)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing audit log: {e}")
    
    async def _write_log(self, audit_log: PermissionAuditLog):
        """写入日志"""
        # 写入文件
        if self.enable_file_logging:
            log_data = audit_log.to_dict()
            self.file_logger.info(json.dumps(log_data, ensure_ascii=False))
        
        # 写入数据库
        if self.enable_db_logging:
            await self._write_to_database(audit_log)
    
    async def _write_to_database(self, audit_log: PermissionAuditLog):
        """写入数据库"""
        try:
            from src.database.manager import get_database_manager
            db_manager = get_database_manager()
            await db_manager.initialize()
            
            # 创建审计表（如果不存在）
            await self._ensure_audit_table(db_manager)
            
            # 插入审计记录
            postgres_adapter = await db_manager.get_postgresql_adapter('server_db')
            await postgres_adapter.execute_query("""
                INSERT INTO permission_audit_logs (
                    id, timestamp, user_id, resource_uri, permission, 
                    result, strategy_used, reason, ip_address, user_agent,
                    session_id, request_metadata
                ) VALUES (
                    :id, :timestamp, :user_id, :resource_uri, :permission,
                    :result, :strategy_used, :reason, :ip_address, :user_agent,
                    :session_id, :request_metadata
                )
            """, {
                "id": audit_log.id,
                "timestamp": audit_log.timestamp,
                "user_id": audit_log.user_id,
                "resource_uri": audit_log.resource_uri,
                "permission": audit_log.permission,
                "result": audit_log.result,
                "strategy_used": audit_log.strategy_used,
                "reason": audit_log.reason,
                "ip_address": audit_log.ip_address,
                "user_agent": audit_log.user_agent,
                "session_id": audit_log.session_id,
                "request_metadata": json.dumps(audit_log.request_metadata)
            })
        except Exception as e:
            logger.error(f"Error writing audit log to database: {e}")
    
    async def _ensure_audit_table(self, db_manager):
        """确保审计表存在"""
        try:
            postgres_adapter = await db_manager.get_postgresql_adapter('server_db')
            
            await postgres_adapter.execute_query("""
                CREATE TABLE IF NOT EXISTS permission_audit_logs (
                    id VARCHAR PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    user_id VARCHAR NOT NULL,
                    resource_uri VARCHAR,
                    permission VARCHAR NOT NULL,
                    result BOOLEAN NOT NULL,
                    strategy_used VARCHAR NOT NULL,
                    reason TEXT,
                    ip_address VARCHAR,
                    user_agent TEXT,
                    session_id VARCHAR,
                    request_metadata TEXT
                )
            """)
            
            # 创建索引
            await postgres_adapter.execute_query("""
                CREATE INDEX IF NOT EXISTS idx_audit_user_timestamp 
                ON permission_audit_logs(user_id, timestamp)
            """)
            
            await postgres_adapter.execute_query("""
                CREATE INDEX IF NOT EXISTS idx_audit_resource 
                ON permission_audit_logs(resource_uri)
            """)
        except Exception as e:
            logger.error(f"Error ensuring audit table: {e}")
    
    async def query_audit_logs(
        self,
        user_id: Optional[str] = None,
        resource_uri: Optional[str] = None,
        permission: Optional[str] = None,
        result: Optional[bool] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """查询审计日志"""
        db_manager = get_database_manager()
        await db_manager.initialize()
        db = db_manager.get_session_sync()
        try:
            conditions = []
            params = {}
            
            if user_id:
                conditions.append("user_id = :user_id")
                params["user_id"] = user_id
            
            if resource_uri:
                conditions.append("resource_uri = :resource_uri")
                params["resource_uri"] = resource_uri
            
            if permission:
                conditions.append("permission = :permission")
                params["permission"] = permission
            
            if result is not None:
                conditions.append("result = :result")
                params["result"] = result
            
            if start_time:
                conditions.append("timestamp >= :start_time")
                params["start_time"] = start_time
            
            if end_time:
                conditions.append("timestamp <= :end_time")
                params["end_time"] = end_time
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT * FROM permission_audit_logs 
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT :limit
            """
            params["limit"] = limit
            
            result = db.execute(text(query), params)
            logs = []
            for row in result:
                log_data = dict(row._mapping)
                if log_data.get('request_metadata'):
                    try:
                        log_data['request_metadata'] = json.loads(log_data['request_metadata'])
                    except:
                        log_data['request_metadata'] = {}
                logs.append(log_data)
            
            return logs
        finally:
            db.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = self.stats.get('total_checks', 0)
        allowed = self.stats.get('allowed_checks', 0)
        denied = self.stats.get('denied_checks', 0)
        
        stats = {
            "total_checks": total,
            "allowed_checks": allowed,
            "denied_checks": denied,
            "allow_rate": allowed / total if total > 0 else 0,
            "deny_rate": denied / total if total > 0 else 0,
            "strategy_usage": {}
        }
        
        # 策略使用统计
        for key, value in self.stats.items():
            if key.startswith('strategy_'):
                strategy_name = key[9:]  # 移除 'strategy_' 前缀
                stats["strategy_usage"][strategy_name] = value
        
        return stats

class PermissionPerformanceMonitor:
    """权限系统性能监控"""
    
    def __init__(self):
        self.metrics = {
            "permission_checks_total": 0,
            "permission_checks_duration": [],
            "cache_hit_rate": 0.0,
            "strategy_usage": defaultdict(int),
            "error_count": 0
        }
        self.start_time = datetime.now()
    
    async def record_permission_check(
        self, 
        context: PermissionContext, 
        result: PermissionResult, 
        duration: float
    ):
        """记录权限检查指标"""
        self.metrics["permission_checks_total"] += 1
        self.metrics["permission_checks_duration"].append(duration)
        self.metrics["strategy_usage"][result.strategy_used] += 1
        
        # 只保留最近1000次的持续时间记录
        if len(self.metrics["permission_checks_duration"]) > 1000:
            self.metrics["permission_checks_duration"] = self.metrics["permission_checks_duration"][-1000:]
        
        # 更新缓存命中率
        from .engine import PermissionEngine
        engine = PermissionEngine.get_instance()
        if engine.cache_manager:
            stats = engine.cache_manager.get_cache_stats()
            self.metrics["cache_hit_rate"] = stats["l1_hit_rate"] + stats["l2_hit_rate"]
    
    def record_error(self):
        """记录错误"""
        self.metrics["error_count"] += 1
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        durations = self.metrics["permission_checks_duration"]
        if durations:
            avg_duration = sum(durations) / len(durations)
            durations_sorted = sorted(durations)
            p95_duration = durations_sorted[int(len(durations_sorted) * 0.95)]
            p99_duration = durations_sorted[int(len(durations_sorted) * 0.99)]
        else:
            avg_duration = p95_duration = p99_duration = 0
        
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "uptime_seconds": uptime,
            "total_checks": self.metrics["permission_checks_total"],
            "checks_per_second": self.metrics["permission_checks_total"] / uptime if uptime > 0 else 0,
            "cache_hit_rate": self.metrics["cache_hit_rate"],
            "avg_duration_ms": avg_duration * 1000,
            "p95_duration_ms": p95_duration * 1000,
            "p99_duration_ms": p99_duration * 1000,
            "error_count": self.metrics["error_count"],
            "error_rate": self.metrics["error_count"] / self.metrics["permission_checks_total"] if self.metrics["permission_checks_total"] > 0 else 0,
            "strategy_usage": dict(self.metrics["strategy_usage"])
        }