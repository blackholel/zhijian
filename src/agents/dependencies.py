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
    from src.database.managers.knowledge_manager import KnowledgeBaseManager


class KnowledgeBaseManagerWrapper:
    """
    知识库管理器包装器
    
    为智能体系统提供兼容的知识库接口，当真实的知识库管理器不可用时作为降级方案。
    """
    
    def __init__(self):
        self._real_manager = None
        logger.debug("知识库管理器包装器创建完成")
    
    async def get_user_accessible_kbs(self, user_id: str):
        """
        获取用户可访问的知识库列表
        
        Returns:
            List: 知识库对象列表
        """
        try:
            if self._real_manager:
                # 调用真实管理器的方法
                logger.debug(f"调用知识库管理器获取用户 {user_id} 的知识库")
                result = await self._real_manager.get_user_knowledge_bases(user_id)
                logger.debug(f"知识库管理器返回 {len(result) if result else 0} 个知识库")
                return result
            else:
                # 返回空列表作为降级
                logger.warning("知识库管理器不可用，返回空知识库列表")
                return []
        except Exception as e:
            logger.error(f"获取用户可访问知识库失败: {e}")
            return []
    
    async def query_knowledge_base(self, kb_id: str, query_text: str, user_id: str):
        """
        查询知识库
        
        Returns:
            str: 查询结果
        """
        try:
            if self._real_manager:
                # 调用真实管理器的查询方法
                return await self._real_manager.query_knowledge_base(kb_id, query_text, user_id)
            else:
                # 返回默认回答
                logger.warning("知识库管理器不可用，返回默认回答")
                return f"知识库查询暂时不可用，查询内容：{query_text}"
        except Exception as e:
            logger.error(f"查询知识库失败: {e}")
            return f"查询失败：{str(e)}"
    
    async def check_kb_permission(self, user_id: str, kb_id: str, permission: str) -> bool:
        """
        检查知识库权限
        
        Returns:
            bool: 是否有权限
        """
        try:
            if self._real_manager:
                # 调用真实管理器的权限检查
                kb = await self._real_manager.get_knowledge_base(kb_id, user_id, include_files=False)
                return kb is not None
            else:
                # 默认拒绝访问（安全考虑）
                logger.warning("知识库管理器不可用，默认拒绝访问")
                return False
        except Exception as e:
            logger.error(f"检查知识库权限失败: {e}")
            return False
    
    async def health_check(self) -> dict:
        """健康检查"""
        return {
            "status": "wrapper",
            "real_manager": bool(self._real_manager),
            "available": False
        }
    
    def set_real_manager(self, manager):
        """设置真实的管理器实例"""
        self._real_manager = manager
        logger.debug("知识库管理器包装器已连接到真实管理器")

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
            self._agent_manager = None  # 智能体管理器
            
            # 初始化状态标记
            self._db_initialized = False
            self._permission_initialized = False
            self._kb_initialized = False
            self._agent_initialized = False
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
                        
                        # 权限引擎不需要额外初始化
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
        
        集成现有的知识库管理系统，支持LightRAG和统一数据库管理。
        """
        if self._kb_manager is None:
            async with self._lock:
                if self._kb_manager is None:
                    try:
                        # 确保数据库管理器先初始化
                        db_manager = await self.db_manager
                        
                        # 尝试使用真实的知识库管理器
                        from src.database.managers.knowledge_manager import KnowledgeBaseManager
                        connection_manager = db_manager.connection_manager
                        real_manager = KnowledgeBaseManager(connection_manager)
                        
                        # 创建包装器并设置真实管理器
                        self._kb_manager = KnowledgeBaseManagerWrapper()
                        self._kb_manager.set_real_manager(real_manager)
                        
                        self._kb_initialized = True
                        logger.debug("知识库管理器初始化完成（使用真实管理器）")
                    except Exception as e:
                        logger.error(f"初始化知识库管理器失败: {e}")
                        # 创建降级包装器
                        self._kb_manager = KnowledgeBaseManagerWrapper()
                        self._kb_initialized = True
                        logger.warning("使用知识库管理器降级包装器")
        
        return self._kb_manager
    
    @property
    async def agent_manager(self):
        """
        获取智能体管理器实例
        
        智能体管理器集成所有依赖，提供统一的智能体管理接口。
        """
        if self._agent_manager is None:
            async with self._lock:
                if self._agent_manager is None:
                    try:
                        # 确保所有依赖都已初始化
                        await self.db_manager
                        await self.permission_engine
                        await self.kb_manager
                        
                        # 导入并获取智能体管理器
                        from src.agents import agent_manager
                        self._agent_manager = agent_manager
                        
                        # 确保智能体管理器已初始化
                        if not self._agent_initialized:
                            await self._agent_manager.initialize()
                            self._agent_initialized = True
                            logger.debug("智能体管理器初始化完成")
                    except Exception as e:
                        logger.error(f"初始化智能体管理器失败: {e}")
                        raise
        
        return self._agent_manager
    
    async def ensure_initialized(self):
        """
        确保所有依赖已初始化（别名方法）
        
        这个方法是 initialize_all 的别名，提供更直观的API。
        """
        return await self.initialize_all()
    
    async def initialize_all(self) -> bool:
        """
        初始化所有依赖对象
        
        Returns:
            bool: 所有依赖是否成功初始化
        """
        try:
            logger.info("开始初始化智能体依赖系统...")
            
            # 按顺序初始化依赖（数据库 -> 权限 -> 知识库 -> 智能体管理器）
            await self.db_manager
            await self.permission_engine  
            await self.kb_manager
            await self.agent_manager
            
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
            "agent_manager": False,
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
            
            # 检查智能体管理器
            if self._agent_manager and self._agent_initialized:
                agent_health = await self._agent_manager.health_check()
                health_status["agent_manager"] = agent_health.get("initialized", False)
            
            # 整体健康状态
            health_status["overall"] = all([
                health_status["db_manager"],
                health_status["permission_engine"],
                health_status["kb_manager"],
                health_status["agent_manager"]
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
        self._agent_manager = None
        self._db_initialized = False
        self._permission_initialized = False
        self._kb_initialized = False
        self._agent_initialized = False
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