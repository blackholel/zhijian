# 直接替换实现计划

## 阶段1：改造 lightrag_based_kb.py

### 1.1 初始化方法改造

```python
class LightRagBasedKB:
    """基于 LightRAG 的知识库管理类 - 使用新文件管理系统"""

    def __init__(self) -> None:
        # 保持 LightRAG 实例映射（内存缓存）
        self.instances: dict[str, LightRAG] = {}
        
        # 新增：文件管理器（懒加载）
        self._file_manager: Optional[FileManager] = None
        self._initialized = False
        
        # 工作目录（保持兼容）
        self.work_dir = os.path.join(config.save_dir, "lightrag_data")
        os.makedirs(self.work_dir, exist_ok=True)
        
        # 权限管理器（保持不变）
        self.permission_manager = None
        
        logger.info("LightRagBasedKB initialized with new file management system")

    async def _ensure_initialized(self):
        """确保文件管理器已初始化"""
        if self._initialized:
            return
            
        try:
            from src.file import load_storage_config, FileManager
            config = load_storage_config()
            self._file_manager = await FileManager.create_from_config(config)
            self._initialized = True
            logger.info("File management system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize file management system: {e}")
            raise

    @property
    async def file_manager(self) -> FileManager:
        """获取文件管理器实例"""
        await self._ensure_initialized()
        return self._file_manager
```

### 1.2 数据库管理方法改造

```python
    async def get_databases(self, user_id: Optional[str] = None):
        """获取用户可访问的数据库信息 - 使用新文件管理系统"""
        fm = await self.file_manager
        
        # 从新系统获取所有知识库
        all_kb_stats = {}
        try:
            # 获取所有知识库的统计信息
            # 这里需要新系统提供获取所有知识库的方法
            all_kb_ids = await self._get_all_kb_ids()
            
            for kb_id in all_kb_ids:
                try:
                    stats = await fm.get_kb_statistics(kb_id)
                    if stats:
                        all_kb_stats[kb_id] = stats
                except Exception as e:
                    logger.warning(f"Failed to get stats for kb {kb_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to get knowledge base list: {e}")
            return {"databases": []}
        
        # 权限过滤（如果启用）
        if user_id and self.permission_manager:
            accessible_db_ids = await self.permission_manager.filter_accessible_databases(user_id, "read")
            all_kb_stats = {kb_id: stats for kb_id, stats in all_kb_stats.items() if kb_id in accessible_db_ids}
        
        # 转换为兼容格式
        databases = []
        for kb_id, stats in all_kb_stats.items():
            # 获取知识库详细信息
            kb_info = await self._get_kb_info_from_stats(kb_id, stats)
            databases.append(kb_info)
        
        return {"databases": databases}

    async def _get_kb_info_from_stats(self, kb_id: str, stats: dict) -> dict:
        """从统计信息构建知识库信息"""
        fm = await self.file_manager
        
        # 获取文档列表
        documents = await fm.get_documents_by_kb(kb_id, limit=1000)
        
        # 构建文件信息
        files = {}
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
            "name": stats.get('name', kb_id),  # 从元数据获取
            "description": stats.get('description', ''),
            "files": files,
            "row_count": stats.get('total_documents', 0),
            "status": "已连接",
            "created_at": stats.get('created_at', time.time())
        }
```

### 1.3 文件操作方法改造

```python
    async def add_content(self, user_id: str, db_id: str, items: list, params: dict = None):
        """添加内容 - 完全使用新文件管理系统"""
        # 权限检查
        await self._check_permission(user_id, db_id, "write")
        
        fm = await self.file_manager
        content_type = params.get('content_type', 'file') if params else 'file'
        
        processed_items = []
        
        for item in items:
            try:
                if content_type == "file":
                    # 使用新文件管理系统上传文件
                    from src.file import FileUploadRequest
                    
                    upload_request = FileUploadRequest(
                        file_path=item,
                        kb_id=db_id,
                        filename=Path(item).name,
                        owner_id=user_id,
                        processing_params=params or {},
                        metadata={
                            "content_type": content_type,
                            "uploaded_via": "lightrag_api"
                        }
                    )
                    
                    # 上传并处理文档
                    document = await fm.upload_file(upload_request)
                    result = await fm.process_document(document.document_id, params)
                    
                    # 获取分块信息
                    chunks = await fm.get_document_chunks(document.document_id)
                    
                    # 将分块内容添加到 LightRAG
                    await self._add_chunks_to_lightrag(db_id, document, chunks)
                    
                    # 转换为兼容格式
                    file_record = {
                        "file_id": document.document_id,
                        "filename": document.filename,
                        "path": document.original_path,
                        "file_type": document.file_type.value,
                        "status": document.status.value,
                        "created_at": document.created_at.timestamp()
                    }
                    
                else:  # URL处理
                    # URL处理逻辑（类似文件处理）
                    file_record = await self._process_url_content(user_id, db_id, item, params)
                
                processed_items.append(file_record)
                
            except Exception as e:
                logger.error(f"Failed to process {content_type} {item}: {e}")
                processed_items.append({
                    "file_id": None,
                    "filename": Path(item).name if content_type == "file" else item,
                    "path": item,
                    "file_type": content_type,
                    "status": "failed",
                    "error": str(e),
                    "created_at": time.time()
                })
        
        return processed_items

    async def _add_chunks_to_lightrag(self, db_id: str, document: DocumentInfo, chunks: List[ChunkInfo]):
        """将分块内容添加到 LightRAG"""
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")
        
        # 构建文档内容
        full_content = "\n\n".join([chunk.content for chunk in chunks])
        
        # 添加到 LightRAG
        await rag.ainsert(
            input=full_content,
            ids=document.document_id,
            file_paths=document.original_path
        )
        
        logger.info(f"Added document {document.document_id} to LightRAG with {len(chunks)} chunks")
```

### 1.4 查询和检索方法保持不变

```python
    async def aquery(self, user_id: str, query_text: str, db_id: str, **kwargs):
        """查询知识库 - LightRAG部分保持不变"""
        # 权限检查
        await self._check_permission(user_id, db_id, "read")
        
        # LightRAG查询逻辑完全不变
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
            logger.error(f"Query error: {e}")
            return ""
```

## 阶段2：增强 indexing.py

### 2.1 保持现有接口，增强内部实现

```python
# src/core/indexing.py 保持所有现有函数签名

async def parse_pdf_async(file_path: str, params: dict = None) -> str:
    """异步PDF解析 - 保持接口不变，内部可选择使用新系统缓存"""
    # 原有逻辑保持不变
    return await asyncio.to_thread(parse_pdf, file_path, params)

def chunk_text(text: str, params: dict = None) -> List[dict]:
    """文本分块 - 接口保持不变"""
    # 原有逻辑保持不变，但可以被新系统调用
    params = params or {}
    chunk_size = int(params.get("chunk_size", 500))
    chunk_overlap = int(params.get("chunk_overlap", 100))

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""]
    )

    nodes = text_splitter.split_text(text)
    nodes = [{"text": node, "metadata": {"chunk_idx": i}} for i, node in enumerate(nodes)]
    return nodes
```

## 阶段3：数据迁移策略

### 3.1 元数据迁移

```python
# 迁移脚本：migrate_metadata.py
async def migrate_existing_data():
    """迁移现有JSON数据到新系统"""
    
    # 1. 读取现有元数据
    old_work_dir = os.path.join(config.save_dir, "lightrag_data")
    meta_file = os.path.join(old_work_dir, "metadata.json")
    
    if not os.path.exists(meta_file):
        logger.info("No existing metadata to migrate")
        return
    
    with open(meta_file, 'r', encoding='utf-8') as f:
        old_data = json.load(f)
    
    databases_meta = old_data.get("databases", {})
    files_meta = old_data.get("files", {})
    
    # 2. 初始化新文件管理系统
    from src.file import load_storage_config, FileManager
    config = load_storage_config()
    file_manager = await FileManager.create_from_config(config)
    
    # 3. 迁移数据库信息
    for db_id, db_info in databases_meta.items():
        logger.info(f"Migrating database: {db_id}")
        
        # 创建知识库记录（如果不存在）
        try:
            stats = await file_manager.get_kb_statistics(db_id)
            if not stats:
                # 创建知识库记录
                await file_manager._create_kb_record(db_id, db_info)
        except Exception as e:
            logger.warning(f"Failed to migrate database {db_id}: {e}")
    
    # 4. 迁移文件信息
    for file_id, file_info in files_meta.items():
        logger.info(f"Migrating file: {file_id}")
        
        try:
            # 构建文档信息
            from src.file.models import DocumentInfo, DocumentType, ProcessingStatus
            from datetime import datetime
            
            document = DocumentInfo(
                document_id=file_id,
                kb_id=file_info.get("database_id", "unknown"),
                filename=file_info.get("filename", "unknown"),
                original_path=file_info.get("path", ""),
                file_type=DocumentType(file_info.get("file_type", "unknown")),
                file_size=os.path.getsize(file_info.get("path", "")) if os.path.exists(file_info.get("path", "")) else 0,
                file_hash=hashlib.md5(file_info.get("path", "").encode()).hexdigest(),
                status=ProcessingStatus(file_info.get("status", "completed")),
                created_at=datetime.fromtimestamp(file_info.get("created_at", time.time())),
                updated_at=datetime.now(),
                metadata=file_info
            )
            
            # 保存到新系统
            await file_manager.metadata_storage.save_document(document)
            
            # 如果有本地文件，迁移到MinIO
            if os.path.exists(file_info.get("path", "")):
                storage_path = f"{document.kb_id}/documents/{document.document_id}/{document.filename}"
                await file_manager.file_storage.upload_file(
                    file_info.get("path", ""),
                    storage_path
                )
                
                # 更新存储路径
                document.storage_path = storage_path
                await file_manager.metadata_storage.save_document(document)
                
        except Exception as e:
            logger.error(f"Failed to migrate file {file_id}: {e}")
    
    # 5. 备份原有数据
    backup_file = f"{meta_file}.backup.{int(time.time())}"
    shutil.copy2(meta_file, backup_file)
    logger.info(f"Original metadata backed up to: {backup_file}")
```

### 3.2 LightRAG存储配置优化

```python
# 在 _get_lightrag_instance 中，保持向量和图存储不变，只改进文档状态存储
rag = LightRAG(
    working_dir=working_dir,
    llm_model_func=self._get_llm_func(llm_info),
    embedding_func=self._get_embedding_func(embed_info),
    vector_storage="MilvusVectorDBStorage",    # 保持不变
    kv_storage="JsonKVStorage",                # 保持不变  
    graph_storage="PGGraphStorage",            # 保持不变
    doc_status_storage="JsonDocStatusStorage", # 可选：替换为PostgreSQL
    log_file_path=os.path.join(self.work_dir, db_id, "lightrag.log"),
)
```

## 阶段4：测试和验证

### 4.1 单元测试

```python
# tests/test_file_system_integration.py
class TestFileSystemIntegration:
    
    async def test_upload_and_query(self):
        """测试文件上传和查询的完整流程"""
        kb = LightRagBasedKB()
        
        # 上传文件
        result = await kb.add_content(
            user_id="test_user",
            db_id="test_kb", 
            items=["/path/to/test.pdf"],
            params={"chunk_size": 500}
        )
        
        assert len(result) == 1
        assert result[0]["status"] == "done"
        
        # 查询测试
        response = await kb.aquery(
            user_id="test_user",
            query_text="test query",
            db_id="test_kb"
        )
        
        assert response is not None
    
    async def test_database_management(self):
        """测试数据库管理功能"""
        kb = LightRagBasedKB()
        
        # 创建数据库
        db_info = await kb.create_database(
            user_id="test_user",
            database_name="test_db",
            description="test description",
            embed_info={}
        )
        
        assert db_info["name"] == "test_db"
        
        # 获取数据库列表
        databases = await kb.get_databases("test_user")
        assert len(databases["databases"]) > 0
```

### 4.2 集成测试

```python
# tests/test_api_compatibility.py  
class TestAPICompatibility:
    """确保API接口完全兼容"""
    
    async def test_data_router_compatibility(self):
        """测试data_router的所有端点"""
        # 测试所有现有API端点仍然正常工作
        pass
```

## 阶段5：部署和监控

### 5.1 部署脚本

```bash
#!/bin/bash
# deploy_new_file_system.sh

# 1. 安装新依赖
pip install minio>=7.2.0

# 2. 创建数据库表
python -c "
from src.file.storage.postgres_storage import PostgreSQLConnection
from src.file.config import load_storage_config

config = load_storage_config()
conn = PostgreSQLConnection(config.postgres_url)
conn.create_tables()
print('Database tables created successfully')
"

# 3. 迁移现有数据
python migrate_metadata.py

# 4. 验证部署
python -c "
import asyncio
from src.core.lightrag_based_kb import LightRagBasedKB

async def test():
    kb = LightRagBasedKB()
    await kb._ensure_initialized()
    health = await kb.file_manager.health_check()
    print(f'Health check: {health}')

asyncio.run(test())
"
```

### 5.2 监控指标

```python
# 关键监控指标
monitoring_metrics = {
    "file_upload_success_rate": "文件上传成功率",
    "query_response_time": "查询响应时间", 
    "storage_usage": "存储空间使用率",
    "cache_hit_rate": "缓存命中率",
    "error_rate": "错误率"
}
```