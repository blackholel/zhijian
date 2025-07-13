"""
智能体依赖注入管理器

实现延迟初始化模式，避免循环导入，集成统一数据库管理系统和权限框架。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
import asyncio
from src.utils import logger

if TYPE_CHECKING:
    from src.database.manager import UnifiedDatabaseManager
    from server.auth.permission_framework.engine import PermissionEngine
    from src.knowledge_base.manager import KnowledgeBaseManager

class AgentDependencies:
    """
    智能体依赖管理器 - 使用延迟初始化避免循环导入
    
    采用单例模式确保全局共享依赖实例，提供异步初始化和延迟加载。
    """
    
    _instance: Optional['AgentDependencies'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls) -> 'AgentDependencies':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            # 延迟初始化的依赖对象
            self._db_manager: Optional['UnifiedDatabaseManager'] = None
            self._permission_engine: Optional['PermissionEngine'] = None
            self._kb_manager: Optional['KnowledgeBaseManager'] = None
            
            # 初始化状态标记
            self._db_initialized = False
            self._permission_initialized = False
            self._kb_initialized = False
            self._initialized = True
            
            logger.debug("AgentDependencies 实例创建完成")
    
    @property
    async def db_manager(self) -> 'UnifiedDatabaseManager':
        """
        获取统一数据库管理器实例
        
        使用延迟导入避免循环依赖，确保线程安全的单例模式。
        """
        if self._db_manager is None:
            async with self._lock:
                if self._db_manager is None:
                    try:
                        from src.database.manager import get_database_manager
                        self._db_manager = get_database_manager()
                        
                        # 确保数据库管理器已初始化
                        if not self._db_initialized:
                            await self._db_manager.initialize()
                            self._db_initialized = True
                            logger.debug("数据库管理器初始化完成")
                    except Exception as e:
                        logger.error(f"初始化数据库管理器失败: {e}")
                        raise
        
        return self._db_manager
    
    @property  
    async def permission_engine(self) -> 'PermissionEngine':
        """
        获取权限引擎实例
        
        集成RBAC权限框架，支持智能体级权限控制。
        """
        if self._permission_engine is None:
            async with self._lock:
                if self._permission_engine is None:
                    try:
                        from server.auth.permission_framework.engine import PermissionEngine
                        self._permission_engine = PermissionEngine.get_instance()
                        
                        # 确保权限引擎已初始化
                        if not self._permission_initialized:
                            await self._permission_engine.initialize()
                            self._permission_initialized = True
                            logger.debug("权限引擎初始化完成")
                    except Exception as e:
                        logger.error(f"初始化权限引擎失败: {e}")
                        raise
        
        return self._permission_engine
    
    @property
    async def kb_manager(self) -> 'KnowledgeBaseManager':
        """
        获取知识库管理器实例
        
        集成LightRAG高性能知识库系统，支持动态知识库工具生成。
        """
        if self._kb_manager is None:
            async with self._lock:
                if self._kb_manager is None:
                    try:
                        # 确保数据库管理器先初始化
                        db_manager = await self.db_manager
                        
                        from src.knowledge_base.manager import KnowledgeBaseManager
                        self._kb_manager = KnowledgeBaseManager(db_manager)
                        
                        # 确保知识库管理器已初始化
                        if not self._kb_initialized:
                            await self._kb_manager.initialize()
                            self._kb_initialized = True
                            logger.debug("知识库管理器初始化完成")
                    except Exception as e:
                        logger.error(f"初始化知识库管理器失败: {e}")
                        raise
        
        return self._kb_manager
    
    async def initialize_all(self) -> bool:
        """
        初始化所有依赖对象
        
        Returns:
            bool: 所有依赖是否成功初始化
        """
        try:
            logger.info("开始初始化智能体依赖系统...")
            
            # 按顺序初始化依赖（数据库 -> 权限 -> 知识库）
            await self.db_manager
            await self.permission_engine  
            await self.kb_manager
            
            logger.info("智能体依赖系统初始化完成")
            return True
        except Exception as e:
            logger.error(f"智能体依赖系统初始化失败: {e}")
            return False
    
    async def health_check(self) -> dict:
        """
        健康检查
        
        Returns:
            dict: 各组件的健康状态
        """
        health_status = {
            "db_manager": False,
            "permission_engine": False, 
            "kb_manager": False,
            "overall": False
        }
        
        try:
            # 检查数据库管理器
            if self._db_manager and self._db_initialized:
                health_status["db_manager"] = await self._db_manager.health_check()
            
            # 检查权限引擎
            if self._permission_engine and self._permission_initialized:
                health_status["permission_engine"] = await self._permission_engine.health_check()
            
            # 检查知识库管理器
            if self._kb_manager and self._kb_initialized:
                health_status["kb_manager"] = await self._kb_manager.health_check()
            
            # 整体健康状态
            health_status["overall"] = all([
                health_status["db_manager"],
                health_status["permission_engine"],
                health_status["kb_manager"]
            ])
            
        except Exception as e:
            logger.error(f"依赖健康检查失败: {e}")
        
        return health_status
    
    def reset(self):
        """
        重置所有依赖（主要用于测试）
        """
        self._db_manager = None
        self._permission_engine = None
        self._kb_manager = None
        self._db_initialized = False
        self._permission_initialized = False
        self._kb_initialized = False
        logger.debug("AgentDependencies 已重置")


# 全局单例实例
_agent_dependencies: Optional[AgentDependencies] = None

def get_agent_dependencies() -> AgentDependencies:
    """
    获取全局智能体依赖管理器实例
    
    Returns:
        AgentDependencies: 单例依赖管理器
    """
    global _agent_dependencies
    if _agent_dependencies is None:
        _agent_dependencies = AgentDependencies()
    return _agent_dependencies