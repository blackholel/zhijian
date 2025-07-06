"""
文件管理器 - 统一的文件管理接口

整合所有存储组件，提供高级文件管理功能
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .abstracts import FileStorage, MetadataStorage, ChunkStorage, CacheStorage
from .models import (
    DocumentInfo, ChunkInfo, ProcessingStatus, DocumentType, 
    ProcessingResult, FileUploadRequest, StorageConfig
)
from .exceptions import (
    FileManagementError, StorageError, ValidationError,
    DocumentNotFoundError, ProcessingError
)
# from .storage import MinIOFileStorage, PostgreSQLMetadataStorage, PostgreSQLChunkStorage, RedisCacheStorage
# Storage components have been moved to src.database architecture

logger = logging.getLogger(__name__)


class FileManager:
    """文件管理器 - 生产级文件管理系统的核心类"""
    
    def __init__(
        self,
        file_storage: FileStorage,
        metadata_storage: MetadataStorage,
        chunk_storage: ChunkStorage,
        cache_storage: Optional[CacheStorage] = None
    ):
        """初始化文件管理器
        
        Args:
            file_storage: 文件存储实现
            metadata_storage: 元数据存储实现  
            chunk_storage: 分块存储实现
            cache_storage: 缓存存储实现（可选）
        """
        self.file_storage = file_storage
        self.metadata_storage = metadata_storage
        self.chunk_storage = chunk_storage
        self.cache_storage = cache_storage
        
        # 处理状态锁，防止并发处理同一文档
        self._processing_locks: Dict[str, asyncio.Lock] = {}
        
        logger.info("文件管理器初始化完成")
    
    @classmethod
    async def create_from_config(cls, config: StorageConfig) -> 'FileManager':
        """从配置创建文件管理器
        
        Args:
            config: 存储配置
            
        Returns:
            FileManager实例
        """
        # TODO: Update to use new database architecture
        # The storage components have been moved to src.database
        raise NotImplementedError("FileManager has been deprecated. Use new database architecture instead.")
    
    def _get_processing_lock(self, document_id: str) -> asyncio.Lock:
        """获取文档处理锁"""
        if document_id not in self._processing_locks:
            self._processing_locks[document_id] = asyncio.Lock()
        return self._processing_locks[document_id]
    
    def _generate_document_id(self, kb_id: str, filename: str) -> str:
        """生成文档ID"""
        unique_str = f"{kb_id}:{filename}:{time.time()}:{uuid.uuid4().hex[:8]}"
        return hashlib.sha256(unique_str.encode()).hexdigest()[:32]
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _detect_file_type(self, filename: str) -> DocumentType:
        """检测文件类型"""
        suffix = Path(filename).suffix.lower()
        type_mapping = {
            '.pdf': DocumentType.PDF,
            '.docx': DocumentType.DOCX,
            '.doc': DocumentType.DOCX,
            '.txt': DocumentType.TXT,
            '.md': DocumentType.MD,
            '.html': DocumentType.HTML,
            '.htm': DocumentType.HTML,
            '.csv': DocumentType.CSV,
            '.json': DocumentType.JSON,
            '.png': DocumentType.IMAGE,
            '.jpg': DocumentType.IMAGE,
            '.jpeg': DocumentType.IMAGE,
            '.gif': DocumentType.IMAGE,
            '.bmp': DocumentType.IMAGE
        }
        return type_mapping.get(suffix, DocumentType.UNKNOWN)
    
    def _generate_storage_path(self, kb_id: str, document_id: str, filename: str) -> str:
        """生成存储路径"""
        safe_filename = Path(filename).name  # 确保只有文件名，没有路径
        return f"{kb_id}/documents/{document_id}/{safe_filename}"
    
    async def upload_file(self, request: FileUploadRequest) -> DocumentInfo:
        """上传文件
        
        Args:
            request: 文件上传请求
            
        Returns:
            文档信息
            
        Raises:
            FileManagementError: 上传失败
        """
        try:
            # 验证文件
            file_path_obj = Path(request.file_path)
            if not file_path_obj.exists():
                raise ValidationError(f"文件不存在: {request.file_path}")
            
            if not file_path_obj.is_file():
                raise ValidationError(f"不是有效文件: {request.file_path}")
            
            # 生成文档ID和基本信息
            document_id = self._generate_document_id(request.kb_id, request.filename)
            file_size = file_path_obj.stat().st_size
            file_hash = self._calculate_file_hash(request.file_path)
            file_type = self._detect_file_type(request.filename)
            
            # 创建文档信息
            document = DocumentInfo(
                document_id=document_id,
                kb_id=request.kb_id,
                filename=request.filename,
                original_path=request.file_path,
                file_type=file_type,
                file_size=file_size,
                file_hash=file_hash,
                status=ProcessingStatus.PENDING,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                owner_id=request.owner_id,
                metadata=request.metadata
            )
            
            # 生成存储路径
            storage_path = self._generate_storage_path(
                request.kb_id, document_id, request.filename
            )
            document.storage_path = storage_path
            
            # 保存文档元数据
            success = await self.metadata_storage.save_document(document)
            if not success:
                raise StorageError("保存文档元数据失败")
            
            # 上传文件到对象存储
            await self.file_storage.upload_file(
                file_path=request.file_path,
                storage_key=storage_path
            )
            
            # 缓存文档信息
            if self.cache_storage:
                await self.cache_storage.cache_document(document)
            
            logger.info(f"文件上传成功: {document_id} -> {storage_path}")
            return document
            
        except Exception as e:
            logger.error(f"文件上传失败: {e}")
            raise FileManagementError(f"文件上传失败: {e}")
    
    async def process_document(self, document_id: str, processing_params: Dict[str, Any] = None) -> ProcessingResult:
        """处理文档（分块、向量化等）
        
        Args:
            document_id: 文档ID
            processing_params: 处理参数
            
        Returns:
            处理结果
        """
        # 获取处理锁，防止并发处理
        lock = self._get_processing_lock(document_id)
        async with lock:
            try:
                # 获取文档信息
                document = await self.get_document(document_id)
                if not document:
                    raise DocumentNotFoundError(f"文档不存在: {document_id}")
                
                if document.status == ProcessingStatus.PROCESSING:
                    raise ProcessingError(f"文档正在处理中: {document_id}")
                
                # 更新状态为处理中
                await self.metadata_storage.update_document_status(
                    document_id, ProcessingStatus.PROCESSING
                )
                
                start_time = time.time()
                chunks = []
                
                try:
                    # 获取文件内容
                    file_content = await self._get_processed_content(document)
                    
                    # 分块处理
                    chunks = await self._chunk_document(
                        content=file_content,
                        document_id=document_id,
                        kb_id=document.kb_id,
                        params=processing_params or {}
                    )
                    
                    # 保存分块
                    if chunks:
                        success = await self.chunk_storage.save_chunks(chunks)
                        if not success:
                            raise StorageError("保存分块失败")
                    
                    # 更新状态为完成
                    await self.metadata_storage.update_document_status(
                        document_id, ProcessingStatus.COMPLETED
                    )
                    
                    # 缓存分块
                    if self.cache_storage and chunks:
                        await self.cache_storage.cache_chunks(chunks)
                    
                    processing_time = time.time() - start_time
                    
                    result = ProcessingResult(
                        document_id=document_id,
                        status=ProcessingStatus.COMPLETED,
                        chunks=chunks,
                        processed_content=file_content,
                        processing_time=processing_time
                    )
                    
                    logger.info(f"文档处理成功: {document_id}, 生成 {len(chunks)} 个分块")
                    return result
                    
                except Exception as e:
                    # 处理失败，更新状态
                    error_msg = str(e)
                    await self.metadata_storage.update_document_status(
                        document_id, ProcessingStatus.FAILED, error_msg
                    )
                    
                    processing_time = time.time() - start_time
                    
                    result = ProcessingResult(
                        document_id=document_id,
                        status=ProcessingStatus.FAILED,
                        chunks=[],
                        error_message=error_msg,
                        processing_time=processing_time
                    )
                    
                    logger.error(f"文档处理失败: {document_id}, 错误: {e}")
                    return result
                    
            except Exception as e:
                logger.error(f"文档处理异常: {document_id}, 错误: {e}")
                raise ProcessingError(f"文档处理异常: {e}")
    
    async def _get_processed_content(self, document: DocumentInfo) -> str:
        """获取处理后的文档内容"""
        try:
            # 从对象存储获取文件
            file_content = await self.file_storage.get_file_bytes(document.storage_path)
            
            # 根据文件类型处理内容
            if document.file_type == DocumentType.PDF:
                return await self._process_pdf_content(file_content)
            elif document.file_type == DocumentType.DOCX:
                return await self._process_docx_content(file_content)
            elif document.file_type in [DocumentType.TXT, DocumentType.MD]:
                return file_content.decode('utf-8')
            else:
                # 对于其他类型，尝试作为文本处理
                try:
                    return file_content.decode('utf-8')
                except UnicodeDecodeError:
                    return f"二进制文件: {document.filename}"
                    
        except Exception as e:
            logger.error(f"获取文档内容失败 {document.document_id}: {e}")
            raise ProcessingError(f"获取文档内容失败: {e}")
    
    async def _process_pdf_content(self, content: bytes) -> str:
        """处理PDF内容"""
        # 这里应该集成现有的PDF处理逻辑
        # 可以使用 src.core.indexing 中的 parse_pdf 函数
        try:
            from src.core.indexing import parse_pdf_async
            import tempfile
            import os
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                
                try:
                    # 使用现有的PDF处理逻辑
                    text = await parse_pdf_async(tmp_file.name)
                    return text
                finally:
                    os.unlink(tmp_file.name)
                    
        except Exception as e:
            logger.error(f"PDF处理失败: {e}")
            return f"PDF处理失败: {e}"
    
    async def _process_docx_content(self, content: bytes) -> str:
        """处理DOCX内容"""
        try:
            from docx import Document
            import io
            
            doc = Document(io.BytesIO(content))
            text = '\n'.join([para.text for para in doc.paragraphs])
            return text
            
        except Exception as e:
            logger.error(f"DOCX处理失败: {e}")
            return f"DOCX处理失败: {e}"
    
    async def _chunk_document(self, content: str, document_id: str, kb_id: str, 
                            params: Dict[str, Any]) -> List[ChunkInfo]:
        """分块文档"""
        try:
            from src.core.indexing import chunk_text
            
            # 获取分块参数
            chunk_size = params.get('chunk_size', 500)
            chunk_overlap = params.get('chunk_overlap', 50)
            
            # 使用现有的分块逻辑
            text_chunks = chunk_text(content, {'chunk_size': chunk_size, 'chunk_overlap': chunk_overlap})
            
            chunks = []
            for i, chunk_data in enumerate(text_chunks):
                chunk_id = f"{document_id}_{i:04d}"
                
                chunk_info = ChunkInfo(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    kb_id=kb_id,
                    content=chunk_data['text'],
                    chunk_index=i,
                    start_char=0,  # 这里需要根据实际情况计算
                    end_char=len(chunk_data['text']),
                    chunk_size=len(chunk_data['text']),
                    created_at=datetime.now(),
                    metadata=chunk_data.get('metadata', {})
                )
                chunks.append(chunk_info)
            
            return chunks
            
        except Exception as e:
            logger.error(f"文档分块失败: {e}")
            raise ProcessingError(f"文档分块失败: {e}")
    
    async def get_document(self, document_id: str) -> Optional[DocumentInfo]:
        """获取文档信息"""
        try:
            # 先从缓存获取
            if self.cache_storage:
                cached_doc = await self.cache_storage.get_cached_document(document_id)
                if cached_doc:
                    return cached_doc
            
            # 从数据库获取
            document = await self.metadata_storage.get_document(document_id)
            
            # 缓存结果
            if document and self.cache_storage:
                await self.cache_storage.cache_document(document)
            
            return document
            
        except Exception as e:
            logger.error(f"获取文档失败 {document_id}: {e}")
            return None
    
    async def get_documents_by_kb(self, kb_id: str, limit: int = 100, 
                                offset: int = 0) -> List[DocumentInfo]:
        """获取知识库文档列表"""
        try:
            return await self.metadata_storage.get_documents_by_kb(kb_id, limit, offset)
        except Exception as e:
            logger.error(f"获取知识库文档列表失败 {kb_id}: {e}")
            return []
    
    async def get_document_chunks(self, document_id: str) -> List[ChunkInfo]:
        """获取文档分块"""
        try:
            # 先从缓存获取
            if self.cache_storage:
                cached_chunks = await self.cache_storage.get_cached_chunks_by_document(document_id)
                if cached_chunks:
                    return cached_chunks
            
            # 从数据库获取
            chunks = await self.chunk_storage.get_chunks_by_document(document_id)
            
            # 缓存结果
            if chunks and self.cache_storage:
                await self.cache_storage.cache_chunks(chunks)
            
            return chunks
            
        except Exception as e:
            logger.error(f"获取文档分块失败 {document_id}: {e}")
            return []
    
    async def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        try:
            # 获取文档信息
            document = await self.get_document(document_id)
            if not document:
                logger.warning(f"文档不存在: {document_id}")
                return True
            
            # 删除文件存储
            if document.storage_path:
                await self.file_storage.delete_file(document.storage_path)
            
            # 删除分块
            await self.chunk_storage.delete_chunks_by_document(document_id)
            
            # 删除文档元数据
            await self.metadata_storage.delete_document(document_id)
            
            # 清除缓存
            if self.cache_storage:
                await self.cache_storage.invalidate_document_cache(document_id)
            
            logger.info(f"文档删除成功: {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除文档失败 {document_id}: {e}")
            return False
    
    async def search_documents(self, query: str, kb_id: Optional[str] = None, 
                             limit: int = 20) -> List[DocumentInfo]:
        """搜索文档"""
        try:
            # 先从缓存获取
            if self.cache_storage:
                cached_result = await self.cache_storage.get_cached_search_result(
                    query, kb_id, "documents"
                )
                if cached_result:
                    return cached_result
            
            # 从数据库搜索
            documents = await self.metadata_storage.search_documents(query, kb_id, limit)
            
            # 缓存结果
            if self.cache_storage:
                await self.cache_storage.cache_search_result(
                    query, kb_id, documents, "documents"
                )
            
            return documents
            
        except Exception as e:
            logger.error(f"搜索文档失败: {e}")
            return []
    
    async def search_chunks(self, query: str, kb_id: Optional[str] = None, 
                          limit: int = 20) -> List[ChunkInfo]:
        """搜索分块"""
        try:
            # 先从缓存获取
            if self.cache_storage:
                cached_result = await self.cache_storage.get_cached_search_result(
                    query, kb_id, "chunks"
                )
                if cached_result:
                    return cached_result
            
            # 从数据库搜索
            chunks = await self.chunk_storage.search_chunks(query, kb_id, limit)
            
            # 缓存结果
            if self.cache_storage:
                await self.cache_storage.cache_search_result(
                    query, kb_id, chunks, "chunks"
                )
            
            return chunks
            
        except Exception as e:
            logger.error(f"搜索分块失败: {e}")
            return []
    
    async def get_kb_statistics(self, kb_id: str) -> Dict[str, Any]:
        """获取知识库统计信息"""
        try:
            # 先从缓存获取
            if self.cache_storage:
                cached_stats = await self.cache_storage.get_cached_kb_statistics(kb_id)
                if cached_stats:
                    return cached_stats
            
            # 计算统计信息
            documents = await self.get_documents_by_kb(kb_id, limit=10000)
            chunk_stats = await self.chunk_storage.get_chunk_statistics(kb_id)
            
            stats = {
                'kb_id': kb_id,
                'total_documents': len(documents),
                'total_chunks': chunk_stats.get('total_chunks', 0),
                'total_size': sum(doc.file_size for doc in documents),
                'status_breakdown': {
                    'pending': len([d for d in documents if d.status == ProcessingStatus.PENDING]),
                    'processing': len([d for d in documents if d.status == ProcessingStatus.PROCESSING]),
                    'completed': len([d for d in documents if d.status == ProcessingStatus.COMPLETED]),
                    'failed': len([d for d in documents if d.status == ProcessingStatus.FAILED]),
                },
                'file_type_breakdown': {}
            }
            
            # 统计文件类型
            for doc in documents:
                file_type = doc.file_type.value
                stats['file_type_breakdown'][file_type] = stats['file_type_breakdown'].get(file_type, 0) + 1
            
            # 缓存统计信息
            if self.cache_storage:
                await self.cache_storage.cache_kb_statistics(kb_id, stats)
            
            return stats
            
        except Exception as e:
            logger.error(f"获取知识库统计失败 {kb_id}: {e}")
            return {}
    
    async def cleanup_orphaned_files(self, kb_id: Optional[str] = None) -> Dict[str, int]:
        """清理孤儿文件"""
        try:
            # 获取数据库中的文档
            if kb_id:
                documents = await self.get_documents_by_kb(kb_id, limit=10000)
            else:
                # 这里需要实现获取所有文档的方法
                documents = []
            
            # 获取存储中的文件
            prefix = f"{kb_id}/" if kb_id else ""
            storage_files = await self.file_storage.list_files(prefix)
            
            # 找出孤儿文件
            documented_paths = {doc.storage_path for doc in documents if doc.storage_path}
            orphaned_files = [f for f in storage_files if f not in documented_paths]
            
            # 删除孤儿文件
            deleted_count = 0
            for file_path in orphaned_files:
                success = await self.file_storage.delete_file(file_path)
                if success:
                    deleted_count += 1
            
            result = {
                'total_storage_files': len(storage_files),
                'documented_files': len(documented_paths),
                'orphaned_files': len(orphaned_files),
                'deleted_files': deleted_count
            }
            
            logger.info(f"清理孤儿文件完成: {result}")
            return result
            
        except Exception as e:
            logger.error(f"清理孤儿文件失败: {e}")
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """系统健康检查"""
        health = {
            'file_storage': False,
            'metadata_storage': False,
            'chunk_storage': False,
            'cache_storage': False,
            'overall': False
        }
        
        try:
            # 检查文件存储
            test_key = "health_check_test"
            await self.file_storage.upload_bytes(b"test", test_key)
            await self.file_storage.delete_file(test_key)
            health['file_storage'] = True
        except Exception as e:
            logger.error(f"文件存储健康检查失败: {e}")
        
        try:
            # 检查元数据存储（尝试查询一个不存在的文档）
            await self.metadata_storage.get_document("health_check_test")
            health['metadata_storage'] = True
        except Exception as e:
            logger.error(f"元数据存储健康检查失败: {e}")
        
        try:
            # 检查分块存储
            await self.chunk_storage.get_chunk("health_check_test")
            health['chunk_storage'] = True
        except Exception as e:
            logger.error(f"分块存储健康检查失败: {e}")
        
        if self.cache_storage:
            try:
                # 检查缓存存储
                await self.cache_storage.set("health_check", "test", 10)
                await self.cache_storage.delete("health_check")
                health['cache_storage'] = True
            except Exception as e:
                logger.error(f"缓存存储健康检查失败: {e}")
        else:
            health['cache_storage'] = True  # 缓存是可选的
        
        # 总体健康状态
        health['overall'] = all([
            health['file_storage'],
            health['metadata_storage'], 
            health['chunk_storage'],
            health['cache_storage']
        ])
        
        return health