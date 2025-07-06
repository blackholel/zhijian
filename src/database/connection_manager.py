"""
统一数据库连接管理器
"""

import asyncio
import logging
from typing import Dict, Optional, Type, List, Any
from contextlib import asynccontextmanager

from .base import DatabaseAdapter, DatabaseType, ConnectionStatus, DatabaseError
from .config_manager import DatabaseConfigManager

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    """数据库连接管理器"""
    
    def __init__(self, config_manager: DatabaseConfigManager = None):
        """
        初始化连接管理器
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
        """
        self.config_manager = config_manager or DatabaseConfigManager()
        self.adapters: Dict[str, DatabaseAdapter] = {}
        self.adapter_classes: Dict[DatabaseType, Type[DatabaseAdapter]] = {}
        self._health_check_task = None
        self._health_check_enabled = False
        
        # 延迟导入适配器类，避免循环导入
        self._register_adapter_classes()
        
        logger.info("Database connection manager initialized")
    
    def _register_adapter_classes(self):
        """注册适配器类"""
        try:
            from .adapters.postgresql import PostgreSQLAdapter
            from .adapters.neo4j import Neo4jAdapter
            from .adapters.redis import RedisAdapter
            from .adapters.milvus import MilvusAdapter
            from .adapters.minio import MinIOAdapter
            
            self.adapter_classes = {
                DatabaseType.POSTGRESQL: PostgreSQLAdapter,
                DatabaseType.NEO4J: Neo4jAdapter,
                DatabaseType.REDIS: RedisAdapter,
                DatabaseType.MILVUS: MilvusAdapter,
                DatabaseType.MINIO: MinIOAdapter,
            }
            logger.debug("Database adapter classes registered")
        except ImportError as e:
            logger.warning(f"Some adapter classes not available: {e}")
    
    async def initialize_database(self, db_name: str, db_type: DatabaseType, 
                                auto_connect: bool = True) -> DatabaseAdapter:
        """
        初始化数据库连接
        
        Args:
            db_name: 数据库名称（配置中的键名）
            db_type: 数据库类型
            auto_connect: 是否自动连接
            
        Returns:
            DatabaseAdapter: 数据库适配器实例
            
        Raises:
            DatabaseError: 初始化失败时抛出
        """
        if db_name in self.adapters:
            logger.debug(f"Database '{db_name}' already initialized")
            return self.adapters[db_name]
        
        try:
            # 验证配置
            if not self.config_manager.validate_database_config(db_name):
                raise DatabaseError(f"Invalid configuration for database '{db_name}'")
            
            # 获取配置
            config = self.config_manager.get_database_config(db_name)
            
            # 添加重试配置
            retry_config = self.config_manager.get_retry_config()
            config.update(retry_config)
            
            # 获取适配器类
            if db_type not in self.adapter_classes:
                raise DatabaseError(f"Unsupported database type: {db_type}")
            
            adapter_class = self.adapter_classes[db_type]
            adapter = adapter_class(config, db_name)
            
            # 建立连接
            if auto_connect:
                if await adapter.connect():
                    self.adapters[db_name] = adapter
                    logger.info(f"Database '{db_name}' ({db_type.value}) initialized and connected")
                else:
                    raise DatabaseError(f"Failed to connect to database '{db_name}'")
            else:
                self.adapters[db_name] = adapter
                logger.info(f"Database '{db_name}' ({db_type.value}) initialized (not connected)")
            
            return adapter
            
        except Exception as e:
            logger.error(f"Failed to initialize database '{db_name}': {e}")
            raise DatabaseError(f"Failed to initialize database '{db_name}': {e}")
    
    async def get_adapter(self, db_name: str) -> Optional[DatabaseAdapter]:
        """
        获取数据库适配器
        
        Args:
            db_name: 数据库名称
            
        Returns:
            Optional[DatabaseAdapter]: 数据库适配器实例，不存在时返回None
        """
        return self.adapters.get(db_name)
    
    async def ensure_connection(self, db_name: str) -> DatabaseAdapter:
        """
        确保数据库连接可用
        
        Args:
            db_name: 数据库名称
            
        Returns:
            DatabaseAdapter: 数据库适配器实例
            
        Raises:
            DatabaseError: 连接不可用时抛出
        """
        adapter = await self.get_adapter(db_name)
        if not adapter:
            raise DatabaseError(f"Database '{db_name}' not initialized")
        
        await adapter.ensure_connected()
        return adapter
    
    @asynccontextmanager
    async def get_session(self, db_name: str):
        """
        获取数据库会话的上下文管理器
        
        Args:
            db_name: 数据库名称
            
        Yields:
            数据库会话对象
        """
        adapter = await self.ensure_connection(db_name)
        async with adapter.get_session() as session:
            yield session
    
    async def close_database(self, db_name: str) -> bool:
        """
        关闭指定数据库连接
        
        Args:
            db_name: 数据库名称
            
        Returns:
            bool: 关闭成功返回True
        """
        adapter = self.adapters.get(db_name)
        if adapter:
            try:
                result = await adapter.disconnect()
                if result:
                    del self.adapters[db_name]
                    logger.info(f"Database '{db_name}' disconnected and removed")
                return result
            except Exception as e:
                logger.error(f"Error disconnecting database '{db_name}': {e}")
                return False
        return True
    
    async def close_all(self):
        """关闭所有数据库连接"""
        if self._health_check_task:
            await self.stop_health_monitoring()
        
        disconnect_tasks = []
        for db_name, adapter in list(self.adapters.items()):
            disconnect_tasks.append(self._safe_disconnect(db_name, adapter))
        
        if disconnect_tasks:
            results = await asyncio.gather(*disconnect_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    db_name = list(self.adapters.keys())[i] if i < len(self.adapters) else "unknown"
                    logger.error(f"Error disconnecting database '{db_name}': {result}")
        
        self.adapters.clear()
        logger.info("All database connections closed")
    
    async def _safe_disconnect(self, db_name: str, adapter: DatabaseAdapter) -> bool:
        """安全断开连接"""
        try:
            result = await adapter.disconnect()
            logger.info(f"Database '{db_name}' disconnected")
            return result
        except Exception as e:
            logger.error(f"Error disconnecting database '{db_name}': {e}")
            return False
    
    async def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """
        检查所有数据库健康状态
        
        Returns:
            Dict[str, Dict[str, Any]]: 健康检查结果
        """
        results = {}
        
        # 并发检查所有数据库
        check_tasks = []
        db_names = []
        
        for db_name, adapter in self.adapters.items():
            check_tasks.append(self._safe_health_check(adapter))
            db_names.append(db_name)
        
        if check_tasks:
            health_results = await asyncio.gather(*check_tasks, return_exceptions=True)
            
            for i, result in enumerate(health_results):
                db_name = db_names[i]
                if isinstance(result, Exception):
                    results[db_name] = {
                        'status': 'error',
                        'error': str(result),
                        'database_name': db_name
                    }
                else:
                    results[db_name] = result
        
        return results
    
    async def _safe_health_check(self, adapter: DatabaseAdapter) -> Dict[str, Any]:
        """安全执行健康检查"""
        try:
            return await adapter.health_check()
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'database_name': adapter.db_name
            }
    
    async def start_health_monitoring(self, interval: int = None):
        """
        启动健康监控
        
        Args:
            interval: 检查间隔（秒），默认从配置获取
        """
        if self._health_check_enabled:
            logger.warning("Health monitoring is already running")
            return
        
        health_config = self.config_manager.get_health_check_config()
        if not health_config.get('enabled', True):
            logger.info("Health monitoring is disabled in config")
            return
        
        check_interval = interval or health_config.get('interval', 60)
        self._health_check_enabled = True
        
        async def monitor_loop():
            while self._health_check_enabled:
                try:
                    results = await self.health_check_all()
                    
                    # 记录不健康的数据库
                    unhealthy_dbs = [
                        db_name for db_name, result in results.items()
                        if result.get('status') != 'healthy'
                    ]
                    
                    if unhealthy_dbs:
                        logger.warning(f"Unhealthy databases detected: {unhealthy_dbs}")
                    else:
                        logger.debug("All databases are healthy")
                    
                    await asyncio.sleep(check_interval)
                    
                except Exception as e:
                    logger.error(f"Health monitoring error: {e}")
                    await asyncio.sleep(5)  # 错误时短暂等待
        
        self._health_check_task = asyncio.create_task(monitor_loop())
        logger.info(f"Health monitoring started with {check_interval}s interval")
    
    async def stop_health_monitoring(self):
        """停止健康监控"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_enabled = False
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            logger.info("Health monitoring stopped")
    
    def get_connection_summary(self) -> Dict[str, Any]:
        """
        获取连接状态摘要
        
        Returns:
            Dict[str, Any]: 连接状态摘要
        """
        summary = {
            'total_adapters': len(self.adapters),
            'connected_count': 0,
            'disconnected_count': 0,
            'error_count': 0,
            'adapters': {}
        }
        
        for db_name, adapter in self.adapters.items():
            status = adapter.status.value
            metrics = adapter.get_metrics()
            
            summary['adapters'][db_name] = {
                'status': status,
                'adapter_type': adapter.__class__.__name__,
                'retry_count': metrics.get('retry_count', 0)
            }
            
            if adapter.status == ConnectionStatus.CONNECTED:
                summary['connected_count'] += 1
            elif adapter.status == ConnectionStatus.ERROR:
                summary['error_count'] += 1
            else:
                summary['disconnected_count'] += 1
        
        summary['health_monitoring'] = self._health_check_enabled
        
        return summary
    
    async def reconnect_all(self) -> Dict[str, bool]:
        """
        重连所有数据库
        
        Returns:
            Dict[str, bool]: 重连结果
        """
        results = {}
        
        reconnect_tasks = []
        db_names = []
        
        for db_name, adapter in self.adapters.items():
            reconnect_tasks.append(adapter.retry_connection())
            db_names.append(db_name)
        
        if reconnect_tasks:
            reconnect_results = await asyncio.gather(*reconnect_tasks, return_exceptions=True)
            
            for i, result in enumerate(reconnect_results):
                db_name = db_names[i]
                if isinstance(result, Exception):
                    results[db_name] = False
                    logger.error(f"Reconnection failed for '{db_name}': {result}")
                else:
                    results[db_name] = result
                    if result:
                        logger.info(f"Reconnection successful for '{db_name}'")
                    else:
                        logger.warning(f"Reconnection failed for '{db_name}'")
        
        return results
    
    def list_available_databases(self) -> List[str]:
        """
        列出配置中可用的数据库
        
        Returns:
            List[str]: 可用的数据库名称列表
        """
        return self.config_manager.get_all_database_names()
    
    async def initialize_common_databases(self):
        """初始化常用数据库"""
        common_dbs = [
            ('server_db', DatabaseType.POSTGRESQL),
            ('lightrag_db', DatabaseType.POSTGRESQL),
            ('neo4j', DatabaseType.NEO4J),
            ('redis', DatabaseType.REDIS),
            ('milvus', DatabaseType.MILVUS),
            ('minio', DatabaseType.MINIO)
        ]
        
        initialization_tasks = []
        for db_name, db_type in common_dbs:
            if self.config_manager.validate_database_config(db_name):
                task = self.initialize_database(db_name, db_type, auto_connect=False)
                initialization_tasks.append((db_name, task))
            else:
                logger.warning(f"Skipping '{db_name}' due to invalid configuration")
        
        # 并发初始化
        for db_name, task in initialization_tasks:
            try:
                await task
                logger.info(f"Initialized {db_name}")
            except Exception as e:
                logger.error(f"Failed to initialize {db_name}: {e}")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize_common_databases()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close_all()