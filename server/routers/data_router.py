import os
import asyncio
import traceback
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Body, Form, Query

from src.utils import logger, hashstr
from src import executor, config, knowledge_base, graph_base
from server.auth.rbac_middleware import get_required_user, get_admin_user
from server.auth.permission_framework import (
    require_kb_permission, require_system_permission, Permission
)
from server.models.user_model import User

data = APIRouter(prefix="/data")

def get_user_id(user: User) -> str:
    """获取用户ID，优先使用external_user_id（外部JWT用户）"""
    return getattr(user, 'external_user_id', None) or str(user.id)


@data.get("/")
@require_system_permission(Permission.READ)
async def get_databases(current_user: User = Depends(get_required_user)):
    try:
        database = await knowledge_base.get_databases(get_user_id(current_user))
    except Exception as e:
        logger.error(f"获取数据库列表失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取数据库列表失败 {e}", "databases": []}
    return database

@data.post("/")
@require_system_permission(Permission.CREATE)
async def create_database(
    database_name: str = Body(...),
    description: str = Body(...),
    embed_model_name: str = Body(...),
    current_user: User = Depends(get_required_user)
):
    logger.debug(f"Create database {database_name}")
    try:
        embed_info = config.embed_model_names[embed_model_name]
        database_info = await knowledge_base.create_database(
            get_user_id(current_user),
            database_name,
            description,
            embed_info=embed_info
        )
    except Exception as e:
        logger.error(f"创建数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"创建数据库失败 {e}", "status": "failed"}
    return database_info

@data.delete("/")
@require_kb_permission(Permission.DELETE, "db_id")
async def delete_database(db_id, current_user: User = Depends(get_required_user)):
    logger.debug(f"Delete database {db_id}")
    await knowledge_base.delete_database(get_user_id(current_user), db_id)
    return {"message": "删除成功"}

@data.post("/query-test")
async def query_test(query: str = Body(...), meta: dict = Body(...), current_user: User = Depends(get_required_user)):
    logger.debug(f"Query test in {meta}: {query}")
    db_id = meta.get("db_id")
    
    # 动态权限检查
    if db_id:
        from server.auth.permission_framework import PermissionEngine, KnowledgeBaseResource, Permission, PermissionContext
        from datetime import datetime
        
        engine = PermissionEngine.get_instance()
        resource = KnowledgeBaseResource(db_id)
        context = PermissionContext(
            user_id=get_user_id(current_user),
            resource=resource,
            permission=Permission.READ,
            request_metadata={"endpoint": "query_test", "method": "POST"},
            timestamp=datetime.now()
        )
        
        result_check = await engine.check_permission(context)
        if not result_check.allowed:
            raise HTTPException(403, f"Permission denied: {result_check.reason}")
    
    result = await knowledge_base.aquery(get_user_id(current_user), query, db_id, **meta)
    return result

@data.post("/add-files")
@require_kb_permission(Permission.WRITE, "db_id")
async def add_files(db_id: str = Body(...), items: list[str] = Body(...), params: dict = Body(...), current_user: User = Depends(get_required_user)):
    logger.debug(f"Add files/urls for db_id {db_id}: {items} {params=}")

    # 从 params 中获取 content_type，默认为 'file'
    content_type = params.get('content_type', 'file')

    try:
        # 使用统一的 add_content 方法
        processed_items = await knowledge_base.add_content(get_user_id(current_user), db_id, items, params=params)

        item_type = "URLs" if content_type == 'url' else "files"
        processed_failed_count = len([_p for _p in processed_items if _p['status'] == 'failed'])
        processed_info = f"Processed {len(processed_items)} {item_type}, {processed_failed_count} {item_type} failed"
        return {"message": processed_info, "items": processed_items, "status": "success"}
    except Exception as e:
        logger.error(f"Failed to process {content_type}s: {e}, {traceback.format_exc()}")
        return {"message": f"Failed to process {content_type}s: {e}", "status": "failed"}

@data.post("/file-to-chunk")
async def file_to_chunk(db_id: str = Body(...), files: list[str] = Body(...), params: dict = Body(...), current_user: User = Depends(get_admin_user)):
    logger.debug(f"File to chunk for db_id {db_id}: {files} {params=} (deprecated, use /add-files)")
    # 兼容性路由，转发到新的统一接口
    params['content_type'] = 'file'
    return await add_files(db_id, files, params, current_user)

@data.post("/url-to-chunk")
async def url_to_chunk(db_id: str = Body(...), urls: list[str] = Body(...), params: dict = Body(...), current_user: User = Depends(get_admin_user)):
    logger.debug(f"Url to chunk for db_id {db_id}: {urls} {params=} (deprecated, use /add-files)")
    # 兼容性路由，转发到新的统一接口
    params['content_type'] = 'url'
    return await add_files(db_id, urls, params, current_user)

@data.post("/add-by-file")
async def create_document_by_file(db_id: str = Body(...), files: list[str] = Body(...), current_user: User = Depends(get_admin_user)):
    raise ValueError("This method is deprecated. Use /add-files instead.")

@data.post("/add-by-chunks")
async def add_by_chunks(db_id: str = Body(...), file_chunks: dict = Body(...), current_user: User = Depends(get_admin_user)):
    raise ValueError("This method is deprecated. Use /add-files instead.")

@data.get("/info")
@require_kb_permission(Permission.READ, "db_id")
async def get_database_info(db_id: str, current_user: User = Depends(get_required_user)):
    # logger.debug(f"Get database {db_id} info")
    database = await knowledge_base.get_database_info(get_user_id(current_user), db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database

@data.delete("/document")
@require_kb_permission(Permission.WRITE, "db_id")
async def delete_document(db_id: str = Body(...), file_id: str = Body(...), current_user: User = Depends(get_required_user)):
    logger.debug(f"DELETE document {file_id} info in {db_id}")
    await knowledge_base.delete_file(get_user_id(current_user), db_id, file_id)
    return {"message": "删除成功"}

@data.get("/document")
@require_kb_permission(Permission.READ, "db_id")
async def get_document_info(db_id: str, file_id: str, current_user: User = Depends(get_required_user)):
    logger.debug(f"GET document {file_id} info in {db_id}")

    try:
        info = await knowledge_base.get_file_info(get_user_id(current_user), db_id, file_id)
    except Exception as e:
        logger.error(f"Failed to get file info, {e}, {db_id=}, {file_id=}, {traceback.format_exc()}")
        info = {"message": "Failed to get file info", "status": "failed"}

    return info

@data.post("/upload")
@require_system_permission(Permission.WRITE)
async def upload_file(
    file: UploadFile = File(...),
    db_id: str | None = Query(None),
    current_user: User = Depends(get_required_user)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No selected file")

    # 使用新的文件管理系统
    from src.database.manager import get_database_manager
    from src.database.repositories.file_repository import FileInfo
    from datetime import datetime
    import hashlib
    import uuid
    
    try:
        db_manager = get_database_manager()
        await db_manager.initialize()
        
        # 获取MinIO适配器进行文件存储
        minio_adapter = await db_manager.get_minio_adapter()
        
        # 读取文件内容
        file_content = await file.read()
        
        # 生成唯一文件名和路径
        basename, ext = os.path.splitext(file.filename)
        unique_filename = f"{basename}_{hashstr(basename, 4, with_salt=True)}{ext}".lower()
        
        # 生成文件ID和存储路径
        file_id = hashlib.sha256(f"{db_id or 'default'}:{unique_filename}:{datetime.now().isoformat()}".encode()).hexdigest()[:32]
        storage_key = f"{db_id or 'uploads'}/documents/{file_id}/{unique_filename}"
        
        # 上传文件到MinIO
        await minio_adapter.upload_bytes(file_content, storage_key)
        
        # 创建文件信息对象
        file_info = FileInfo(
            file_id=file_id,
            filename=unique_filename,
            storage_key=storage_key,
            size=len(file_content),
            content_type=file.content_type,
            metadata={
                "upload_time": datetime.now().isoformat(),
                "original_filename": file.filename,
                "uploaded_by": current_user.username if hasattr(current_user, 'username') else str(current_user.id),
                "kb_id": db_id
            }
        )
        
        # 获取文件仓储并保存文件信息
        file_repo = db_manager.get_file_repository()
        saved_file_info = await file_repo.create(file_info)
        
        return {
            "message": "File successfully uploaded to distributed storage",
            "file_id": file_info.file_id,
            "filename": file_info.filename,
            "storage_key": file_info.storage_key,
            "size": file_info.size,
            "status": "pending_processing",
            "db_id": db_id,
            # 保持向后兼容性，提供file_path字段
            "file_path": file_info.storage_key
        }
        
    except Exception as e:
        logger.error(f"File upload failed: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@data.get("/file-status/{file_id}")
@require_system_permission(Permission.READ)
async def get_file_status(
    file_id: str,
    current_user: User = Depends(get_required_user)
):
    """获取文件处理状态"""
    try:
        from src.database.manager import get_database_manager
        
        db_manager = get_database_manager()
        await db_manager.initialize()
        
        file_repo = db_manager.get_file_repository()
        file_info = await file_repo.get_by_id(file_id)
        
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        return {
            "file_id": file_info.file_id,
            "filename": file_info.filename,
            "status": file_info.status,
            "size": file_info.size,
            "content_type": file_info.content_type,
            "created_at": file_info.created_at.isoformat() if hasattr(file_info, 'created_at') else None,
            "updated_at": file_info.updated_at.isoformat() if hasattr(file_info, 'updated_at') else None,
            "metadata": file_info.metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file status: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get file status: {e}")

@data.post("/file-process/{file_id}")
@require_system_permission(Permission.WRITE)
async def process_file(
    file_id: str,
    processing_params: dict = Body(default={}),
    current_user: User = Depends(get_required_user)
):
    """手动触发文件处理"""
    try:
        from src.database.manager import get_database_manager
        
        db_manager = get_database_manager()
        await db_manager.initialize()
        
        file_repo = db_manager.get_file_repository()
        
        # 获取文件信息并更新状态为处理中
        file_info = await file_repo.get_by_id(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_info.metadata["status"] = "processing"
        await file_repo.update(file_info)
        
        # 这里可以添加异步任务调度，比如使用Celery
        # 目前返回处理中状态
        return {
            "message": "File processing initiated",
            "file_id": file_id,
            "status": "processing",
            "processing_params": processing_params
        }
        
    except Exception as e:
        logger.error(f"Failed to process file: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {e}")

@data.get("/files")
@require_system_permission(Permission.READ)
async def list_files(
    db_id: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str = Query(None),
    current_user: User = Depends(get_required_user)
):
    """获取文件列表"""
    try:
        from src.database.manager import get_database_manager
        
        db_manager = get_database_manager()
        await db_manager.initialize()
        
        file_repo = db_manager.get_file_repository()
        
        # 获取文件列表
        files = await file_repo.find_all(limit=limit, offset=offset)
        
        return {
            "files": [
                {
                    "file_id": f.file_id,
                    "filename": f.filename,
                    "size": f.size,
                    "content_type": f.content_type,
                    "status": f.status,
                    "created_at": f.created_at.isoformat() if hasattr(f, 'created_at') else None,
                    "metadata": f.metadata
                }
                for f in files
            ],
            "total": len(files),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Failed to list files: {e}, {traceback.format_exc()}")
        return {"files": [], "total": 0, "error": str(e)}

@data.get("/graph")
async def get_graph_info(current_user: User = Depends(get_admin_user)):
    graph_info = graph_base.get_graph_info()
    if graph_info is None:
        raise HTTPException(status_code=400, detail="图数据库获取出错")
    return graph_info

@data.post("/graph/index-nodes")
async def index_nodes(data: dict = Body(default={}), current_user: User = Depends(get_admin_user)):
    if not graph_base.is_running():
        raise HTTPException(status_code=400, detail="图数据库未启动")

    # 获取参数或使用默认值
    kgdb_name = data.get('kgdb_name', 'neo4j')

    # 调用GraphDatabase的add_embedding_to_nodes方法
    count = graph_base.add_embedding_to_nodes(kgdb_name=kgdb_name)

    return {"status": "success", "message": f"已成功为{count}个节点添加嵌入向量", "indexed_count": count}

@data.get("/graph/node")
async def get_graph_node(entity_name: str, current_user: User = Depends(get_admin_user)):
    result = graph_base.query_node(entity_name=entity_name)
    return {"result": graph_base.format_query_result_to_graph(result), "message": "success"}

@data.get("/graph/nodes")
async def get_graph_nodes(kgdb_name: str, num: int, current_user: User = Depends(get_admin_user)):

    logger.debug(f"Get graph nodes in {kgdb_name} with {num} nodes")
    result = graph_base.get_sample_nodes(kgdb_name, num)
    return {"result": graph_base.format_general_results(result), "message": "success"}

@data.post("/graph/add-by-jsonl")
async def add_graph_entity(file_path: str = Body(...), kgdb_name: str | None = Body(None), current_user: User = Depends(get_admin_user)):

    if not file_path.endswith('.jsonl'):
        return {"message": "文件格式错误，请上传jsonl文件", "status": "failed"}

    try:
        await graph_base.jsonl_file_add_entity(file_path, kgdb_name)
        return {"message": "实体添加成功", "status": "success"}
    except Exception as e:
        logger.error(f"添加实体失败: {e}, {traceback.format_exc()}")
        return {"message": f"添加实体失败: {e}", "status": "failed"}

@data.post("/update")
@require_kb_permission(Permission.UPDATE, "db_id")
async def update_database_info(
    db_id: str = Body(...),
    name: str = Body(...),
    description: str = Body(...),
    current_user: User = Depends(get_required_user)
):
    logger.debug(f"Update database {db_id} info: {name}, {description}")
    try:
        database = await knowledge_base.update_database(get_user_id(current_user), db_id, name, description)
        return {"message": "更新成功", "database": database}
    except Exception as e:
        logger.error(f"更新数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"更新数据库失败: {e}")

