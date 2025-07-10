"""
统一的LightRAG知识库管理系统

集成原有的lightrag_based_kb.py和lightrag_storage_adapter.py功能，
完全使用统一数据库管理系统(/home/xm/Yuxi-Know-main/src/database)
"""

import os
import json
import time
import traceback
import shutil
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import asynccontextmanager

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, setup_logger
from lightrag.kg.shared_storage import initialize_pipeline_status

from src import config
from src.utils import logger, hashstr, get_docker_safe_url
from src.plugins import ocr
from src.database.manager import get_database_manager

# 设置LightRAG日志
work_dir = os.path.join(config.save_dir, "lightrag_data")
log_dir = os.path.join(work_dir, "logs", "lightrag")
setup_logger("lightrag", log_file_path=os.path.join(log_dir, f"lightrag_{datetime.now().strftime('%Y-%m-%d')}.log"))


class UnifiedLightRAGKnowledgeBase:
    """
    统一的LightRAG知识库管理系统
    
    集成了原有的知识库管理和存储适配器功能，
    完全使用统一数据库管理系统
    """

    def __init__(self) -> None:
        # 存储 LightRAG 实例映射 {db_id: LightRAG}
        self.instances: Dict[str, LightRAG] = {}
        # 数据库元信息存储 {db_id: metadata}
        self.databases_meta: Dict[str, Dict] = {}
        # 文件信息存储 {file_id: file_info}
        self.files_meta: Dict[str, Dict] = {}
        # 工作目录
        self.work_dir = os.path.join(config.save_dir, "lightrag_data")
        os.makedirs(self.work_dir, exist_ok=True)

        # 统一数据库管理器
        self.db_manager = get_database_manager()

        # 加载已有的元数据
        self._load_metadata()

        logger.info("UnifiedLightRAGKnowledgeBase initialized")

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

    async def _ensure_database_manager_initialized(self):
        """确保数据库管理器已初始化"""
        if not self.db_manager._initialized:
            await self.db_manager.initialize()

    async def _setup_lightrag_environment(self, db_id: str):
        """
        设置LightRAG运行环境
        
        使用统一数据库管理系统获取配置并设置环境变量
        """
        try:
            await self._ensure_database_manager_initialized()
            
            # 获取各数据库配置
            milvus_config = self.db_manager.get_database_config('milvus')
            neo4j_config = self.db_manager.get_database_config('neo4j')
            redis_config = self.db_manager.get_database_config('redis')
            pg_config = self.db_manager.get_database_config('lightrag_db')
            
            # 设置Milvus环境变量
            os.environ['MILVUS_URI'] = milvus_config['uri']
            os.environ['MILVUS_USER'] = milvus_config['user']
            os.environ['MILVUS_PASSWORD'] = milvus_config['password']
            os.environ['MILVUS_DB_NAME'] = milvus_config['db_name']
            # 设置空的MILVUS_TOKEN以避免认证冲突
            os.environ['MILVUS_TOKEN'] = ''
            
            # 设置Neo4j环境变量
            os.environ['NEO4J_URI'] = neo4j_config['uri']
            os.environ['NEO4J_USERNAME'] = neo4j_config['username']
            os.environ['NEO4J_PASSWORD'] = neo4j_config['password']
            
            # 设置Redis环境变量
            from urllib.parse import quote
            if redis_config['password']:
                encoded_password = quote(redis_config['password'], safe='')
                redis_uri = f"redis://:{encoded_password}@{redis_config['host']}:{redis_config['port']}/{redis_config['db']}"
            else:
                redis_uri = f"redis://{redis_config['host']}:{redis_config['port']}/{redis_config['db']}"
            os.environ['REDIS_URI'] = redis_uri
            
            # 设置PostgreSQL环境变量
            os.environ['POSTGRES_USER'] = pg_config['username']
            os.environ['POSTGRES_PASSWORD'] = pg_config['password']
            os.environ['POSTGRES_DATABASE'] = pg_config['database']
            os.environ['POSTGRES_HOST'] = pg_config['host']
            os.environ['POSTGRES_PORT'] = str(pg_config['port'])
            
            logger.info(f"LightRAG环境变量设置完成 [db_id={db_id}]")
            
        except Exception as e:
            logger.error(f"设置LightRAG环境变量失败 [db_id={db_id}]: {e}")
            raise ValueError(f"无法设置环境变量: {e}")

    async def _get_storage_config(self, db_id: str) -> Dict[str, Any]:
        """
        获取存储类型配置
        
        使用统一数据库管理系统获取存储配置
        """
        try:
            await self._ensure_database_manager_initialized()
            
            # 检查各数据库适配器是否可用
            neo4j_adapter = await self.db_manager.get_neo4j_adapter()
            redis_adapter = await self.db_manager.get_redis_adapter()
            milvus_adapter = await self.db_manager.get_milvus_adapter()
            pg_adapter = await self.db_manager.get_postgresql_adapter('lightrag_db')
            
            # 根据适配器可用性决定存储类型
            config = {
                'graph_storage': 'Neo4JStorage' if neo4j_adapter else 'JsonKVStorage',
                'kv_storage': 'RedisKVStorage' if redis_adapter else 'JsonKVStorage',
                'vector_storage': 'MilvusVectorDBStorage' if milvus_adapter else 'SimpleVectorStorage',
                'doc_status_storage': 'PGDocStatusStorage' if pg_adapter else 'JsonKVStorage'
            }
            
            logger.info(f"存储类型配置获取完成 [db_id={db_id}]: {config}")
            return config
            
        except Exception as e:
            logger.error(f"获取存储配置失败 [db_id={db_id}]: {e}")
            # 返回降级配置
            return {
                'graph_storage': 'JsonKVStorage',
                'kv_storage': 'JsonKVStorage',
                'vector_storage': 'SimpleVectorStorage',
                'doc_status_storage': 'JsonKVStorage'
            }

    async def _get_lightrag_instance(self, db_id: str) -> LightRAG | None:
        """获取或创建 LightRAG 实例"""
        logger.info(f"Getting or creating LightRAG instance for {db_id}")

        if db_id in self.instances:
            return self.instances[db_id]

        if db_id not in self.databases_meta:
            return None

        try:
            # 设置环境变量
            await self._setup_lightrag_environment(db_id)
            
            # 获取存储配置
            storage_config = await self._get_storage_config(db_id)
            
            # 获取模型配置
            llm_info = self.databases_meta[db_id].get("llm_info", {})
            embed_info = self.databases_meta[db_id].get("embed_info", {})
            
            # 创建工作目录
            working_dir = os.path.join(self.work_dir, db_id)
            os.makedirs(working_dir, exist_ok=True)
            
            # 创建LightRAG实例
            rag = LightRAG(
                working_dir=working_dir,
                namespace_prefix=f"kb_{db_id}_",  # 设置知识库级别的命名空间前缀
                llm_model_func=self._get_llm_func(llm_info, db_id=db_id),
                embedding_func=self._get_embedding_func(embed_info, db_id=db_id),
                vector_storage=storage_config['vector_storage'],
                kv_storage=storage_config['kv_storage'],
                graph_storage=storage_config['graph_storage'],
                doc_status_storage=storage_config['doc_status_storage'],
                log_file_path=os.path.join(working_dir, "lightrag.log"),
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

    def _get_llm_func(self, llm_info: dict, db_id: str = None):
        """获取 LLM 函数"""
        from src.core.lightrag_model_adapter import get_lightrag_model_adapter
        
        adapter = get_lightrag_model_adapter()
        return adapter.get_llm_func(llm_config=llm_info, kb_id=db_id)

    def _get_embedding_func(self, embed_info: dict, db_id: str = None):
        """获取 embedding 函数"""
        from src.core.lightrag_model_adapter import get_lightrag_model_adapter
        
        adapter = get_lightrag_model_adapter()
        return adapter.get_embedding_func(embed_config=embed_info, kb_id=db_id)

    async def _process_file_to_markdown(self, file_path: str, params: dict | None = None) -> str:
        """将不同类型的文件转换为 markdown 格式"""
        file_path_obj = Path(file_path)
        file_ext = file_path_obj.suffix.lower()

        if file_ext == '.pdf':
            from src.core.indexing import parse_pdf_async
            text = await parse_pdf_async(str(file_path_obj), params=params)
            return f"Using OCR to process {file_path_obj.name}\n\n{text}"

        elif file_ext in ['.txt', '.md']:
            with open(file_path_obj, encoding='utf-8') as f:
                content = f.read()
            return f"# {file_path_obj.name}\n\n{content}"

        elif file_ext in ['.doc', '.docx']:
            from docx import Document  # type: ignore
            doc = Document(file_path_obj)
            text = '\n'.join([para.text for para in doc.paragraphs])
            return f"# {file_path_obj.name}\n\n{text}"

        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            text = ocr.process_image(str(file_path_obj))
            return f"# {file_path_obj.name}\n\n{text}"

        else:
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
    # 数据库健康检查和监控
    # =============================================================================

    async def health_check(self) -> Dict[str, Any]:
        """统一健康检查"""
        try:
            await self._ensure_database_manager_initialized()
            
            # 使用统一数据库管理器的健康检查
            db_health = await self.db_manager.health_check()
            
            # 添加知识库特定的健康信息
            kb_health = {
                'total_databases': len(self.databases_meta),
                'total_files': len(self.files_meta),
                'active_instances': len(self.instances),
                'work_dir': self.work_dir,
                'metadata_file_exists': os.path.exists(os.path.join(self.work_dir, "metadata.json"))
            }
            
            return {
                'kb_status': 'healthy',
                'knowledge_base': kb_health,
                'database_manager': db_health
            }
            
        except Exception as e:
            return {
                'kb_status': 'error',
                'error': str(e),
                'knowledge_base': {
                    'total_databases': len(self.databases_meta),
                    'total_files': len(self.files_meta),
                    'active_instances': len(self.instances)
                }
            }

    @asynccontextmanager
    async def get_database_adapters(self, db_id: str = None):
        """
        获取数据库适配器的异步上下文管理器
        
        使用统一数据库管理系统获取适配器
        """
        adapters = {}
        try:
            await self._ensure_database_manager_initialized()
            
            # 获取所有适配器
            adapters['neo4j'] = await self.db_manager.get_neo4j_adapter()
            adapters['redis'] = await self.db_manager.get_redis_adapter()
            adapters['milvus'] = await self.db_manager.get_milvus_adapter()
            adapters['postgresql'] = await self.db_manager.get_postgresql_adapter('lightrag_db')
            
            yield adapters
            
        except Exception as e:
            logger.error(f"Error in database adapters context [db_id={db_id}]: {e}")
            raise
        finally:
            # 清理工作（如果需要）
            pass

    # =============================================================================
    # 知识库管理方法 (data_router.py 中使用的核心方法)
    # =============================================================================

    def get_databases(self):
        """获取所有数据库信息"""
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

    def create_database(self, database_name, description, embed_info: dict | None = None, **kwargs):
        """创建数据库"""
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

    def delete_database(self, db_id):
        """删除数据库"""
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

    async def add_content(self, db_id, items, params: dict | None = None):
        """通用的内容添加方法 - 支持文件和URL"""
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

    def get_database_info(self, db_id):
        """获取数据库详细信息"""
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

    async def delete_file(self, db_id, file_id):
        """删除文件"""
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                await rag.adelete_by_doc_id(file_id)
            except Exception as e:
                logger.error(f"Error deleting file {file_id} from LightRAG: {e}")

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()

    async def get_file_info(self, db_id, file_id):
        """获取文件信息和其 chunks"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 LightRAG 获取 chunks
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                assert hasattr(rag.text_chunks, 'get_all'), "text_chunks does not have get_all method"
                all_chunks = await rag.text_chunks.get_all()  # type: ignore

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
        """获取数据库上传路径"""
        if db_id:
            uploads_folder = os.path.join(self.work_dir, db_id, "uploads")
            os.makedirs(uploads_folder, exist_ok=True)
            return uploads_folder

        general_uploads = os.path.join(self.work_dir, "uploads")
        os.makedirs(general_uploads, exist_ok=True)
        return general_uploads

    def update_database(self, db_id, name, description):
        """更新数据库"""
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        self.databases_meta[db_id]["name"] = name
        self.databases_meta[db_id]["description"] = description
        self._save_metadata()

        return self.get_database_info(db_id)

    # =============================================================================
    # 查询和检索方法
    # =============================================================================

    def query(self, query_text, db_id, **kwargs):
        """同步查询方法 (向后兼容)"""
        logger.warning("query is deprecated, use aquery instead")
        return asyncio.run(self.aquery(query_text, db_id, **kwargs))

    async def aquery(self, query_text, db_id, **kwargs):
        """异步查询知识库"""
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
        """获取所有检索器"""
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

    # =============================================================================
    # 上下文管理器支持
    # =============================================================================

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._ensure_database_manager_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        # 清理工作
        try:
            # 清理 LightRAG 实例
            for instance in self.instances.values():
                if hasattr(instance, 'close'):
                    await instance.close()
            self.instances.clear()
            
            # 数据库管理器会自动处理连接清理
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# 全局单例实例
_unified_kb_instance = None


def get_unified_lightrag_kb() -> UnifiedLightRAGKnowledgeBase:
    """获取统一LightRAG知识库管理器单例"""
    global _unified_kb_instance
    if _unified_kb_instance is None:
        _unified_kb_instance = UnifiedLightRAGKnowledgeBase()
    return _unified_kb_instance


# 为了向后兼容，保留原有的接口
def get_lightrag_based_kb():
    """向后兼容：获取LightRAG知识库管理器"""
    return get_unified_lightrag_kb()


# 向后兼容的类别名
LightRagBasedKB = UnifiedLightRAGKnowledgeBase