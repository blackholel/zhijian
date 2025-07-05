"""
权限决策引擎
统一的权限检查和决策中心
"""

from typing import List, Optional
from datetime import datetime
import logging

from .core import PermissionContext, PermissionResult, Permission
from .resources import Resource
from .strategies import PermissionStrategy

logger = logging.getLogger(__name__)

class PermissionEngine:
    """统一权限决策引擎"""
    
    _instance = None
    
    def __init__(self):
        self.strategies: List[PermissionStrategy] = []
        self.cache_manager: Optional['UnifiedPermissionCache'] = None
        self.audit_logger: Optional['PermissionAuditLogger'] = None
        self._initialized = False
    
    @classmethod
    def get_instance(cls) -> 'PermissionEngine':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_strategy(self, strategy: PermissionStrategy):
        """注册权限策略"""
        self.strategies.append(strategy)
        # 按优先级排序
        self.strategies.sort(key=lambda s: s.get_priority())
        logger.info(f"Registered strategy: {strategy.get_strategy_name()}")
    
    def set_cache_manager(self, cache_manager: 'UnifiedPermissionCache'):
        """设置缓存管理器"""
        self.cache_manager = cache_manager
        logger.info("Cache manager set for permission engine")
    
    def set_audit_logger(self, audit_logger: 'PermissionAuditLogger'):
        """设置审计日志记录器"""
        self.audit_logger = audit_logger
        logger.info("Audit logger set for permission engine")
    
    def initialize_default_strategies(self, rbac_middleware):
        """初始化默认策略"""
        if self._initialized:
            logger.info("Permission engine already initialized, skipping strategy registration")
            return
        
        logger.info("Starting permission engine strategy initialization...")
        
        try:
            from .strategies import (
                SuperAdminStrategy, OwnershipStrategy, PublicResourceStrategy,
                SystemPermissionStrategy, ResourcePermissionStrategy, 
                InheritanceStrategy, DenyAllStrategy
            )
            logger.info("Successfully imported all strategy classes")
            
            # 注册默认策略
            logger.info("Registering SuperAdminStrategy...")
            self.register_strategy(SuperAdminStrategy(rbac_middleware))
            
            logger.info("Registering OwnershipStrategy...")
            self.register_strategy(OwnershipStrategy())
            
            logger.info("Registering PublicResourceStrategy...")
            self.register_strategy(PublicResourceStrategy())
            
            logger.info("Registering SystemPermissionStrategy...")
            self.register_strategy(SystemPermissionStrategy(rbac_middleware))
            
            logger.info("Registering ResourcePermissionStrategy...")
            self.register_strategy(ResourcePermissionStrategy())
            
            logger.info("Registering InheritanceStrategy...")
            self.register_strategy(InheritanceStrategy())
            
            logger.info("Registering DenyAllStrategy...")
            self.register_strategy(DenyAllStrategy())
            
            self._initialized = True
            logger.info(f"Default permission strategies initialized successfully. Total strategies: {len(self.strategies)}")
            
        except Exception as e:
            logger.error(f"Error initializing permission strategies: {e}")
            import traceback
            logger.error(f"Strategy initialization traceback: {traceback.format_exc()}")
            raise
    
    async def check_permission(
        self, 
        context: PermissionContext, 
        skip_inheritance: bool = False
    ) -> PermissionResult:
        """检查权限"""
        
        # 1. 尝试从缓存获取结果
        if self.cache_manager:
            cached_result = await self.cache_manager.get_permission(context)
            if cached_result:
                logger.debug(f"Permission check cache hit for {context.user_id}:{context.resource.uri if context.resource else 'system'}:{context.permission.value}")
                return cached_result
        
        # 2. 依次执行权限策略
        for strategy in self.strategies:
            if not strategy.is_applicable(context):
                continue
                
            # 跳过继承策略（防止无限递归）
            if skip_inheritance and strategy.get_strategy_name() == "InheritanceStrategy":
                continue
            
            try:
                result = await strategy.check_permission(context)
                
                # 记录策略执行结果
                logger.debug(f"Strategy {strategy.get_strategy_name()} result: {result.allowed} - {result.reason}")
                
                if result.allowed:
                    # 记录审计日志
                    if self.audit_logger:
                        await self.audit_logger.log_permission_check(context, result)
                    
                    # 缓存结果
                    if self.cache_manager:
                        await self.cache_manager.cache_permission(context, result)
                    
                    return result
                    
            except Exception as e:
                logger.error(f"Error in permission strategy {strategy.get_strategy_name()}: {e}")
                continue
        
        # 3. 所有策略都拒绝，返回拒绝结果
        result = PermissionResult(False, "All strategies denied access", "PermissionEngine")
        
        # 记录审计日志
        if self.audit_logger:
            await self.audit_logger.log_permission_check(context, result)
        
        logger.warning(f"Permission denied for {context.user_id}:{context.resource.uri if context.resource else 'system'}:{context.permission.value}")
        return result
    
    async def check_permission_simple(
        self, 
        user_id: str, 
        resource: Optional[Resource], 
        permission: Permission,
        metadata: dict = None
    ) -> bool:
        """简化的权限检查接口"""
        context = PermissionContext(
            user_id=user_id,
            resource=resource,
            permission=permission,
            request_metadata=metadata or {},
            timestamp=datetime.now()
        )
        result = await self.check_permission(context)
        return result.allowed
    
    async def batch_check_permissions(
        self,
        user_id: str,
        permission_requests: List[tuple]  # [(resource, permission), ...]
    ) -> List[bool]:
        """批量权限检查"""
        results = []
        for resource, permission in permission_requests:
            allowed = await self.check_permission_simple(user_id, resource, permission)
            results.append(allowed)
        return results
    
    def get_strategy_stats(self) -> dict:
        """获取策略统计信息"""
        return {
            "total_strategies": len(self.strategies),
            "strategy_names": [s.get_strategy_name() for s in self.strategies],
            "cache_enabled": self.cache_manager is not None,
            "audit_enabled": self.audit_logger is not None
        }