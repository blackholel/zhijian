"""
PostgreSQL数据库适配器
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import quote_plus

from sqlalchemy import create_engine, event, text, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.engine import Engine

from ..base import SQLDatabaseAdapter, ConnectionStatus, ConnectionError

logger = logging.getLogger(__name__)


class PostgreSQLAdapter(SQLDatabaseAdapter):
    """PostgreSQL数据库适配器"""
    
    def __init__(self, config: Dict[str, Any], db_name: str = None):
        """
        初始化PostgreSQL适配器
        
        Args:
            config: 数据库配置
            db_name: 数据库名称
        """
        super().__init__(config, db_name)
        
        self.engine = None
        self.SessionLocal = None
        self.connection_string = self._build_connection_string()
        
        # 连接池配置
        self.pool_size = config.get('pool_size', 10)
        self.max_overflow = config.get('max_overflow', 20)
        self.pool_timeout = config.get('pool_timeout', 30)
        self.pool_recycle = config.get('pool_recycle', 3600)
        self.echo = config.get('echo', False)
        self.connect_timeout = config.get('connect_timeout', 30)
        
        logger.debug(f"PostgreSQL adapter initialized for {self.db_name}")
    
    def _build_connection_string(self) -> str:
        """构建数据库连接字符串"""
        try:
            # URL编码用户名和密码以处理特殊字符
            username = quote_plus(str(self.config['username']))
            password = quote_plus(str(self.config['password']))
            host = self.config['host']
            port = self.config['port']
            database = self.config['database']
            
            return f"postgresql://{username}:{password}@{host}:{port}/{database}"
        except KeyError as e:
            raise ConnectionError(f"Missing required config parameter: {e}")
    
    async def connect(self) -> bool:
        """建立数据库连接"""
        if self.status == ConnectionStatus.CONNECTED:
            return True
        
        self.status = ConnectionStatus.CONNECTING
        
        try:
            # 创建引擎
            engine_kwargs = {
                'pool_size': self.pool_size,
                'max_overflow': self.max_overflow,
                'pool_timeout': self.pool_timeout,
                'pool_pre_ping': True,
                'pool_recycle': self.pool_recycle,
                'echo': self.echo,
                'connect_args': {
                    'connect_timeout': self.connect_timeout,
                    'options': '-c timezone=UTC'
                }
            }
            
            self.engine = create_engine(self.connection_string, **engine_kwargs)
            
            # 添加连接事件监听器
            @event.listens_for(self.engine, "connect")
            def set_postgresql_search_path(dbapi_connection, connection_record):
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public")
            
            # 创建会话工厂
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # 测试连接
            await self._test_connection()
            
            self._client = self.engine
            self.status = ConnectionStatus.CONNECTED
            
            logger.info(f"PostgreSQL connection established for {self.db_name}")
            return True
            
        except Exception as e:
            self.status = ConnectionStatus.ERROR
            logger.error(f"Failed to connect to PostgreSQL {self.db_name}: {e}")
            return False
    
    async def _test_connection(self):
        """测试数据库连接"""
        def _sync_test():
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        
        # 在线程池中执行同步操作
        await asyncio.get_event_loop().run_in_executor(None, _sync_test)
    
    async def disconnect(self) -> bool:
        """断开数据库连接"""
        try:
            if self.engine:
                self.engine.dispose()
                self.engine = None
                self._client = None
                self.SessionLocal = None
            
            self.status = ConnectionStatus.DISCONNECTED
            logger.info(f"PostgreSQL connection closed for {self.db_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from PostgreSQL {self.db_name}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.is_connected:
                return {
                    'status': 'disconnected',
                    'database_name': self.db_name,
                    'timestamp': datetime.now().isoformat()
                }
            
            def _sync_health_check():
                with self.engine.connect() as conn:
                    # 基本连接测试
                    conn.execute(text("SELECT 1"))
                    
                    # 获取数据库信息
                    version_result = conn.execute(text("SELECT version()"))
                    version = version_result.scalar()
                    
                    # 获取连接统计
                    stats_result = conn.execute(text("""
                        SELECT 
                            COUNT(*) as total_connections,
                            COUNT(*) FILTER (WHERE state = 'active') as active_connections
                        FROM pg_stat_activity 
                        WHERE datname = current_database()
                    """))
                    stats = stats_result.fetchone()
                    
                    # 获取数据库大小
                    size_result = conn.execute(text("SELECT pg_database_size(current_database())"))
                    db_size = size_result.scalar()
                    
                    return {
                        'status': 'healthy',
                        'database_name': self.db_name,
                        'version': version,
                        'total_connections': stats[0] if stats else 0,
                        'active_connections': stats[1] if stats else 0,
                        'database_size_bytes': db_size,
                        'pool_status': {
                            'pool_size': self.engine.pool.size(),
                            'checked_in': self.engine.pool.checkedin(),
                            'checked_out': self.engine.pool.checkedout(),
                            'overflow': self.engine.pool.overflow(),
                            'invalid': self.engine.pool.invalid()
                        },
                        'timestamp': datetime.now().isoformat()
                    }
            
            # 在线程池中执行同步操作
            result = await asyncio.get_event_loop().run_in_executor(None, _sync_health_check)
            return result
            
        except Exception as e:
            return {
                'status': 'error',
                'database_name': self.db_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            'database_name': self.db_name,
            'type': 'postgresql',
            'host': self.config.get('host'),
            'port': self.config.get('port'),
            'database': self.config.get('database'),
            'username': self.config.get('username'),
            'pool_size': self.pool_size,
            'max_overflow': self.max_overflow,
            'status': self.status.value,
            'connection_string_safe': self.connection_string.split('@')[1] if '@' in self.connection_string else 'unknown'
        }
    
    def get_session(self) -> Session:
        """
        获取数据库会话（同步版本）
        
        Returns:
            Session: SQLAlchemy会话对象
        """
        if not self.SessionLocal:
            raise ConnectionError(f"PostgreSQL not connected for {self.db_name}")
        return self.SessionLocal()
    
    @asynccontextmanager
    async def get_session_context(self):
        """获取数据库会话的异步上下文管理器"""
        await self.ensure_connected()
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error for {self.db_name}: {e}")
            raise
        finally:
            session.close()
    
    async def execute_query(self, query: str, params: Dict[str, Any] = None) -> Any:
        """
        执行SQL查询
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            查询结果
        """
        await self.ensure_connected()
        
        def _sync_execute():
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                if result.returns_rows:
                    return result.fetchall()
                return result.rowcount
        
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_execute)
        except Exception as e:
            logger.error(f"Query execution failed for {self.db_name}: {e}")
            raise
    
    async def execute_transaction(self, operations: List[Dict[str, Any]]) -> bool:
        """
        执行事务
        
        Args:
            operations: 操作列表，每个操作包含 'query' 和 'params'
            
        Returns:
            bool: 事务执行成功返回True
        """
        await self.ensure_connected()
        
        def _sync_transaction():
            with self.engine.begin() as conn:
                for operation in operations:
                    query = operation.get('query')
                    params = operation.get('params', {})
                    conn.execute(text(query), params)
            return True
        
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_transaction)
        except Exception as e:
            logger.error(f"Transaction failed for {self.db_name}: {e}")
            return False
    
    async def create_tables_if_not_exists(self, metadata):
        """
        创建数据库表（如果不存在）
        
        Args:
            metadata: SQLAlchemy MetaData对象
        """
        await self.ensure_connected()
        
        def _sync_create_tables():
            metadata.create_all(bind=self.engine)
        
        try:
            await asyncio.get_event_loop().run_in_executor(None, _sync_create_tables)
            logger.info(f"Tables created/checked for {self.db_name}")
        except Exception as e:
            logger.error(f"Failed to create tables for {self.db_name}: {e}")
            raise
    
    async def get_table_count(self) -> int:
        """获取表数量"""
        try:
            result = await self.execute_query(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
            return result[0][0] if result else 0
        except Exception as e:
            logger.error(f"Failed to get table count for {self.db_name}: {e}")
            return 0
    
    async def get_database_size(self) -> Optional[int]:
        """获取数据库大小（字节）"""
        try:
            result = await self.execute_query("SELECT pg_database_size(current_database())")
            return result[0][0] if result else None
        except Exception as e:
            logger.error(f"Failed to get database size for {self.db_name}: {e}")
            return None
    
    async def check_table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        try:
            result = await self.execute_query(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)",
                {'table_name': table_name}
            )
            return result[0][0] if result else False
        except Exception as e:
            logger.error(f"Failed to check table existence for {self.db_name}: {e}")
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        base_metrics = super().get_metrics()
        
        if self.engine:
            pool_metrics = {
                'pool_size': self.engine.pool.size(),
                'checked_in': self.engine.pool.checkedin(),
                'checked_out': self.engine.pool.checkedout(),
                'overflow': self.engine.pool.overflow()
            }
            # QueuePool没有invalid()方法，改为检查无效连接的属性
            try:
                pool_metrics['invalid'] = getattr(self.engine.pool, '_invalidated', 0)
            except AttributeError:
                pool_metrics['invalid'] = 0
            base_metrics['pool_metrics'] = pool_metrics
        
        return base_metrics