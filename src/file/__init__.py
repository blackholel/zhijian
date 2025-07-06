"""
生产级文件管理系统

这个模块提供了完整的文件管理功能，适用于生产环境：
- 文档存储到MinIO对象存储
- 元数据和分块信息存储到PostgreSQL
- 高性能缓存使用Redis
- 不依赖内存存储，支持分布式部署
"""

from .manager import FileManager
from .models import DocumentInfo, ChunkInfo, ProcessingStatus, DocumentType, FileUploadRequest, StorageConfig
from .exceptions import FileManagementError, StorageError, ValidationError
from .config import ConfigLoader, load_storage_config, load_processing_config

__all__ = [
    'FileManager',
    'DocumentInfo',
    'ChunkInfo',
    'ProcessingStatus',
    'DocumentType',
    'FileUploadRequest',
    'StorageConfig',
    'FileManagementError',
    'StorageError',
    'ValidationError',
    'ConfigLoader',
    'load_storage_config',
    'load_processing_config'
]