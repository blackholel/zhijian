"""
文件管理系统数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path


class ProcessingStatus(Enum):
    """文档处理状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DocumentType(Enum):
    """文档类型"""
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"
    HTML = "html"
    CSV = "csv"
    JSON = "json"
    IMAGE = "image"
    URL = "url"
    UNKNOWN = "unknown"


@dataclass
class DocumentInfo:
    """文档信息模型"""
    document_id: str
    kb_id: str
    filename: str
    original_path: str
    file_type: DocumentType
    file_size: int
    file_hash: str
    status: ProcessingStatus
    created_at: datetime
    updated_at: datetime
    owner_id: Optional[str] = None
    storage_path: Optional[str] = None
    processed_path: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'document_id': self.document_id,
            'kb_id': self.kb_id,
            'filename': self.filename,
            'original_path': self.original_path,
            'file_type': self.file_type.value,
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'owner_id': self.owner_id,
            'storage_path': self.storage_path,
            'processed_path': self.processed_path,
            'error_message': self.error_message,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentInfo':
        """从字典创建实例"""
        return cls(
            document_id=data['document_id'],
            kb_id=data['kb_id'],
            filename=data['filename'],
            original_path=data['original_path'],
            file_type=DocumentType(data['file_type']),
            file_size=data['file_size'],
            file_hash=data['file_hash'],
            status=ProcessingStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            owner_id=data.get('owner_id'),
            storage_path=data.get('storage_path'),
            processed_path=data.get('processed_path'),
            error_message=data.get('error_message'),
            metadata=data.get('metadata', {})
        )


@dataclass
class ChunkInfo:
    """分块信息模型"""
    chunk_id: str
    document_id: str
    kb_id: str
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    chunk_size: int
    created_at: datetime
    vector_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'chunk_id': self.chunk_id,
            'document_id': self.document_id,
            'kb_id': self.kb_id,
            'content': self.content,
            'chunk_index': self.chunk_index,
            'start_char': self.start_char,
            'end_char': self.end_char,
            'chunk_size': self.chunk_size,
            'created_at': self.created_at.isoformat(),
            'vector_id': self.vector_id,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkInfo':
        """从字典创建实例"""
        return cls(
            chunk_id=data['chunk_id'],
            document_id=data['document_id'],
            kb_id=data['kb_id'],
            content=data['content'],
            chunk_index=data['chunk_index'],
            start_char=data['start_char'],
            end_char=data['end_char'],
            chunk_size=data['chunk_size'],
            created_at=datetime.fromisoformat(data['created_at']),
            vector_id=data.get('vector_id'),
            metadata=data.get('metadata', {})
        )


@dataclass
class ProcessingResult:
    """处理结果模型"""
    document_id: str
    status: ProcessingStatus
    chunks: List[ChunkInfo]
    processed_content: Optional[str] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileUploadRequest:
    """文件上传请求"""
    file_path: str
    kb_id: str
    filename: str
    owner_id: Optional[str] = None
    processing_params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StorageConfig:
    """存储配置"""
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    postgres_url: str
    redis_url: str
    minio_secure: bool = False
    redis_password: Optional[str] = None