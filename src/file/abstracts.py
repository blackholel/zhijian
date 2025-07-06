"""
文件管理系统抽象基类定义
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncGenerator
from pathlib import Path
import io

from .models import DocumentInfo, ChunkInfo, ProcessingStatus


class FileStorage(ABC):
    """文件存储抽象基类"""
    
    @abstractmethod
    async def upload_file(self, file_path: str, storage_key: str, content_type: str = None) -> str:
        """上传文件到存储"""
        pass
    
    @abstractmethod
    async def upload_bytes(self, data: bytes, storage_key: str, content_type: str = None) -> str:
        """上传二进制数据到存储"""
        pass
    
    @abstractmethod
    async def download_file(self, storage_key: str, local_path: str) -> bool:
        """下载文件到本地"""
        pass
    
    @abstractmethod
    async def get_file_stream(self, storage_key: str) -> AsyncGenerator[bytes, None]:
        """获取文件流"""
        pass
    
    @abstractmethod
    async def get_file_bytes(self, storage_key: str) -> bytes:
        """获取文件二进制数据"""
        pass
    
    @abstractmethod
    async def delete_file(self, storage_key: str) -> bool:
        """删除文件"""
        pass
    
    @abstractmethod
    async def file_exists(self, storage_key: str) -> bool:
        """检查文件是否存在"""
        pass
    
    @abstractmethod
    async def get_file_info(self, storage_key: str) -> Dict[str, Any]:
        """获取文件信息"""
        pass
    
    @abstractmethod
    async def list_files(self, prefix: str = "") -> List[str]:
        """列出文件"""
        pass


class MetadataStorage(ABC):
    """元数据存储抽象基类"""
    
    @abstractmethod
    async def save_document(self, document: DocumentInfo) -> bool:
        """保存文档信息"""
        pass
    
    @abstractmethod
    async def get_document(self, document_id: str) -> Optional[DocumentInfo]:
        """获取文档信息"""
        pass
    
    @abstractmethod
    async def get_documents_by_kb(self, kb_id: str, limit: int = 100, offset: int = 0) -> List[DocumentInfo]:
        """获取知识库文档列表"""
        pass
    
    @abstractmethod
    async def update_document_status(self, document_id: str, status: ProcessingStatus, 
                                   error_message: Optional[str] = None) -> bool:
        """更新文档状态"""
        pass
    
    @abstractmethod
    async def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        pass
    
    @abstractmethod
    async def search_documents(self, query: str, kb_id: Optional[str] = None, 
                             limit: int = 20) -> List[DocumentInfo]:
        """搜索文档"""
        pass


class ChunkStorage(ABC):
    """分块存储抽象基类"""
    
    @abstractmethod
    async def save_chunks(self, chunks: List[ChunkInfo]) -> bool:
        """批量保存分块"""
        pass
    
    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> Optional[ChunkInfo]:
        """获取分块信息"""
        pass
    
    @abstractmethod
    async def get_chunks_by_document(self, document_id: str) -> List[ChunkInfo]:
        """获取文档的所有分块"""
        pass
    
    @abstractmethod
    async def get_chunks_by_kb(self, kb_id: str, limit: int = 100, offset: int = 0) -> List[ChunkInfo]:
        """获取知识库的分块列表"""
        pass
    
    @abstractmethod
    async def delete_chunks_by_document(self, document_id: str) -> bool:
        """删除文档的所有分块"""
        pass
    
    @abstractmethod
    async def update_chunk_vector_id(self, chunk_id: str, vector_id: str) -> bool:
        """更新分块的向量ID"""
        pass
    
    @abstractmethod
    async def search_chunks(self, query: str, kb_id: Optional[str] = None, 
                          limit: int = 20) -> List[ChunkInfo]:
        """搜索分块"""
        pass


class CacheStorage(ABC):
    """缓存存储抽象基类"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """设置缓存值"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存值"""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        pass
    
    @abstractmethod
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """批量获取缓存值"""
        pass
    
    @abstractmethod
    async def set_many(self, data: Dict[str, Any], ttl: int = 3600) -> bool:
        """批量设置缓存值"""
        pass
    
    @abstractmethod
    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的缓存键"""
        pass
    
    @abstractmethod
    async def clear_cache(self) -> bool:
        """清空缓存"""
        pass


class DocumentProcessor(ABC):
    """文档处理器抽象基类"""
    
    @abstractmethod
    def can_process(self, file_path: str) -> bool:
        """检查是否可以处理该文件"""
        pass
    
    @abstractmethod
    async def process_document(self, file_path: str, params: Dict[str, Any] = None) -> str:
        """处理文档，返回处理后的文本内容"""
        pass
    
    @abstractmethod
    async def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """提取文档元数据"""
        pass


class ChunkProcessor(ABC):
    """分块处理器抽象基类"""
    
    @abstractmethod
    async def chunk_text(self, text: str, document_id: str, kb_id: str,
                        chunk_size: int = 500, chunk_overlap: int = 50) -> List[ChunkInfo]:
        """将文本分块"""
        pass
    
    @abstractmethod
    async def rechunk_document(self, document_id: str, chunk_size: int = 500, 
                             chunk_overlap: int = 50) -> List[ChunkInfo]:
        """重新分块文档"""
        pass