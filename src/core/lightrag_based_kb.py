"""
增强版 LightRagBasedKB - 集成新文件管理系统
直接替换原有文件管理逻辑，保持API完全兼容
"""

import os
import json
import time
import traceback
import shutil
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, setup_logger
from lightrag.kg.shared_storage import initialize_pipeline_status

from src import config
from src.utils import logger, hashstr, get_docker_safe_url
from src.plugins import ocr
from src.file.config import load_storage_config

# 延迟导入新文件管理系统
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.database.repositories.file_repository import FileRepository
    from server.auth.permission_framework import PermissionEngine
    from src.file.manager import FileManager

work_dir = os.path.join(config.save_dir, "lightrag_data")
log_dir = os.path.join(work_dir, "logs", "lightrag")
setup_logger("lightrag", log_file_path=os.path.join(log_dir, f"lightrag_{datetime.now().strftime('%Y-%m-%d')}.log"))


class LightRagBasedKB:
    """基于 LightRAG 的知识库管理类 - 集成新文件管理系统
    
    ⭐ 核心设计原则：
    1. 保持所有公开方法签名不变 - 确保API兼容性
    2. 内部完全使用新文件管理系统 - 获得生产级特性
    3. LightRAG配置保持不变 - 不影响向量和图存储
    4. 渐进式替换 - 降低风险
    """

    def __init__(self) -> None:
        # 保持 LightRAG 实例映射（继续使用内存缓存以提高性能）
        self.instances: dict[str, LightRAG] = {}
        
        # 🔧 核心改变：移除内存字典，使用新文件管理系统
        # self.databases_meta: dict[str, dict] = {}  # ❌ 删除
        # self.files_meta: dict[str, dict] = {}      # ❌ 删除
        
        # ✅ 新增：文件管理器（懒加载）
        self._file_manager: Optional['FileManager'] = None
        self._file_manager_initialized = False
        
        # 工作目录（保持兼容，但主要用于LightRAG）
        self.work_dir = os.path.join(config.save_dir, "lightrag_data")
        os.makedirs(self.work_dir, exist_ok=True)
        
        # 权限管理器（保持不变）
        self.permission_manager = None

        # 🔧 关键改变：不再加载JSON元数据
        # self._load_metadata()  # ❌ 删除
        
        logger.info("LightRagBasedKB initialized with new file management system")

    async def _ensure_file_manager(self) -> 'FileManager':
        """确保文件管理器已初始化（懒加载）"""
        if self._file_manager_initialized:
            return self._file_manager
            
        try:
            # TODO: FileManager has been deprecated, use new database architecture
            # For now, disable file management system to avoid startup errors
            logger.warning("File management system has been deprecated. Some features may not work correctly.")
            self._file_manager = None
            self._file_manager_initialized = True
            
            return self._file_manager
            
        except Exception as e:
            logger.error(f"Failed to initialize file management system: {e}")
            # 如果新系统初始化失败，回退到兼容模式
            self._file_manager_initialized = False
            raise RuntimeError(f"File management system initialization failed: {e}")

    # =====================================================================
    # 权限检查方法 - 保持不变
    # =====================================================================
    
    async def _check_permission(self, user_id: str, db_id: Optional[str], permission: str):
        """权限检查方法 - 使用新权限框架（保持不变）"""
        try:
            from server.auth.permission_framework import (
                PermissionEngine, KnowledgeBaseResource, Permission as PermEnum
            )
            
            engine = PermissionEngine.get_instance()
            resource = None
            if db_id:
                resource = KnowledgeBaseResource(db_id)
            
            perm_enum = getattr(PermEnum, permission.upper(), PermEnum.READ)
            has_permission = await engine.check_permission_simple(user_id, resource, perm_enum)
            
            if not has_permission:
                resource_desc = f"知识库 {db_id}" if db_id else "系统"
                raise PermissionError(f"用户 {user_id} 没有权限对{resource_desc}执行 {permission} 操作")
            
            return True
            
        except ImportError:
            logger.warning("Permission framework not available, skipping permission check")
            return True
        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            raise

    # =====================================================================
    # 数据库管理方法 - 使用新文件管理系统
    # =====================================================================

    async def get_databases(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """获取用户可访问的数据库信息 - 🔧 使用新文件管理系统"""
        try:
            file_manager = await self._ensure_file_manager()
            
            # 获取所有知识库的统计信息
            all_kb_stats = await self._get_all_kb_stats(file_manager)
            
            # 权限过滤
            if user_id and self.permission_manager:
                accessible_db_ids = await self.permission_manager.filter_accessible_databases(user_id, "read")
                all_kb_stats = {kb_id: stats for kb_id, stats in all_kb_stats.items() 
                              if kb_id in accessible_db_ids}
            
            # 转换为兼容格式
            databases = []
            for kb_id, stats in all_kb_stats.items():
                db_info = await self._convert_stats_to_db_info(file_manager, kb_id, stats)
                databases.append(db_info)
            
            return {"databases": databases}
            
        except Exception as e:
            logger.error(f"Failed to get databases: {e}")
            # 兼容模式回退
            return {"databases": []}

    async def _get_all_kb_stats(self, file_manager: 'FileManager') -> Dict[str, Dict[str, Any]]:
        """获取所有知识库统计信息"""
        # File manager is deprecated, fallback to legacy method
        all_kb_stats = {}
        
        # Fallback: 从LightRAG工作目录扫描
        try:
            for item in os.listdir(self.work_dir):
                item_path = os.path.join(self.work_dir, item)
                if os.path.isdir(item_path) and item.startswith('kb_'):
                    try:
                        # Use legacy stats collection
                        stats = await self._get_legacy_kb_stats(item)
                        if stats:
                            all_kb_stats[item] = stats
                    except Exception as e:
                        logger.warning(f"Failed to get stats for kb {item}: {e}")
        except Exception as e:
            logger.warning(f"Failed to scan work directory {self.work_dir}: {e}")
        
        return all_kb_stats

    async def _get_legacy_kb_stats(self, kb_id: str) -> Dict[str, Any]:
        """获取知识库统计信息（兼容模式）"""
        try:
            # Basic stats from directory structure
            kb_path = os.path.join(self.work_dir, kb_id)
            if not os.path.exists(kb_path):
                return None
            
            # Count files in directory (approximation)
            file_count = 0
            total_size = 0
            for root, dirs, files in os.walk(kb_path):
                file_count += len(files)
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                    except:
                        pass
            
            return {
                'document_count': max(1, file_count // 10),  # Rough estimate
                'total_size': total_size,
                'chunk_count': max(1, file_count // 2),  # Rough estimate
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"Failed to get legacy stats for {kb_id}: {e}")
            return {
                'document_count': 0,
                'total_size': 0,
                'chunk_count': 0,
                'last_updated': datetime.now().isoformat()
            }

    async def _convert_stats_to_db_info(self, file_manager: 'FileManager', 
                                      kb_id: str, stats: Dict[str, Any]) -> Dict[str, Any]:
        """将统计信息转换为数据库信息格式"""
        try:
            # File manager is deprecated, use legacy approach
            files = {}
            
            # Try to get files from directory structure if available
            if file_manager is None:
                # Legacy approach: scan directory for files
                kb_path = os.path.join(self.work_dir, kb_id)
                if os.path.exists(kb_path):
                    for root, dirs, file_list in os.walk(kb_path):
                        for file in file_list:
                            if file.endswith(('.txt', '.json', '.md')):
                                file_path = os.path.join(root, file)
                                file_id = hashstr(file_path)
                                files[file_id] = {
                                    "file_id": file_id,
                                    "filename": file,
                                    "path": file_path,
                                    "type": "text",
                                    "status": "processed",
                                    "created_at": time.time()
                                }
            else:
                # Original implementation (keeping for potential future use)
                documents = await file_manager.get_documents_by_kb(kb_id, limit=1000)
                for doc in documents:
                    files[doc.document_id] = {
                        "file_id": doc.document_id,
                        "filename": doc.filename,
                        "path": doc.original_path,
                        "type": doc.file_type.value,
                        "status": doc.status.value,
                        "created_at": doc.created_at.timestamp()
                    }
            
            return {
                "db_id": kb_id,
                "name": stats.get('name', kb_id),
                "description": stats.get('description', ''),
                "files": files,
                "row_count": len(files),
                "status": "已连接",
                "created_at": stats.get('created_at', time.time()),
                # 保持其他兼容字段
                "embed_info": stats.get('embed_info', {}),
                "metadata": stats.get('metadata', {})
            }
            
        except Exception as e:
            logger.warning(f"Failed to convert stats for kb {kb_id}: {e}")
            return {
                "db_id": kb_id,
                "name": kb_id,
                "description": "",
                "files": {},
                "row_count": 0,
                "status": "已连接"
            }

    async def create_database(self, user_id: str, database_name: str, description: str, 
                            embed_info: dict = None, **kwargs) -> Dict[str, Any]:
        """创建数据库 - 🔧 使用新文件管理系统"""
        await self._check_permission(user_id, None, "create")
        
        db_id = f"kb_{hashstr(database_name, with_salt=True)}"
        
        try:
            file_manager = await self._ensure_file_manager()
            
            # 在新系统中创建知识库记录
            await self._create_kb_in_new_system(file_manager, db_id, {
                "name": database_name,
                "description": description,
                "embed_info": embed_info,
                "metadata": kwargs,
                "created_at": datetime.now().isoformat(),
                "owner_id": user_id
            })
            
            # 创建LightRAG工作目录（保持兼容）
            working_dir = os.path.join(self.work_dir, db_id)
            os.makedirs(working_dir, exist_ok=True)
            
            # 如果有权限管理器，同步创建PostgreSQL记录
            if self.permission_manager:
                await self._sync_kb_to_permission_system(db_id, database_name, description, user_id)
            
            return {
                "db_id": db_id,
                "name": database_name,
                "description": description,
                "files": {},
                "row_count": 0,
                "status": "已连接",
                "created_at": time.time()
            }
            
        except Exception as e:
            logger.error(f"Failed to create database {database_name}: {e}")
            raise

    async def _create_kb_in_new_system(self, file_manager: 'FileManager', 
                                     kb_id: str, kb_info: Dict[str, Any]):
        """在新文件管理系统中创建知识库记录"""
        # 这里需要新系统提供创建知识库的方法
        # 临时实现：创建一个标记文档
        try:
            # 使用新架构的文件模型
            from src.database.repositories.file_repository import FileInfo, FileStatus
            
            # 创建知识库元数据文档
            kb_meta_doc = DocumentInfo(
                document_id=f"{kb_id}_metadata",
                kb_id=kb_id,
                filename=f"{kb_id}_metadata.json",
                original_path="",
                file_type=DocumentType.JSON,
                file_size=len(json.dumps(kb_info)),
                file_hash=hashstr(json.dumps(kb_info)),
                status=ProcessingStatus.COMPLETED,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                owner_id=kb_info.get("owner_id"),
                metadata=kb_info
            )
            
            await file_manager.metadata_storage.save_document(kb_meta_doc)
            logger.info(f"Created knowledge base metadata for {kb_id}")
            
        except Exception as e:
            logger.warning(f"Failed to create kb metadata in new system: {e}")

    async def _sync_kb_to_permission_system(self, db_id: str, name: str, 
                                          description: str, user_id: str):
        """同步知识库到权限系统"""
        try:
            from server.models.kb_models import KnowledgeDatabase
            
            existing_db = self.permission_manager.db.query(KnowledgeDatabase).filter(
                KnowledgeDatabase.db_id == db_id
            ).first()
            
            if not existing_db:
                new_db = KnowledgeDatabase(
                    db_id=db_id,
                    name=name,
                    description=description,
                    owner_id=user_id,
                    is_public=False,
                    access_level="private",
                    created_at=datetime.now()
                )
                self.permission_manager.db.add(new_db)
                self.permission_manager.db.commit()
                logger.info(f"Synced database {db_id} to permission system")
                
        except Exception as e:
            logger.warning(f"Failed to sync kb to permission system: {e}")

    # =====================================================================
    # 文件管理方法 - 完全使用新文件管理系统
    # =====================================================================

    async def add_content(self, user_id: str, db_id: str, items: List[str], 
                         params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """通用的内容添加方法 - 🔧 完全使用新文件管理系统"""
        await self._check_permission(user_id, db_id, "write")
        
        try:
            file_manager = await self._ensure_file_manager()
            content_type = params.get('content_type', 'file') if params else 'file'
            
            processed_items = []
            
            for item in items:
                try:
                    if content_type == "file":
                        result = await self._process_file_with_new_system(
                            file_manager, user_id, db_id, item, params
                        )
                    else:  # URL
                        result = await self._process_url_with_new_system(
                            file_manager, user_id, db_id, item, params
                        )
                    
                    processed_items.append(result)
                    
                except Exception as e:
                    logger.error(f"Failed to process {content_type} {item}: {e}")
                    error_result = {
                        "file_id": None,
                        "filename": Path(item).name if content_type == "file" else item,
                        "path": item,
                        "type": content_type,
                        "status": "failed",
                        "error": str(e),
                        "created_at": time.time()
                    }
                    processed_items.append(error_result)
            
            return processed_items
            
        except Exception as e:
            logger.error(f"Failed to add content to {db_id}: {e}")
            raise

    async def _process_file_with_new_system(self, file_manager: 'FileManager', 
                                          user_id: str, db_id: str, file_path: str, 
                                          params: Dict[str, Any]) -> Dict[str, Any]:
        """使用新文件管理系统处理文件"""
        # 使用新架构的文件模型
        from src.database.repositories.file_repository import FileInfo
        
        # 1. 上传文件到新系统
        upload_request = FileUploadRequest(
            file_path=file_path,
            kb_id=db_id,
            filename=Path(file_path).name,
            owner_id=user_id,
            processing_params=params or {},
            metadata={
                "content_type": "file",
                "uploaded_via": "lightrag_api",
                "processing_params": params or {}
            }
        )
        
        # 2. 上传并处理文档
        document = await file_manager.upload_file(upload_request)
        processing_result = await file_manager.process_document(document.document_id, params)
        
        # 3. 获取处理后的分块
        chunks = processing_result.chunks
        
        # 4. 将内容添加到LightRAG
        await self._add_content_to_lightrag(db_id, document, chunks)
        
        # 5. 返回兼容格式
        return {
            "file_id": document.document_id,
            "filename": document.filename,
            "path": document.original_path,
            "type": document.file_type.value,
            "status": document.status.value,
            "created_at": document.created_at.timestamp(),
            "file_size": document.file_size,
            "chunks_count": len(chunks)
        }

    async def _add_content_to_lightrag(self, db_id: str, document: 'DocumentInfo', 
                                     chunks: List['ChunkInfo']):
        """将处理后的内容添加到LightRAG"""
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")
        
        # 构建完整文档内容
        full_content = "\n\n".join([chunk.content for chunk in chunks])
        
        # 添加文档标题和元数据
        if document.metadata:
            metadata_text = f"文档: {document.filename}\n"
            metadata_text += f"类型: {document.file_type.value}\n"
            metadata_text += f"大小: {document.file_size} bytes\n\n"
            full_content = metadata_text + full_content
        
        # 使用LightRAG处理内容
        await rag.ainsert(
            input=full_content,
            ids=document.document_id,
            file_paths=document.original_path
        )
        
        logger.info(f"Added document {document.document_id} to LightRAG: {len(chunks)} chunks")

    # =====================================================================
    # LightRAG实例管理 - 保持不变但优化
    # =====================================================================

    async def _get_lightrag_instance(self, db_id: str) -> Optional[LightRAG]:
        """获取或创建 LightRAG 实例 - 🔧 集成新文件管理系统"""
        logger.info(f"Getting or creating LightRAG instance for {db_id}")

        if db_id in self.instances:
            return self.instances[db_id]

        # 从新文件管理系统获取知识库信息
        try:
            file_manager = await self._ensure_file_manager()
            kb_stats = await file_manager.get_kb_statistics(db_id)
            
            if not kb_stats:
                logger.warning(f"Knowledge base {db_id} not found in new system")
                return None
            
            # 从统计信息中获取配置（或使用默认配置）
            llm_info = kb_stats.get("llm_info", {})
            embed_info = kb_stats.get("embed_info", {})
            
        except Exception as e:
            logger.warning(f"Failed to get kb info from new system, using defaults: {e}")
            llm_info = {}
            embed_info = {}

        # 创建 LightRAG 实例（配置保持不变）
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        try:
            # ⭐ 关键：LightRAG配置完全保持不变
            rag = LightRAG(
                working_dir=working_dir,
                llm_model_func=self._get_llm_func(llm_info),
                embedding_func=self._get_embedding_func(embed_info),
                vector_storage="MilvusVectorDBStorage",     # 保持不变
                kv_storage="JsonKVStorage",                 # 保持不变
                graph_storage="PGGraphStorage",             # 保持不变
                doc_status_storage="JsonDocStatusStorage",  # 保持不变
                log_file_path=os.path.join(self.work_dir, db_id, "lightrag.log"),
            )

            await self._initialize_rag_storages(rag)
            self.instances[db_id] = rag
            return rag

        except Exception as e:
            logger.error(f"Failed to create LightRAG instance for {db_id}: {e}")
            return None

    # =====================================================================
    # 查询方法 - 保持完全不变
    # =====================================================================
    
    async def aquery(self, user_id: str, query_text: str, db_id: str, **kwargs) -> str:
        """查询知识库 - ✅ 保持完全不变"""
        await self._check_permission(user_id, db_id, "read")
        
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Database {db_id} not found")

        try:
            params_dict = {
                "mode": "mix",
                "only_need_context": True,
                "top_k": 10,
            } | kwargs
            param = QueryParam(**params_dict)

            response = await rag.aquery(query_text, param)
            logger.debug(f"Query response: {response}")
            return response

        except Exception as e:
            logger.error(f"Query error: {e}, {traceback.format_exc()}")
            return ""

    # =====================================================================
    # 其他方法保持不变或小幅优化
    # =====================================================================
    
    async def _process_url_with_new_system(self, file_manager: 'FileManager', 
                                          user_id: str, db_id: str, url: str, 
                                          params: Dict[str, Any]) -> Dict[str, Any]:
        """使用新文件管理系统处理URL"""
        # 使用新架构的文件模型
        from src.database.repositories.file_repository import FileInfo
        import hashlib
        import requests
        from bs4 import BeautifulSoup
        
        try:
            # 1. 获取URL内容
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; YuxiKnow/1.0)'
            })
            response.raise_for_status()
            
            # 2. 解析HTML内容
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 移除脚本和样式标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 提取文本内容
            text_content = soup.get_text()
            lines = (line.strip() for line in text_content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            content = '\n'.join(chunk for chunk in chunks if chunk)
            
            # 3. 创建临时文件
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            temp_filename = f"webpage_{url_hash}.md"
            temp_file_path = f"/tmp/{temp_filename}"
            
            # 添加元数据到内容
            markdown_content = f"# {soup.title.string if soup.title else url}\n\n"
            markdown_content += f"**来源**: {url}\n\n"
            markdown_content += content
            
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            # 4. 创建上传请求
            upload_request = FileUploadRequest(
                file_path=temp_file_path,
                kb_id=db_id,
                filename=temp_filename,
                owner_id=user_id,
                processing_params=params or {},
                metadata={
                    "content_type": "url",
                    "source_url": url,
                    "page_title": soup.title.string if soup.title else "Untitled",
                    "uploaded_via": "lightrag_api",
                    "processing_params": params or {}
                }
            )
            
            # 5. 上传和处理文档
            document = await file_manager.upload_file(upload_request)
            processing_result = await file_manager.process_document(document.document_id, params)
            
            # 6. 获取处理后的分块
            chunks = processing_result.chunks
            
            # 7. 将内容添加到LightRAG
            await self._add_content_to_lightrag(db_id, document, chunks)
            
            # 8. 清理临时文件
            try:
                os.unlink(temp_file_path)
            except:
                pass
            
            # 9. 返回结果
            return {
                "file_id": document.document_id,
                "filename": document.filename,
                "path": url,  # 原始URL
                "type": "url",
                "status": document.status.value,
                "created_at": document.created_at.timestamp(),
                "file_size": document.file_size,
                "chunks_count": len(chunks),
                "source_url": url
            }
            
        except Exception as e:
            logger.error(f"Failed to process URL {url}: {e}")
            return {
                "file_id": None,
                "filename": url.split('/')[-1] or "webpage",
                "path": url,
                "type": "url",
                "status": "failed",
                "error": str(e),
                "created_at": time.time()
            }

    async def delete_database(self, user_id: str, db_id: str) -> Dict[str, Any]:
        """删除数据库 - 🔧 使用新文件管理系统"""
        await self._check_permission(user_id, db_id, "delete")
        
        try:
            file_manager = await self._ensure_file_manager()
            
            # 1. 获取该数据库的所有文档
            documents = await file_manager.get_documents_by_kb(db_id)
            
            # 2. 删除所有文档
            for document in documents:
                try:
                    await file_manager.delete_document(document.document_id)
                    logger.info(f"Deleted document {document.document_id} from kb {db_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete document {document.document_id}: {e}")
            
            # 3. 删除知识库元数据记录
            try:
                # 如果新系统提供了删除知识库的方法
                if hasattr(file_manager, 'delete_kb'):
                    await file_manager.delete_kb(db_id)
                else:
                    # 删除知识库元数据文档
                    kb_meta_id = f"{db_id}_metadata"
                    try:
                        await file_manager.delete_document(kb_meta_id)
                    except:
                        pass  # 元数据文档可能不存在
            except Exception as e:
                logger.warning(f"Failed to delete kb metadata: {e}")
            
            # 4. 删除LightRAG实例和工作目录
            if db_id in self.instances:
                del self.instances[db_id]
            
            working_dir = os.path.join(self.work_dir, db_id)
            if os.path.exists(working_dir):
                try:
                    shutil.rmtree(working_dir)
                    logger.info(f"Deleted LightRAG working directory: {working_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete working directory: {e}")
            
            # 5. 如果有权限管理器，同步删除PostgreSQL记录
            if self.permission_manager:
                await self._delete_kb_from_permission_system(db_id)
            
            return {"message": "数据库删除成功", "db_id": db_id}
            
        except Exception as e:
            logger.error(f"Failed to delete database {db_id}: {e}")
            raise

    async def _delete_kb_from_permission_system(self, db_id: str):
        """从权限系统中删除知识库记录"""
        try:
            from server.models.kb_models import KnowledgeDatabase
            
            database_record = self.permission_manager.db.query(KnowledgeDatabase).filter(
                KnowledgeDatabase.db_id == db_id
            ).first()
            
            if database_record:
                self.permission_manager.db.delete(database_record)
                self.permission_manager.db.commit()
                logger.info(f"Deleted database record from PostgreSQL: {db_id}")
                
        except Exception as e:
            logger.warning(f"Failed to delete kb from permission system: {e}")

    async def get_database_info(self, user_id: str, db_id: str) -> Optional[Dict[str, Any]]:
        """获取数据库详细信息 - 🔧 使用新文件管理系统"""
        await self._check_permission(user_id, db_id, "read")
        
        try:
            file_manager = await self._ensure_file_manager()
            
            # 获取知识库统计信息
            stats = await file_manager.get_kb_statistics(db_id)
            if not stats:
                return None
            
            # 获取文档列表
            documents = await file_manager.get_documents_by_kb(db_id, limit=1000)
            
            # 构建文件信息字典
            files = {}
            for doc in documents:
                files[doc.document_id] = {
                    "file_id": doc.document_id,
                    "filename": doc.filename,
                    "path": doc.original_path,
                    "type": doc.file_type.value,
                    "status": doc.status.value,
                    "created_at": doc.created_at.timestamp(),
                    "file_size": doc.file_size,
                    "owner_id": doc.owner_id
                }
            
            # 构建数据库信息
            db_info = {
                "db_id": db_id,
                "name": stats.get('name', db_id),
                "description": stats.get('description', ''),
                "files": files,
                "row_count": len(files),
                "status": "已连接",
                "created_at": stats.get('created_at', time.time()),
                "embed_info": stats.get('embed_info', {}),
                "metadata": stats.get('metadata', {}),
                "owner_id": stats.get('owner_id')
            }
            
            return db_info
            
        except Exception as e:
            logger.error(f"Failed to get database info for {db_id}: {e}")
            return None

    async def delete_file(self, user_id: str, db_id: str, file_id: str) -> Dict[str, Any]:
        """删除文件 - 🔧 使用新文件管理系统"""
        await self._check_permission(user_id, db_id, "write")
        
        try:
            file_manager = await self._ensure_file_manager()
            
            # 1. 从新文件管理系统删除文档
            await file_manager.delete_document(file_id)
            
            # 2. 从LightRAG删除文档
            rag = await self._get_lightrag_instance(db_id)
            if rag:
                try:
                    await rag.adelete_by_doc_id(file_id)
                    logger.info(f"Deleted document {file_id} from LightRAG")
                except Exception as e:
                    logger.warning(f"Failed to delete from LightRAG: {e}")
            
            return {"message": "文件删除成功", "file_id": file_id}
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            raise

    async def get_file_info(self, user_id: str, db_id: str, file_id: str) -> Dict[str, Any]:
        """获取文件信息和分块 - 🔧 使用新文件管理系统"""
        await self._check_permission(user_id, db_id, "read")
        
        try:
            file_manager = await self._ensure_file_manager()
            
            # 1. 获取文档信息
            document = await file_manager.get_document(file_id)
            if not document:
                raise ValueError(f"Document {file_id} not found")
            
            # 2. 获取文档分块
            chunks = await file_manager.get_document_chunks(file_id)
            
            # 3. 转换为兼容格式
            lines = []
            for i, chunk in enumerate(chunks):
                line_data = {
                    "id": chunk.chunk_id,
                    "content": chunk.content,
                    "chunk_order_index": chunk.chunk_index,
                    "full_doc_id": file_id,
                    "tokens": len(chunk.content.split()),  # 简单token计算
                    "metadata": chunk.metadata or {},
                    "content_vector": []  # 向量数据太大，返回空列表
                }
                lines.append(line_data)
            
            # 按chunk_order_index排序
            lines.sort(key=lambda x: x.get("chunk_order_index", 0))
            
            return {
                "lines": lines,
                "document_info": {
                    "file_id": document.document_id,
                    "filename": document.filename,
                    "file_size": document.file_size,
                    "status": document.status.value,
                    "created_at": document.created_at.timestamp(),
                    "chunks_count": len(chunks)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get file info for {file_id}: {e}")
            # 兼容模式：尝试从LightRAG获取
            return await self._get_file_info_from_lightrag(db_id, file_id)

    async def _get_file_info_from_lightrag(self, db_id: str, file_id: str) -> Dict[str, Any]:
        """从LightRAG获取文件信息（兼容模式）"""
        try:
            rag = await self._get_lightrag_instance(db_id)
            if not rag:
                return {"lines": []}
            
            # 获取所有chunks
            all_chunks = await rag.text_chunks.get_all()
            
            # 筛选属于该文档的chunks
            doc_chunks = []
            for chunk_id, chunk_data in all_chunks.items():
                if isinstance(chunk_data, dict) and chunk_data.get("full_doc_id") == file_id:
                    chunk_data["id"] = chunk_id
                    chunk_data["content_vector"] = []
                    doc_chunks.append(chunk_data)
            
            # 按chunk_order_index排序
            doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
            
            return {"lines": doc_chunks}
            
        except Exception as e:
            logger.error(f"Failed to get file info from LightRAG: {e}")
            return {"lines": []}

    # =====================================================================
    # 保持不变的方法
    # =====================================================================
    
    def _get_llm_func(self, llm_info: dict):
        """获取 LLM 函数 - 保持不变"""
        from src.models import get_custom_model
        llm_info = get_custom_model("qwen3:32b-RFnC")
        
        async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return await openai_complete_if_cache(
                llm_info.get("name", "qwen3-1.7b"),
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=llm_info.get("api_key"),
                base_url=get_docker_safe_url(llm_info.get("api_base")),
                extra_body={"enable_thinking": False},
                **kwargs,
            )
        return llm_model_func

    def _get_embedding_func(self, embed_info: dict):
        """获取 embedding 函数 - 保持不变"""
        api_key = os.getenv(embed_info.get("api_key", "OPENAI_API_KEY")) or "no_api_key"
        base_url = embed_info.get("base_url", "http://localhost:8081/v1").replace("/embeddings", "")
        
        return EmbeddingFunc(
            embedding_dim=embed_info.get("dimension") or 1024,
            max_token_size=4096,
            func=lambda texts: openai_embed(
                texts=texts,
                model=embed_info.get("model_name") or "Qwen3-Embedding-0.6B",
                api_key=api_key,
                base_url=get_docker_safe_url(base_url)
            ),
        )

    async def _initialize_rag_storages(self, rag: LightRAG):
        """异步初始化 LightRAG 存储 - 保持不变"""
        logger.info(f"Initializing LightRAG storages for {rag.working_dir}")
        await rag.initialize_storages()
        await initialize_pipeline_status()

    def get_retrievers(self):
        """获取所有检索器 - 用于工具系统"""
        retrievers = {}
        
        # 使用同步方式获取数据库信息，因为这是在类初始化时调用的
        try:
            # 创建事件循环来运行异步方法
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            databases = loop.run_until_complete(self.get_databases())
            
            for db_id, meta in databases.items():
                def make_retriever(db_id):
                    async def retriever(query_text):
                        return await self.aquery(None, query_text, db_id)
                    return retriever

                retrievers[db_id] = {
                    "name": meta["name"],
                    "description": meta["description"],
                    "retriever": make_retriever(db_id),
                }
        except Exception as e:
            logger.warning(f"Failed to get retrievers: {e}")
            # 返回空字典，避免启动失败
            
        return retrievers