"""
文件存储仓储
"""

import logging
import json
from typing import List, Optional, Dict, Any
from enum import Enum

from .base import FileRepository as BaseFileRepository
from ..connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)


class FileStatus(Enum):
    """文件状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"


class FileInfo:
    """文件信息模型"""
    
    def __init__(self, file_id: str, filename: str, storage_key: str,
                 size: int = 0, content_type: str = None, metadata: Dict[str, Any] = None):
        self.file_id = file_id
        self.filename = filename
        self.storage_key = storage_key
        self.size = size
        self.content_type = content_type
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'file_id': self.file_id,
            'filename': self.filename,
            'storage_key': self.storage_key,
            'size': self.size,
            'content_type': self.content_type,
            'metadata': self.metadata
        }


class FileRepository(BaseFileRepository[FileInfo]):
    """文件存储仓储"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        super().__init__(connection_manager, 'minio')
    
    async def create(self, file_info: FileInfo) -> FileInfo:
        """创建文件记录"""
        try:
            # 获取PostgreSQL适配器
            postgres_adapter = await self.connection_manager.get_adapter('server_db')
            
            # 确保连接可用
            await postgres_adapter.ensure_connected()
            
            # 插入文件信息
            query = """
                INSERT INTO files (file_id, filename, storage_key, size, content_type, metadata, status, created_at, updated_at)
                VALUES (:file_id, :filename, :storage_key, :size, :content_type, :metadata, :status, NOW(), NOW())
                RETURNING file_id, filename, storage_key, size, content_type, metadata, status, created_at, updated_at
            """
            
            params = {
                'file_id': file_info.file_id,
                'filename': file_info.filename,
                'storage_key': file_info.storage_key,
                'size': file_info.size,
                'content_type': file_info.content_type,
                'metadata': json.dumps(file_info.metadata) if file_info.metadata else '{}',
                'status': FileStatus.PENDING.value
            }
            logger.info(f"Executing INSERT with params: {params}")
            result = await postgres_adapter.execute_query(query, params)
            logger.info(f"INSERT result: {result}")
            
            if result and len(result) > 0:
                # result是元组列表，按INSERT RETURNING字段顺序：
                # file_id, filename, storage_key, size, content_type, metadata, status, created_at, updated_at
                row = result[0]
                file_info.status = row[6]  # status字段
                file_info.created_at = row[7]  # created_at字段
                file_info.updated_at = row[8]  # updated_at字段
                
                logger.info(f"File record created successfully: {file_info.file_id}")
                
                # 立即验证插入是否成功
                verify_query = "SELECT COUNT(*) FROM files WHERE file_id = :file_id"
                verify_result = await postgres_adapter.execute_query(verify_query, {'file_id': file_info.file_id})
                logger.info(f"Verification query result: {verify_result}")
            
            return file_info
            
        except Exception as e:
            logger.error(f"Failed to create file record: {e}")
            raise
    
    async def get_by_id(self, file_id: str) -> Optional[FileInfo]:
        """根据ID获取文件信息"""
        try:
            # 获取PostgreSQL适配器
            postgres_adapter = await self.connection_manager.get_adapter('server_db')
            
            # 确保连接可用
            await postgres_adapter.ensure_connected()
            
            # 查询文件信息
            query = """
                SELECT file_id, filename, storage_key, size, content_type, metadata, status, created_at, updated_at
                FROM files 
                WHERE file_id = :file_id
            """
            
            logger.debug(f"Querying file with ID: {file_id}")
            result = await postgres_adapter.execute_query(query, {'file_id': file_id})
            logger.debug(f"Query result: {result}")
            
            if result and len(result) > 0:
                # result是元组列表，按SELECT字段顺序：
                # file_id, filename, storage_key, size, content_type, metadata, status, created_at, updated_at
                row = result[0]
                
                # 解析metadata JSON字段
                metadata_json = row[5] if len(row) > 5 else '{}'
                if isinstance(metadata_json, str):
                    try:
                        metadata = json.loads(metadata_json)
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                else:
                    metadata = metadata_json or {}
                
                file_info = FileInfo(
                    file_id=row[0],
                    filename=row[1],
                    storage_key=row[2],
                    size=row[3] if len(row) > 3 and row[3] is not None else 0,
                    content_type=row[4] if len(row) > 4 else None,
                    metadata=metadata
                )
                
                # 添加额外的属性
                file_info.status = row[6] if len(row) > 6 else FileStatus.PENDING.value
                file_info.created_at = row[7] if len(row) > 7 else None
                file_info.updated_at = row[8] if len(row) > 8 else None
                
                logger.info(f"File found: {file_info.file_id}")
                return file_info
            
            logger.warning(f"File not found: {file_id}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get file by ID {file_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def update(self, file_info: FileInfo) -> FileInfo:
        """更新文件信息"""
        # 实现更新逻辑
        return file_info
    
    async def delete(self, file_id: str) -> bool:
        """删除文件"""
        # 实现删除逻辑
        return True
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[FileInfo]:
        """查找所有文件"""
        # 实现查找逻辑
        return []