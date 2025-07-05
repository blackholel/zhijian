import os
import json
import time
import traceback
import shutil
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, setup_logger
from lightrag.kg.shared_storage import initialize_pipeline_status

from src import config
from src.utils import logger, hashstr, get_docker_safe_url
from src.plugins import ocr
# 延迟导入，避免循环依赖
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from server.auth.permission_framework import PermissionEngine

work_dir = os.path.join(config.save_dir, "lightrag_data")
log_dir = os.path.join(work_dir, "logs", "lightrag")
setup_logger("lightrag", log_file_path=os.path.join(log_dir, f"lightrag_{datetime.now().strftime('%Y-%m-%d')}.log"))

class LightRagBasedKB:
    """基于 LightRAG 的知识库管理类 - 集成新权限框架"""

    def __init__(self) -> None:
        # 存储 LightRAG 实例映射 {db_id: LightRAG}
        self.instances: dict[str, LightRAG] = {}
        # 数据库元信息存储 {db_id: metadata}
        self.databases_meta: dict[str, dict] = {}
        # 文件信息存储 {file_id: file_info}
        self.files_meta: dict[str, dict] = {}
        # 工作目录
        self.work_dir = os.path.join(config.save_dir, "lightrag_data")
        os.makedirs(self.work_dir, exist_ok=True)
        
        # 权限管理器（可选，用于细粒度权限控制）
        self.permission_manager = None

        # 加载已有的元数据
        self._load_metadata()

        logger.info("LightRagBasedKB initialized with new permission framework")

    async def _check_permission(self, user_id: str, db_id: Optional[str], permission: str):
        """权限检查方法 - 使用新权限框架"""
        try:
            from server.auth.permission_framework import (
                PermissionEngine, KnowledgeBaseResource, Permission as PermEnum
            )
            
            # 获取权限引擎
            engine = PermissionEngine.get_instance()
            
            # 创建资源（如果有db_id）
            resource = None
            if db_id:
                resource = KnowledgeBaseResource(db_id)
            
            # 转换权限枚举
            perm_enum = None
            if permission == "read":
                perm_enum = PermEnum.READ
            elif permission == "write":
                perm_enum = PermEnum.WRITE
            elif permission == "create":
                perm_enum = PermEnum.CREATE
            elif permission == "delete":
                perm_enum = PermEnum.DELETE
            elif permission == "admin":
                perm_enum = PermEnum.ADMIN
            else:
                perm_enum = PermEnum.READ  # 默认为读权限
            
            # 执行权限检查 - 使用用户ID进行检查
            has_permission = await engine.check_permission_simple(user_id, resource, perm_enum)
            
            if not has_permission:
                resource_desc = f"知识库 {db_id}" if db_id else "系统"
                raise PermissionError(f"用户 {user_id} 没有权限对{resource_desc}执行 {permission} 操作")
            
            return True
            
        except ImportError:
            logger.warning("New permission framework not available, skipping permission check")
            return True  # 兼容模式
        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            raise

    def _load_metadata(self):
        """加载元数据"""
        meta_file = os.path.join(self.work_dir, "metadata.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, encoding='utf-8') as f:
                    data = json.load(f)
                    self.databases_meta = data.get("databases", {})
                    self.files_meta = data.get("files", {})
                logger.info(f"Loaded metadata for {len(self.databases_meta)} databases")
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")

    def _save_metadata(self):
        """保存元数据"""
        # 确保工作目录存在
        os.makedirs(self.work_dir, exist_ok=True)

        meta_file = os.path.join(self.work_dir, "metadata.json")
        try:
            data = {
                "databases": self.databases_meta,
                "files": self.files_meta
            }
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    async def _get_lightrag_instance(self, db_id: str) -> LightRAG | None:
        """获取或创建 LightRAG 实例"""
        logger.info(f"Getting or creating LightRAG instance for {db_id}")

        if db_id in self.instances:
            return self.instances[db_id]

        if db_id not in self.databases_meta:
            return None

        llm_info = self.databases_meta[db_id].get("llm_info", {})
        embed_info = self.databases_meta[db_id].get("embed_info", {})
        logger.info(f"LLM info: {llm_info}")
        logger.info(f"Embed info: {embed_info}")

        # 创建 LightRAG 实例
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        try:
            # 使用配置的 LLM 和 embedding 函数
            rag = LightRAG(
                working_dir=working_dir,
                llm_model_func=self._get_llm_func(llm_info),
                embedding_func=self._get_embedding_func(embed_info),
                vector_storage="MilvusVectorDBStorage",
                kv_storage="JsonKVStorage",
                graph_storage="PGGraphStorage",
                doc_status_storage="JsonDocStatusStorage",
                log_file_path=os.path.join(self.work_dir, db_id, "lightrag.log"),
            )

            # 异步初始化存储
            await self._initialize_rag_storages(rag)

            self.instances[db_id] = rag
            return rag

        except Exception as e:
            logger.error(f"Failed to create LightRAG instance for {db_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def _initialize_rag_storages(self, rag: LightRAG):
        """异步初始化 LightRAG 存储"""
        logger.info(f"Initializing LightRAG storages for {rag.working_dir}")
        await rag.initialize_storages()
        await initialize_pipeline_status()

    def _get_llm_func(self, llm_info: dict):
        """获取 LLM 函数"""
        # llm_info = llm_info | {
        #     "model_name": "qwen3-1.7b",
        #     "provider": "custom"
        # }
        # provider_info = config.model_names[llm_info.get("provider")]
        # api_key = os.getenv(provider_info.get("env")[0] or "OPENAI_API_KEY") or "no_api_key"
        # base_url = get_docker_safe_url(provider_info.get("base_url", "http://localhost:8081/v1"))
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
        """获取 embedding 函数"""
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

    async def _process_file_to_markdown(self, file_path: str, params: dict | None = None) -> str:
        """将不同类型的文件转换为 markdown 格式"""
        file_path_obj = Path(file_path)
        file_ext = file_path_obj.suffix.lower()

        if file_ext == '.pdf':
            # 使用 OCR 处理 PDF
            from src.core.indexing import parse_pdf_async
            text = await parse_pdf_async(str(file_path_obj), params=params)
            return f"Using OCR to process {file_path_obj.name}\n\n{text}"

        elif file_ext in ['.txt', '.md']:
            # 直接读取文本文件
            with open(file_path_obj, encoding='utf-8') as f:
                content = f.read()
            return f"# {file_path_obj.name}\n\n{content}"

        elif file_ext in ['.doc', '.docx']:
            # 处理 Word 文档

            from docx import Document  # type: ignore
            doc = Document(file_path_obj)
            text = '\n'.join([para.text for para in doc.paragraphs])
            return f"# {file_path_obj.name}\n\n{text}"

        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            # 使用 OCR 处理图片
            text = ocr.process_image(str(file_path_obj))
            return f"# {file_path_obj.name}\n\n{text}"

        else:
            # 尝试作为文本文件读取
            import textract  # type: ignore
            text = textract.process(file_path_obj)
            return f"# {file_path_obj.name}\n\n{text}"

    async def _process_url_to_markdown(self, url: str, params: dict | None = None) -> str:
        """将 URL 转换为 markdown 格式"""
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(url, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')
        text_content = soup.get_text()
        return f"# {url}\n\n{text_content}"

    # =============================================================================
    # data_router.py 中使用的核心方法
    # =============================================================================

    async def get_databases(self, user_id: Optional[str] = None):
        """获取用户可访问的数据库信息 - data_router.py 使用"""
        if not user_id or not self.permission_manager:
            # 兼容模式：返回所有数据库
            return self._get_all_databases()
        
        # 获取用户可访问的知识库ID列表
        accessible_db_ids = await self.permission_manager.filter_accessible_databases(user_id, "read")
        
        databases = []
        for db_id in accessible_db_ids:
            if db_id in self.databases_meta:
                meta = self.databases_meta[db_id]
                db_dict = meta.copy()
                db_dict["db_id"] = db_id

                # 获取文件信息
                db_files = {}
                for file_id, file_info in self.files_meta.items():
                    if file_info.get("database_id") == db_id:
                        db_files[file_id] = {
                            "file_id": file_id,
                            "filename": file_info.get("filename", ""),
                            "path": file_info.get("path", ""),
                            "type": file_info.get("file_type", ""),
                            "status": file_info.get("status", "done"),
                            "created_at": file_info.get("created_at", time.time())
                        }

                db_dict["files"] = db_files
                db_dict["row_count"] = len(db_files)
                db_dict["status"] = "已连接"
                databases.append(db_dict)

        return {"databases": databases}
    
    def _get_all_databases(self):
        """获取所有数据库信息（兼容模式）"""
        databases = []
        for db_id, meta in self.databases_meta.items():
            db_dict = meta.copy()
            db_dict["db_id"] = db_id

            # 获取文件信息
            db_files = {}
            for file_id, file_info in self.files_meta.items():
                if file_info.get("database_id") == db_id:
                    db_files[file_id] = {
                        "file_id": file_id,
                        "filename": file_info.get("filename", ""),
                        "path": file_info.get("path", ""),
                        "type": file_info.get("file_type", ""),
                        "status": file_info.get("status", "done"),
                        "created_at": file_info.get("created_at", time.time())
                    }

            db_dict["files"] = db_files
            db_dict["row_count"] = len(db_files)
            db_dict["status"] = "已连接"
            databases.append(db_dict)

        return {"databases": databases}

    async def create_database(self, user_id: str, database_name, description, embed_info: dict | None = None, **kwargs):
        """创建数据库 - data_router.py 使用（集成权限控制）"""
        # 检查创建权限
        await self._check_permission(user_id, None, "create")
        
        db_id = f"kb_{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        self.databases_meta[db_id] = {
            "name": database_name,
            "description": description,
            "embed_info": embed_info,
            "metadata": kwargs,
            "created_at": datetime.now().isoformat(),
            "owner_id": user_id
        }
        self._save_metadata()

        # 创建工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)
        
        # 在PostgreSQL中创建数据库记录
        if self.permission_manager:
            from server.models.kb_models import KnowledgeDatabase
            
            # 检查是否已存在
            existing_db = self.permission_manager.db.query(KnowledgeDatabase).filter(
                KnowledgeDatabase.db_id == db_id
            ).first()
            
            if not existing_db:
                # 创建新的数据库记录
                new_db = KnowledgeDatabase(
                    db_id=db_id,
                    name=database_name,
                    description=description,
                    owner_id=user_id,
                    is_public=False,
                    access_level="private",
                    created_at=datetime.now()
                )
                self.permission_manager.db.add(new_db)
                self.permission_manager.db.commit()
                logger.info(f"Created database record in PostgreSQL: {db_id}")
            else:
                # 更新现有记录的所有者
                existing_db.owner_id = user_id
                self.permission_manager.db.commit()
                logger.info(f"Updated database owner in PostgreSQL: {db_id}")

        # 返回数据库信息
        db_dict = self.databases_meta[db_id].copy()
        db_dict["db_id"] = db_id
        db_dict["files"] = {}

        return db_dict
    
    def create_database_compat(self, database_name, description, embed_info: dict | None = None, **kwargs):
        """创建数据库 - 兼容原有接口"""
        db_id = f"kb_{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        self.databases_meta[db_id] = {
            "name": database_name,
            "description": description,
            "embed_info": embed_info,
            "metadata": kwargs,
            "created_at": datetime.now().isoformat()
        }
        self._save_metadata()

        # 创建工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        # 返回数据库信息
        db_dict = self.databases_meta[db_id].copy()
        db_dict["db_id"] = db_id
        db_dict["files"] = {}

        return db_dict

    async def delete_database(self, user_id: str, db_id: str):
        """删除数据库 - data_router.py 使用（集成权限控制）"""
        # 检查删除权限
        await self._check_permission(user_id, db_id, "delete")
        
        if db_id in self.databases_meta:
            # 删除相关文件记录
            files_to_delete = [fid for fid, finfo in self.files_meta.items()
                             if finfo.get("database_id") == db_id]
            for file_id in files_to_delete:
                del self.files_meta[file_id]

            # 删除数据库记录
            del self.databases_meta[db_id]

            # 删除 LightRAG 实例
            if db_id in self.instances:
                del self.instances[db_id]

            self._save_metadata()
            
        # 删除PostgreSQL中的数据库记录
        if self.permission_manager:
            from server.models.kb_models import KnowledgeDatabase
            
            database_record = self.permission_manager.db.query(KnowledgeDatabase).filter(
                KnowledgeDatabase.db_id == db_id
            ).first()
            
            if database_record:
                self.permission_manager.db.delete(database_record)
                self.permission_manager.db.commit()
                logger.info(f"Deleted database record from PostgreSQL: {db_id}")

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        if os.path.exists(working_dir):
            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}
    
    def delete_database_compat(self, db_id):
        """删除数据库 - 兼容原有接口"""
        if db_id in self.databases_meta:
            # 删除相关文件记录
            files_to_delete = [fid for fid, finfo in self.files_meta.items()
                             if finfo.get("database_id") == db_id]
            for file_id in files_to_delete:
                del self.files_meta[file_id]

            # 删除数据库记录
            del self.databases_meta[db_id]

            # 删除 LightRAG 实例
            if db_id in self.instances:
                del self.instances[db_id]

            self._save_metadata()

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        if os.path.exists(working_dir):
            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}

    async def add_content(self, user_id: str, db_id, items, params: dict | None = None):
        """通用的内容添加方法 - 支持文件和URL（集成权限控制）"""
        # 检查上传权限
        await self._check_permission(user_id, db_id, "write")
        
        processed_items = await self._add_content_internal(db_id, items, params)
        
        # 记录上传者信息
        if self.permission_manager:
            await self.permission_manager.record_file_upload(user_id, processed_items)
        
        return processed_items
    
    async def _add_content_internal(self, db_id, items, params: dict | None = None):
        """通用的内容添加方法 - 支持文件和URL（内部实现）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        content_type = params.get('content_type', 'file') if params else 'file'

        processed_items_info = []

        for item in items:
            # 根据内容类型生成不同的ID和文件名
            if content_type == "file":
                file_path = Path(item)
                file_id = f"file_{hashstr(str(file_path) + str(time.time()), 6)}"
                file_type = file_path.suffix.lower().replace(".", "")
                filename = file_path.name
                item_path = str(file_path)
            else:  # URL
                file_id = f"url_{hashstr(item + str(time.time()), 6)}"
                file_type = "url"
                filename = f"webpage_{hashstr(item, 6)}.md"
                item_path = item

            # 添加文件记录
            file_record = {
                "database_id": db_id,
                "filename": filename,
                "path": item_path,
                "file_type": file_type,
                "status": "processing",
                "created_at": time.time()
            }
            self.files_meta[file_id] = file_record
            self._save_metadata()

            # 添加 file_id 到返回数据
            file_record = file_record.copy()
            file_record["file_id"] = file_id

            try:
                # 根据内容类型处理内容
                if content_type == "file":
                    markdown_content = await self._process_file_to_markdown(item, params=params)
                    logger.info(f"Markdown content: {markdown_content[:100].replace('\n', ' ')}...")
                else:  # URL
                    markdown_content = await self._process_url_to_markdown(item, params=params)

                # 使用 LightRAG 插入内容
                await rag.ainsert(
                    input=markdown_content,
                    ids=file_id,
                    file_paths=item_path
                )

                logger.info(f"Inserted {content_type} {item} into LightRAG. Done.")

                # 更新状态为完成
                self.files_meta[file_id]["status"] = "done"
                self._save_metadata()
                file_record['status'] = "done"

            except Exception as e:
                logger.error(f"处理{content_type} {item} 失败: {e}, {traceback.format_exc()}")
                self.files_meta[file_id]["status"] = "failed"
                self._save_metadata()
                file_record['status'] = "failed"

            processed_items_info.append(file_record)

        return processed_items_info

    async def get_database_info(self, user_id: str, db_id: str):
        """获取数据库详细信息 - data_router.py 使用（集成权限控制）"""
        # 检查读取权限
        await self._check_permission(user_id, db_id, "read")
        
        if db_id not in self.databases_meta:
            return None

        meta = self.databases_meta[db_id].copy()
        meta["db_id"] = db_id

        # 获取文件信息
        db_files = {}
        for file_id, file_info in self.files_meta.items():
            if file_info.get("database_id") == db_id:
                db_files[file_id] = {
                    "file_id": file_id,
                    "filename": file_info.get("filename", ""),
                    "path": file_info.get("path", ""),
                    "type": file_info.get("file_type", ""),
                    "status": file_info.get("status", "done"),
                    "created_at": file_info.get("created_at", time.time())
                }

        meta["files"] = db_files
        meta["row_count"] = len(db_files)
        meta["status"] = "已连接"
        return meta
    
    def get_database_info_compat(self, db_id):
        """获取数据库详细信息 - 兼容原有接口"""
        if db_id not in self.databases_meta:
            return None

        meta = self.databases_meta[db_id].copy()
        meta["db_id"] = db_id

        # 获取文件信息
        db_files = {}
        for file_id, file_info in self.files_meta.items():
            if file_info.get("database_id") == db_id:
                db_files[file_id] = {
                    "file_id": file_id,
                    "filename": file_info.get("filename", ""),
                    "path": file_info.get("path", ""),
                    "type": file_info.get("file_type", ""),
                    "status": file_info.get("status", "done"),
                    "created_at": file_info.get("created_at", time.time())
                }

        meta["files"] = db_files
        meta["row_count"] = len(db_files)
        meta["status"] = "已连接"
        return meta

    async def delete_file(self, user_id: str, db_id, file_id):
        """删除文件 - data_router.py 使用（集成权限控制）"""
        # 检查删除权限
        await self._check_permission(user_id, db_id, "write")
        
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 使用 LightRAG 删除文档
                await rag.adelete_by_doc_id(file_id)
            except Exception as e:
                logger.error(f"Error deleting file {file_id} from LightRAG: {e}")

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()
    
    async def delete_file_compat(self, db_id, file_id):
        """删除文件 - 兼容原有接口"""
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 使用 LightRAG 删除文档
                await rag.adelete_by_doc_id(file_id)
            except Exception as e:
                logger.error(f"Error deleting file {file_id} from LightRAG: {e}")

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()

    async def get_file_info(self, user_id: str, db_id, file_id):
        """获取文件信息和其 chunks - data_router.py 使用（集成权限控制）"""
        # 检查读取权限
        await self._check_permission(user_id, db_id, "read")
        
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 LightRAG 获取 chunks
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 获取文档的所有 chunks
                assert hasattr(rag.text_chunks, 'get_all'), "text_chunks does not have get_all method"
                all_chunks = await rag.text_chunks.get_all() # type: ignore

                # 筛选属于该文档的 chunks
                doc_chunks = []
                for chunk_id, chunk_data in all_chunks.items():
                    if isinstance(chunk_data, dict) and chunk_data.get("full_doc_id") == file_id:
                        chunk_data["id"] = chunk_id
                        chunk_data["content_vector"] = []
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                return {"lines": doc_chunks}

            except Exception as e:
                logger.error(f"Error getting chunks for file {file_id}: {e}")

        return {"lines": []}
    
    async def get_file_info_compat(self, db_id, file_id):
        """获取文件信息和其 chunks - 兼容原有接口"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 LightRAG 获取 chunks
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 获取文档的所有 chunks
                assert hasattr(rag.text_chunks, 'get_all'), "text_chunks does not have get_all method"
                all_chunks = await rag.text_chunks.get_all() # type: ignore

                # 筛选属于该文档的 chunks
                doc_chunks = []
                for chunk_id, chunk_data in all_chunks.items():
                    if isinstance(chunk_data, dict) and chunk_data.get("full_doc_id") == file_id:
                        chunk_data["id"] = chunk_id
                        chunk_data["content_vector"] = []
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                return {"lines": doc_chunks}

            except Exception as e:
                logger.error(f"Error getting chunks for file {file_id}: {e}")

        return {"lines": []}

    def get_db_upload_path(self, db_id=None):
        """获取数据库上传路径 - data_router.py 使用"""
        if db_id:
            uploads_folder = os.path.join(self.work_dir, db_id, "uploads")
            os.makedirs(uploads_folder, exist_ok=True)
            return uploads_folder

        general_uploads = os.path.join(self.work_dir, "uploads")
        os.makedirs(general_uploads, exist_ok=True)
        return general_uploads

    async def update_database(self, user_id: str, db_id, name, description):
        """更新数据库 - data_router.py 使用（集成权限控制）"""
        # 检查更新权限
        await self._check_permission(user_id, db_id, "admin")
        
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        self.databases_meta[db_id]["name"] = name
        self.databases_meta[db_id]["description"] = description
        self._save_metadata()

        # 返回更新后的数据库信息
        return await self.get_database_info(user_id, db_id)
    
    def update_database_compat(self, db_id, name, description):
        """更新数据库 - 兼容原有接口"""
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        self.databases_meta[db_id]["name"] = name
        self.databases_meta[db_id]["description"] = description
        self._save_metadata()

        # 返回更新后的数据库信息
        return self.get_database_info_compat(db_id)

    # =============================================================================
    # 为了系统兼容性需要的其他方法
    # =============================================================================

    def query(self, query_text, db_id, **kwargs):
        logger.warning("query is deprecated, use aquery instead")
        return asyncio.run(self.aquery(query_text, db_id, **kwargs))

    async def aquery(self, user_id: str, query_text, db_id, **kwargs):
        """查询知识库 - 用于检索器（集成权限控制）"""
        # 检查查询权限
        await self._check_permission(user_id, db_id, "read")
        
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Database {db_id} not found")

        try:
            # 设置查询参数
            params_dict = {
                "mode": "mix",
                "only_need_context": True,
                "top_k": 10,
            } | kwargs
            param = QueryParam(**params_dict)

            # 执行查询
            response = await rag.aquery(query_text, param)
            logger.debug(f"Query response: {response}")

            return response

        except Exception as e:
            logger.error(f"Query error: {e}, {traceback.format_exc()}")
            return ""
    
    async def aquery_compat(self, query_text, db_id, **kwargs):
        """查询知识库 - 兼容原有接口"""
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Database {db_id} not found")

        try:
            # 设置查询参数
            params_dict = {
                "mode": "mix",
                "only_need_context": True,
                "top_k": 10,
            } | kwargs
            param = QueryParam(**params_dict)

            # 执行查询
            response = await rag.aquery(query_text, param)
            logger.debug(f"Query response: {response}")

            return response

        except Exception as e:
            logger.error(f"Query error: {e}, {traceback.format_exc()}")
            return ""

    def get_retrievers(self):
        """获取所有检索器 - 用于工具系统"""
        retrievers = {}
        for db_id, meta in self.databases_meta.items():
            def make_retriever(db_id):
                async def retriever(query_text):
                    return await self.aquery(query_text, db_id)
                return retriever

            retrievers[db_id] = {
                "name": meta["name"],
                "description": meta["description"],
                "retriever": make_retriever(db_id),
            }
        return retrievers
