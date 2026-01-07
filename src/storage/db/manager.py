import asyncio
import json
import os
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.utils.singleton import SingletonMeta
from src.storage.db.models import Base, User
from src.utils import logger


class DBManager(metaclass=SingletonMeta):
    """数据库管理器 - 提供异步数据库连接和会话管理"""

    def __init__(self):
        raw_url = os.getenv("POSTGRES_URI")
        if not raw_url or not raw_url.startswith("postgresql"):
            raise ValueError("POSTGRES_URI 未配置或不是 postgresql 连接串，无法初始化数据库")

        self.db_url = raw_url

        self.async_engine = create_async_engine(
            self.db_url,
            json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
            json_deserializer=json.loads,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        self.engine = create_engine(
            self.db_url.replace("+asyncpg", ""),
            json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
            json_deserializer=json.loads,
        )

        # 创建异步会话工厂
        self.AsyncSession = async_sessionmaker(bind=self.async_engine, class_=AsyncSession, expire_on_commit=False)

        self.Session = sessionmaker(bind=self.engine)

    def create_tables(self):
        """创建数据库表"""
        # 确保所有表都会被创建
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created/checked")

    def get_session(self):
        """获取同步数据库会话"""
        return self.Session()

    @contextmanager
    def get_session_context(self):
        """获取同步数据库会话的上下文管理器"""
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

    async def get_async_session(self):
        """获取异步数据库会话"""
        return self.AsyncSession()

    @asynccontextmanager
    async def get_async_session_context(self):
        """获取异步数据库会话的上下文管理器"""
        session = self.AsyncSession()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Async database operation failed: {e}")
            raise
        finally:
            # Shield close operation to ensure connection is properly closed even if task is cancelled
            # This prevents aiosqlite from raising errors during cancellation
            await asyncio.shield(session.close())

    def get_async_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self.AsyncSession

    def check_first_run(self):
        """检查是否首次运行（同步版本）"""
        session = self.get_session()
        try:
            # 检查是否有任何用户存在
            return session.query(User).count() == 0
        finally:
            session.close()

    async def async_check_first_run(self):
        """检查是否首次运行（异步版本）"""
        async with self.get_async_session_context() as session:
            # 检查是否有任何用户存在
            result = await session.execute(select(func.count(User.id)))
            count = result.scalar()
            return count == 0


# 创建全局数据库管理器实例
db_manager = DBManager()
