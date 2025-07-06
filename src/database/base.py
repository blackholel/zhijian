"""
数据库适配器基类和类型定义
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Union
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class DatabaseType(Enum):
    """数据库类型枚举"""
    POSTGRESQL = "postgresql"
    NEO4J = "neo4j"
    MILVUS = "milvus"
    REDIS = "redis"
    MINIO = "minio"


class ConnectionStatus(Enum):
    """连接状态枚举"""
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class DatabaseError(Exception):
    """数据库相关异常"""
    pass


class ConnectionError(DatabaseError):
    """连接相关异常"""
    pass


class ConfigurationError(DatabaseError):
    """配置相关异常"""
    pass


class DatabaseAdapter(ABC):
    """数据库适配器抽象基类"""
    
    def __init__(self, config: Dict[str, Any], db_name: str = None):
        """
        初始化适配器
        
        Args:
            config: 数据库配置字典
            db_name: 数据库名称
        """
        self.config = config
        self.db_name = db_name or "unknown"
        self.status = ConnectionStatus.DISCONNECTED
        self._client = None
        self._connection_pool = None
        self.retry_count = 0
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 1)
        
        logger.info(f"Initialized {self.__class__.__name__} for {self.db_name}")
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        建立数据库连接
        
        Returns:
            bool: 连接成功返回True，失败返回False
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        断开数据库连接
        
        Returns:
            bool: 断开成功返回True，失败返回False
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict[str, Any]: 健康检查结果
        """
        pass
    
    @abstractmethod
    async def get_connection_info(self) -> Dict[str, Any]:
        """
        获取连接信息
        
        Returns:
            Dict[str, Any]: 连接信息
        """
        pass
    
    @property
    def client(self):
        """获取数据库客户端"""
        if not self._client:
            raise ConnectionError(f"{self.__class__.__name__} not connected to {self.db_name}")
        return self._client
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.status == ConnectionStatus.CONNECTED
    
    @property
    def is_available(self) -> bool:
        """检查是否可用（连接状态且客户端存在）"""
        return self.is_connected and self._client is not None
    
    async def ensure_connected(self):
        """确保连接状态，如果未连接则尝试连接"""
        if not self.is_connected:
            await self.connect()
    
    async def retry_connection(self) -> bool:
        """重试连接"""
        for attempt in range(self.max_retries):
            try:
                if await self.connect():
                    self.retry_count = 0
                    return True
            except Exception as e:
                self.retry_count += 1
                logger.warning(
                    f"Connection attempt {attempt + 1}/{self.max_retries} failed for {self.db_name}: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))  # 指数退避
        
        self.status = ConnectionStatus.ERROR
        return False
    
    @asynccontextmanager
    async def get_session(self):
        """获取数据库会话的上下文管理器（子类可选择实现）"""
        await self.ensure_connected()
        try:
            yield self._client
        except Exception as e:
            logger.error(f"Session error in {self.db_name}: {e}")
            raise
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return {
            'database_name': self.db_name,
            'status': self.status.value,
            'retry_count': self.retry_count,
            'adapter_type': self.__class__.__name__
        }
    
    async def test_query(self) -> bool:
        """执行测试查询"""
        try:
            await self.health_check()
            return True
        except Exception as e:
            logger.error(f"Test query failed for {self.db_name}: {e}")
            return False


class SQLDatabaseAdapter(DatabaseAdapter):
    """SQL数据库适配器基类"""
    
    @abstractmethod
    async def execute_query(self, query: str, params: Dict[str, Any] = None) -> Any:
        """执行SQL查询"""
        pass
    
    @abstractmethod
    async def execute_transaction(self, queries: list) -> bool:
        """执行事务"""
        pass


class NoSQLDatabaseAdapter(DatabaseAdapter):
    """NoSQL数据库适配器基类"""
    
    @abstractmethod
    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """获取文档"""
        pass
    
    @abstractmethod
    async def save_document(self, collection: str, doc_id: str, document: Dict[str, Any]) -> bool:
        """保存文档"""
        pass


class CacheAdapter(DatabaseAdapter):
    """缓存适配器基类"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存值"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存值"""
        pass


class FileStorageAdapter(DatabaseAdapter):
    """文件存储适配器基类"""
    
    @abstractmethod
    async def upload_file(self, file_path: str, storage_key: str) -> str:
        """上传文件"""
        pass
    
    @abstractmethod
    async def download_file(self, storage_key: str, local_path: str) -> bool:
        """下载文件"""
        pass
    
    @abstractmethod
    async def delete_file(self, storage_key: str) -> bool:
        """删除文件"""
        pass