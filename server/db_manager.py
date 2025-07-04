import os
import pathlib
from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
from contextlib import contextmanager
from typing import Optional
import psycopg2
from psycopg2 import OperationalError
import time

from src import config
from server.models import Base
from server.models.user_model import User
from server.models.thread_model import Thread
from server.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode
from src.utils import logger

class DBManager:
    """数据库管理器 - 提供PostgreSQL连接和会话管理"""

    def __init__(self):
        self.config = config
        self.db_config = None
        self.engine = None
        self.Session = None
        self._initialize_database()

    def _initialize_database(self):
        """初始化数据库连接"""
        try:
            # 获取数据库配置
            self.db_config = self.config.get_database_config('server_db')
            logger.info(f"Database config loaded: {self.db_config.get('host')}:{self.db_config.get('port')}/{self.db_config.get('database')}")
            
            # 验证配置
            if not self.config.validate_database_config('server_db'):
                raise ValueError("Invalid database configuration")
            
            # 创建数据库连接
            self._create_engine()
            
            # 创建会话工厂
            self.Session = sessionmaker(bind=self.engine)
            
            # 测试连接
            self._test_connection()
            
            # 确保表存在
            self.create_tables()
            
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            self._fallback_to_sqlite()
    
    def _create_engine(self):
        """创建数据库引擎"""
        connection_string = self.config.get_database_connection_string('server_db')
        
        # 引擎参数
        engine_kwargs = {
            'pool_size': self.db_config.get('pool_size', 10),
            'max_overflow': self.db_config.get('max_overflow', 20),
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'connect_args': {
                'connect_timeout': self.db_config.get('connect_timeout', 30),
                'options': '-c timezone=UTC'
            }
        }
        
        if self.db_config.get('echo', False):
            engine_kwargs['echo'] = True
        
        self.engine = create_engine(connection_string, **engine_kwargs)
        
        # 添加连接事件监听器
        @event.listens_for(self.engine, "connect")
        def set_postgresql_search_path(dbapi_connection, connection_record):
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")
    
    def _test_connection(self):
        """测试数据库连接"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise
    
    def _fallback_to_sqlite(self):
        """回退到SQLite（开发模式）"""
        logger.warning("Falling back to SQLite database")
        self.db_path = os.path.join(config.save_dir, "database", "server.db")
        self.ensure_db_dir()
        
        # 创建SQLite引擎
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        
        # 创建会话工厂
        self.Session = sessionmaker(bind=self.engine)
        
        # 确保表存在
        self.create_tables()
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_connection_info(self) -> dict:
        """获取连接信息"""
        if self.db_config:
            return {
                'type': 'postgresql',
                'host': self.db_config.get('host'),
                'port': self.db_config.get('port'),
                'database': self.db_config.get('database'),
                'pool_size': self.db_config.get('pool_size'),
                'max_overflow': self.db_config.get('max_overflow')
            }
        else:
            return {
                'type': 'sqlite',
                'path': getattr(self, 'db_path', 'unknown')
            }
    
    def retry_connection(self, max_retries: int = 3, delay: float = 1.0) -> bool:
        """重试数据库连接"""
        for attempt in range(max_retries):
            try:
                self._test_connection()
                return True
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay * (2 ** attempt))  # 指数退避
        return False

    def ensure_db_dir(self):
        """确保数据库目录存在（SQLite回退模式）"""
        if hasattr(self, 'db_path'):
            db_dir = os.path.dirname(self.db_path)
            pathlib.Path(db_dir).mkdir(parents=True, exist_ok=True)

    def create_tables(self):
        """创建数据库表"""
        try:
            # 确保所有表都会被创建
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created/checked")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    def get_session(self):
        """获取数据库会话"""
        if not self.Session:
            raise RuntimeError("Database not initialized")
        return self.Session()

    @contextmanager
    def get_session_context(self):
        """获取数据库会话的上下文管理器"""
        if not self.Session:
            raise RuntimeError("Database not initialized")
        
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            session.close()
    
    def execute_raw_sql(self, sql: str, params: dict = None):
        """执行原始SQL语句"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                return result
        except Exception as e:
            logger.error(f"Failed to execute raw SQL: {e}")
            raise

    def check_first_run(self):
        """检查是否首次运行"""
        try:
            session = self.get_session()
            try:
                # 检查是否有任何用户存在
                return session.query(User).count() == 0
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error checking first run: {e}")
            return True  # 假设是首次运行
    
    def get_database_size(self) -> Optional[int]:
        """获取数据库大小（字节）"""
        try:
            if self.db_config:  # PostgreSQL
                sql = "SELECT pg_database_size(current_database())"
                result = self.execute_raw_sql(sql)
                return result.scalar()
            elif hasattr(self, 'db_path'):  # SQLite
                return os.path.getsize(self.db_path)
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
        return None
    
    def get_table_count(self) -> int:
        """获取表数量"""
        try:
            if self.db_config:  # PostgreSQL
                sql = "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
            else:  # SQLite
                sql = "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            
            result = self.execute_raw_sql(sql)
            return result.scalar()
        except Exception as e:
            logger.error(f"Error getting table count: {e}")
            return 0
    
    def close(self):
        """关闭数据库连接"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

# 创建全局数据库管理器实例
try:
    db_manager = DBManager()
except Exception as e:
    logger.error(f"Failed to initialize database manager: {e}")
    raise
