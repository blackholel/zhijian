"""
统一数据库管理器

替换原有的分散数据库管理，提供统一的数据库访问接口
"""

import logging
from typing import Dict, Any, Optional

from .config_manager import DatabaseConfigManager
from .connection_manager import DatabaseConnectionManager
from .base import DatabaseType

logger = logging.getLogger(__name__)


class UnifiedDatabaseManager:
    """统一数据库管理器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化统一数据库管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_manager = DatabaseConfigManager(config_path)
        self.connection_manager = DatabaseConnectionManager(self.config_manager)
        
        # 仓储实例缓存
        self._repositories = {}
        
        # 初始化状态
        self._initialized = False
        
        logger.info("Unified database manager created")
    
    async def initialize(self):
        """初始化数据库连接"""
        if self._initialized:
            return
        
        try:
            # 初始化常用数据库连接
            databases_to_init = [
                ('server_db', DatabaseType.POSTGRESQL),
                ('lightrag_db', DatabaseType.POSTGRESQL),
                ('neo4j', DatabaseType.NEO4J),
                ('redis', DatabaseType.REDIS),
                ('milvus', DatabaseType.MILVUS),
                ('minio', DatabaseType.MINIO)
            ]
            
            for db_name, db_type in databases_to_init:
                try:
                    if self.config_manager.validate_database_config(db_name):
                        adapter = await self.connection_manager.initialize_database(
                            db_name, db_type, auto_connect=True
                        )
                        logger.info(f"Database {db_name} initialized successfully")
                    else:
                        logger.warning(f"Database {db_name} configuration invalid, skipping")
                except Exception as e:
                    logger.error(f"Failed to initialize database {db_name}: {e}")
            
            # 启动健康监控
            await self.connection_manager.start_health_monitoring()
            
            self._initialized = True
            logger.info("Unified database manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize unified database manager: {e}")
            raise
    
    async def shutdown(self):
        """关闭数据库管理器"""
        try:
            await self.connection_manager.close_all()
            self._repositories.clear()
            self._initialized = False
            logger.info("Unified database manager shutdown completed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    # 适配器访问方法
    
    async def get_postgresql_adapter(self, db_name: str = 'server_db'):
        """获取PostgreSQL适配器"""
        return await self.connection_manager.get_adapter(db_name)
    
    async def get_neo4j_adapter(self, db_name: str = 'neo4j'):
        """获取Neo4j适配器"""
        return await self.connection_manager.get_adapter(db_name)
    
    async def get_redis_adapter(self, db_name: str = 'redis'):
        """获取Redis适配器"""
        return await self.connection_manager.get_adapter(db_name)
    
    async def get_milvus_adapter(self, db_name: str = 'milvus'):
        """获取Milvus适配器"""
        return await self.connection_manager.get_adapter(db_name)
    
    async def get_minio_adapter(self, db_name: str = 'minio'):
        """获取MinIO适配器"""
        return await self.connection_manager.get_adapter(db_name)
    
    # 仓储访问方法（延迟导入避免循环依赖）
    
    def get_user_repository(self):
        """获取用户仓储"""
        if 'user' not in self._repositories:
            from .repositories.user_repository import UserRepository
            self._repositories['user'] = UserRepository(self.connection_manager)
        return self._repositories['user']
    
    def get_knowledge_repository(self):
        """获取知识库仓储"""
        if 'knowledge' not in self._repositories:
            from .repositories.knowledge_repository import KnowledgeRepository
            self._repositories['knowledge'] = KnowledgeRepository(self.connection_manager)
        return self._repositories['knowledge']
    
    def get_graph_repository(self):
        """获取图数据仓储"""
        if 'graph' not in self._repositories:
            from .repositories.graph_repository import GraphRepository
            self._repositories['graph'] = GraphRepository(self.connection_manager)
        return self._repositories['graph']
    
    def get_file_repository(self):
        """获取文件仓储"""
        if 'file' not in self._repositories:
            from .repositories.file_repository import FileRepository
            self._repositories['file'] = FileRepository(self.connection_manager)
        return self._repositories['file']
    
    # 兼容性方法（用于替换原有的数据库管理器）
    
    async def get_session(self, db_name: str = 'server_db'):
        """获取数据库会话（兼容原有API）"""
        return await self.connection_manager.get_session(db_name)
    
    def get_session_sync(self, db_name: str = 'server_db'):
        """获取同步数据库会话（兼容原有API）"""
        import asyncio
        adapter = asyncio.run(self.connection_manager.get_adapter(db_name))
        if adapter and hasattr(adapter, 'get_session'):
            return adapter.get_session()
        return None
    
    async def health_check(self) -> Dict[str, Any]:
        """统一健康检查"""
        if not self._initialized:
            return {'status': 'not_initialized'}
        
        try:
            db_health = await self.connection_manager.health_check_all()
            connection_summary = self.connection_manager.get_connection_summary()
            
            # 仓储健康检查
            repo_health = {}
            for repo_name, repo in self._repositories.items():
                try:
                    repo_health[repo_name] = await repo.health_check()
                except Exception as e:
                    repo_health[repo_name] = {
                        'status': 'error',
                        'error': str(e)
                    }
            
            return {
                'status': 'healthy',
                'initialized': self._initialized,
                'databases': db_health,
                'connections': connection_summary,
                'repositories': repo_health,
                'config_environment': self.config_manager.environment
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'initialized': self._initialized
            }
    
    # 配置相关方法
    
    def get_database_config(self, db_name: str) -> Dict[str, Any]:
        """获取数据库配置"""
        return self.config_manager.get_database_config(db_name)
    
    def get_connection_string(self, db_name: str) -> str:
        """获取数据库连接字符串"""
        return self.config_manager.get_postgresql_connection_string(db_name)
    
    def validate_database_config(self, db_name: str) -> bool:
        """验证数据库配置"""
        return self.config_manager.validate_database_config(db_name)
    
    # 向后兼容的属性和方法
    
    @property
    def engine(self):
        """兼容性属性：获取PostgreSQL引擎"""
        import asyncio
        try:
            adapter = asyncio.run(self.get_postgresql_adapter())
            return adapter.engine if adapter else None
        except:
            return None
    
    @property
    def Session(self):
        """兼容性属性：获取PostgreSQL会话工厂"""
        import asyncio
        try:
            adapter = asyncio.run(self.get_postgresql_adapter())
            return adapter.SessionLocal if adapter else None
        except:
            return None
    
    def create_tables(self):
        """兼容性方法：创建数据库表"""
        import asyncio
        try:
            adapter = asyncio.run(self.get_postgresql_adapter())
            if adapter and hasattr(adapter, 'create_tables_if_not_exists'):
                # 需要传入metadata，这里需要从实际模型中获取
                from server.models import Base
                asyncio.run(adapter.create_tables_if_not_exists(Base.metadata))
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.shutdown()


# 全局实例
_global_db_manager: Optional[UnifiedDatabaseManager] = None


def get_database_manager() -> UnifiedDatabaseManager:
    """获取全局数据库管理器实例"""
    global _global_db_manager
    if _global_db_manager is None:
        _global_db_manager = UnifiedDatabaseManager()
    return _global_db_manager


async def initialize_global_database_manager():
    """初始化全局数据库管理器"""
    db_manager = get_database_manager()
    await db_manager.initialize()
    return db_manager


async def shutdown_global_database_manager():
    """关闭全局数据库管理器"""
    global _global_db_manager
    if _global_db_manager:
        await _global_db_manager.shutdown()
        _global_db_manager = None


# 向后兼容的函数

def get_db_manager():
    """向后兼容：获取数据库管理器"""
    return get_database_manager()


def get_db_session():
    """向后兼容：获取数据库会话"""
    db_manager = get_database_manager()
    return db_manager.get_session_sync()


# 依赖注入函数（用于FastAPI）

async def get_database_manager_dependency() -> UnifiedDatabaseManager:
    """FastAPI依赖注入：获取数据库管理器"""
    db_manager = get_database_manager()
    if not db_manager._initialized:
        await db_manager.initialize()
    return db_manager


async def get_user_repository_dependency():
    """FastAPI依赖注入：获取用户仓储"""
    db_manager = await get_database_manager_dependency()
    return db_manager.get_user_repository()


async def get_knowledge_repository_dependency():
    """FastAPI依赖注入：获取知识库仓储"""
    db_manager = await get_database_manager_dependency()
    return db_manager.get_knowledge_repository()


async def get_graph_repository_dependency():
    """FastAPI依赖注入：获取图数据仓储"""
    db_manager = await get_database_manager_dependency()
    return db_manager.get_graph_repository()


async def get_file_repository_dependency():
    """FastAPI依赖注入：获取文件仓储"""
    db_manager = await get_database_manager_dependency()
    return db_manager.get_file_repository()


# 兼容性便捷方法

async def check_first_run() -> bool:
    """检查是否是首次运行（兼容接口）"""
    db_manager = get_database_manager()
    await db_manager.initialize()
    user_repo = db_manager.get_user_repository()
    return await user_repo.is_first_run()

def get_db_session():
    """获取同步数据库会话（兼容接口）"""
    db_manager = get_database_manager()
    return db_manager.get_session_sync()

async def get_db_session_async():
    """获取异步数据库会话（兼容接口）"""
    db_manager = get_database_manager()
    await db_manager.initialize()
    return await db_manager.get_session()