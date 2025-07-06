"""
权限框架管理器
统一初始化和管理权限系统的各个组件
"""

import logging
from typing import Optional
import asyncio

from .engine import PermissionEngine
from .cache import UnifiedPermissionCache, CacheInvalidationManager
from .audit import PermissionAuditLogger, PermissionPerformanceMonitor
from .concrete_resources import ResourceFactory
# 使用新的数据库架构中的Redis适配器
from src.database.manager import get_database_manager

logger = logging.getLogger(__name__)

class PermissionFrameworkManager:
    """权限框架管理器"""
    
    _instance = None
    
    def __init__(self):
        self.engine: Optional[PermissionEngine] = None
        self.cache_manager: Optional[UnifiedPermissionCache] = None
        self.cache_invalidation_manager: Optional[CacheInvalidationManager] = None
        self.audit_logger: Optional[PermissionAuditLogger] = None
        self.performance_monitor: Optional[PermissionPerformanceMonitor] = None
        self._initialized = False
    
    @classmethod
    def get_instance(cls) -> 'PermissionFrameworkManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def initialize(
        self,
        rbac_middleware,
        enable_cache: bool = True,
        enable_audit: bool = True,
        enable_performance_monitoring: bool = True
    ):
        """初始化权限框架"""
        if self._initialized:
            logger.warning("Permission framework already initialized")
            return
        
        try:
            logger.info("Starting permission framework initialization...")
            logger.info(f"RBAC middleware received: {type(rbac_middleware)}")
            
            # 1. 初始化权限引擎
            logger.info("Creating permission engine instance...")
            self.engine = PermissionEngine.get_instance()
            logger.info(f"Permission engine instance: {self.engine}")
            
            logger.info("Initializing default strategies...")
            self.engine.initialize_default_strategies(rbac_middleware)
            
            # 检查策略是否正确注册
            strategy_stats = self.engine.get_strategy_stats()
            logger.info(f"Strategy initialization result: {strategy_stats}")
            
            # 2. 初始化缓存系统
            if enable_cache:
                db_manager = get_database_manager()
                await db_manager.initialize()
                redis_adapter = await db_manager.get_redis_adapter()
                self.cache_manager = UnifiedPermissionCache(redis_adapter)
                self.engine.set_cache_manager(self.cache_manager)
                
                # 初始化缓存失效管理器
                self.cache_invalidation_manager = CacheInvalidationManager(self.cache_manager)
                self.cache_invalidation_manager.setup_default_rules()
                
                logger.info("Permission cache system initialized")
            
            # 3. 初始化审计系统
            if enable_audit:
                self.audit_logger = PermissionAuditLogger(
                    enable_db_logging=True,
                    enable_file_logging=True
                )
                self.engine.set_audit_logger(self.audit_logger)
                await self.audit_logger.start()
                
                logger.info("Permission audit system initialized")
            
            # 4. 初始化性能监控
            if enable_performance_monitoring:
                self.performance_monitor = PermissionPerformanceMonitor()
                logger.info("Permission performance monitoring initialized")
            
            self._initialized = True
            logger.info("Permission framework initialization completed")
            
        except Exception as e:
            logger.error(f"Failed to initialize permission framework: {e}")
            raise
    
    async def shutdown(self):
        """关闭权限框架"""
        logger.info("Shutting down permission framework...")
        
        if self.audit_logger:
            await self.audit_logger.stop()
        
        self._initialized = False
        logger.info("Permission framework shutdown completed")
    
    def get_engine(self) -> Optional[PermissionEngine]:
        """获取权限引擎"""
        return self.engine
    
    def get_cache_manager(self) -> Optional[UnifiedPermissionCache]:
        """获取缓存管理器"""
        return self.cache_manager
    
    def get_audit_logger(self) -> Optional[PermissionAuditLogger]:
        """获取审计日志记录器"""
        return self.audit_logger
    
    def get_performance_monitor(self) -> Optional[PermissionPerformanceMonitor]:
        """获取性能监控器"""
        return self.performance_monitor
    
    async def invalidate_user_cache(self, user_id: str):
        """清除用户权限缓存"""
        if self.cache_invalidation_manager:
            await self.cache_invalidation_manager.handle_event("user_role_changed", {"user_id": user_id})
    
    async def invalidate_resource_cache(self, resource_uri: str):
        """清除资源权限缓存"""
        if self.cache_invalidation_manager:
            await self.cache_invalidation_manager.handle_event("resource_deleted", {"resource_uri": resource_uri})
    
    async def grant_permission_event(self, user_id: str, resource_uri: str):
        """权限授予事件"""
        if self.cache_invalidation_manager:
            await self.cache_invalidation_manager.handle_event("permission_granted", {
                "user_id": user_id,
                "resource_uri": resource_uri
            })
    
    async def revoke_permission_event(self, user_id: str, resource_uri: str):
        """权限撤销事件"""
        if self.cache_invalidation_manager:
            await self.cache_invalidation_manager.handle_event("permission_revoked", {
                "user_id": user_id,
                "resource_uri": resource_uri
            })
    
    def get_system_status(self) -> dict:
        """获取系统状态"""
        status = {
            "initialized": self._initialized,
            "engine_status": "active" if self.engine else "inactive",
            "cache_status": "active" if self.cache_manager else "inactive",
            "audit_status": "active" if self.audit_logger else "inactive",
            "performance_monitoring": "active" if self.performance_monitor else "inactive"
        }
        
        if self.engine:
            status["engine_stats"] = self.engine.get_strategy_stats()
        
        if self.cache_manager:
            status["cache_stats"] = self.cache_manager.get_cache_stats()
        
        if self.audit_logger:
            status["audit_stats"] = self.audit_logger.get_stats()
        
        if self.performance_monitor:
            status["performance_stats"] = self.performance_monitor.get_performance_report()
        
        return status

# 全局管理器实例
_framework_manager = None

def get_permission_framework() -> PermissionFrameworkManager:
    """获取权限框架管理器实例"""
    global _framework_manager
    if _framework_manager is None:
        _framework_manager = PermissionFrameworkManager.get_instance()
    return _framework_manager

async def initialize_permission_framework(rbac_middleware, **kwargs):
    """初始化权限框架"""
    framework = get_permission_framework()
    await framework.initialize(rbac_middleware, **kwargs)

async def shutdown_permission_framework():
    """关闭权限框架"""
    framework = get_permission_framework()
    await framework.shutdown()