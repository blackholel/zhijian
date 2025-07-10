"""
知识库API路由 - 使用新的架构
"""

import logging
import traceback
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Body, Query, File, UploadFile
from fastapi.responses import StreamingResponse

from src.auth.middleware.rbac_middleware import get_required_user
from src.auth.permission_framework import require_kb_permission, require_system_permission, Permission
from src.auth.models.user_models import User
from src.database.connection_manager import DatabaseConnectionManager
from src.database.managers.knowledge_manager import KnowledgeBaseManager

logger = logging.getLogger(__name__)

# 创建路由器
knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# 全局变量
_kb_manager: Optional[KnowledgeBaseManager] = None


async def get_kb_manager() -> KnowledgeBaseManager:
    """获取知识库管理器实例"""
    global _kb_manager
    if _kb_manager is None:
        connection_manager = DatabaseConnectionManager()
        await connection_manager.initialize_common_databases()
        _kb_manager = KnowledgeBaseManager(connection_manager)
    return _kb_manager


def get_user_id(user: User) -> str:
    """获取用户ID，返回UUID格式的id用于数据库关联"""
    return str(user.id)


# 知识库管理接口

@knowledge_router.get("/databases")
async def list_knowledge_bases(
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取用户可访问的知识库列表"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        knowledge_bases = await kb_manager.get_user_knowledge_bases(user_id)
        
        return {
            "knowledge_bases": [kb.to_dict() for kb in knowledge_bases],
            "total": len(knowledge_bases),
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"获取知识库列表失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")


@knowledge_router.post("/databases")
@require_system_permission(Permission.CREATE)
async def create_knowledge_base(
    kb_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """创建知识库"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        # 验证必需字段
        if 'name' not in kb_data:
            raise HTTPException(status_code=400, detail="缺少必需字段: name")
        
        knowledge_base = await kb_manager.create_knowledge_base(kb_data, user_id)
        
        return {
            "message": "知识库创建成功",
            "knowledge_base": knowledge_base.to_dict(),
            "status": "success"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建知识库失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {str(e)}")


@knowledge_router.get("/databases/{kb_id}")
@require_kb_permission(Permission.READ, "kb_id")
async def get_knowledge_base(
    kb_id: str,
    include_files: bool = Query(True),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取知识库详情"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        knowledge_base = await kb_manager.get_knowledge_base(kb_id, user_id, include_files)
        
        if not knowledge_base:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        return {
            "knowledge_base": knowledge_base.to_dict(),
            "status": "success"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取知识库失败: {str(e)}")


@knowledge_router.put("/databases/{kb_id}")
@require_kb_permission(Permission.WRITE, "kb_id")
async def update_knowledge_base(
    kb_id: str,
    updates: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """更新知识库"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        knowledge_base = await kb_manager.update_knowledge_base(kb_id, updates, user_id)
        
        if not knowledge_base:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        return {
            "message": "知识库更新成功",
            "knowledge_base": knowledge_base.to_dict(),
            "status": "success"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"更新知识库失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"更新知识库失败: {str(e)}")


@knowledge_router.delete("/databases/{kb_id}")
@require_kb_permission(Permission.DELETE, "kb_id")
async def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """删除知识库"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        success = await kb_manager.delete_knowledge_base(kb_id, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        return {
            "message": "知识库删除成功",
            "status": "success"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"删除知识库失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")


# 文件管理接口

@knowledge_router.post("/databases/{kb_id}/upload")
@require_kb_permission(Permission.WRITE, "kb_id")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    metadata: Optional[str] = Body(None),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """上传文档到知识库（仅支持MinIO存储）"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="未选择文件")
        
        # 读取文件内容
        file_content = await file.read()
        
        # 获取文件类型
        file_type = file.content_type or 'application/octet-stream'
        
        # 解析元数据
        import json
        file_metadata = {}
        if metadata:
            try:
                file_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="元数据格式错误")
        
        # 使用MinIO存储
        import hashlib
        import os
        from datetime import datetime
        
        # 使用知识库管理器中的MinIO适配器
        minio_adapter = await kb_manager.connection_manager.get_minio_adapter()
        
        # 生成唯一文件名和MinIO存储路径
        basename, ext = os.path.splitext(file.filename)
        file_id = hashlib.sha256(f"{kb_id}:{file.filename}:{datetime.now().isoformat()}".encode()).hexdigest()[:32]
        storage_key = f"knowledge_bases/{kb_id}/documents/{file_id}/{file.filename}"
        
        # 上传到MinIO
        actual_storage_key = await minio_adapter.upload_bytes(file_content, storage_key)
        
        # 使用MinIO返回的实际存储键创建知识库文件记录
        uploaded_file = await kb_manager.upload_document(
            kb_id, actual_storage_key, file.filename, file_type, user_id, file_metadata, file_id, len(file_content)
        )
        
        return {
            "message": "文档上传成功",
            "file": uploaded_file.to_dict(),
            "status": "success",
            "storage_type": "minio"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"文档上传失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")


@knowledge_router.get("/databases/{kb_id}/files")
@require_kb_permission(Permission.READ, "kb_id")
async def list_files(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取知识库文件列表"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        files = await kb_manager.file_repo.get_files_by_database(kb_id, user_id)
        
        return {
            "files": [file_obj.to_dict() for file_obj in files],
            "total": len(files),
            "kb_id": kb_id
        }
        
    except Exception as e:
        logger.error(f"获取文件列表失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")


@knowledge_router.get("/files/{file_id}")
@require_kb_permission(Permission.READ, "kb_id")  # 需要从文件获取kb_id
async def get_file_details(
    file_id: str,
    include_nodes: bool = Query(False),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取文件详情"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        file_obj = await kb_manager.get_file_details(file_id, user_id, include_nodes)
        
        if not file_obj:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return {
            "file": file_obj.to_dict(),
            "status": "success"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件详情失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取文件详情失败: {str(e)}")


@knowledge_router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_required_user)
):
    """下载文件（仅支持MinIO存储）"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        # 获取文件信息
        file_obj = await kb_manager.get_file_details(file_id, user_id, include_nodes=False)
        if not file_obj:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 从MinIO下载
        from fastapi.responses import StreamingResponse
        import io
        
        # 使用知识库管理器中的MinIO适配器
        minio_adapter = await kb_manager.connection_manager.get_minio_adapter()
        
        # 获取文件内容
        file_content = await minio_adapter.get_file_bytes(file_obj.path)
        
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=file_obj.file_type,
            headers={"Content-Disposition": f"attachment; filename={file_obj.filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件下载失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"文件下载失败: {str(e)}")


@knowledge_router.delete("/files/{file_id}")
async def delete_document(
    file_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """删除文档"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        success = await kb_manager.delete_document(file_id, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return {
            "message": "文件删除成功",
            "status": "success"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"删除文件失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")


# 查询和搜索接口

@knowledge_router.post("/databases/{kb_id}/query")
@require_kb_permission(Permission.READ, "kb_id")
async def query_knowledge_base(
    kb_id: str,
    query_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """查询知识库"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        query = query_data.get('query', '')
        limit = query_data.get('limit', 10)
        
        if not query:
            raise HTTPException(status_code=400, detail="查询内容不能为空")
        
        results = await kb_manager.query_knowledge_base(kb_id, query, user_id, limit)
        
        return {
            "query": query,
            "results": results,
            "total": len(results),
            "kb_id": kb_id
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"查询知识库失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"查询知识库失败: {str(e)}")


# 权限管理接口

@knowledge_router.post("/databases/{kb_id}/permissions")
@require_kb_permission(Permission.ADMIN, "kb_id")
async def grant_permission(
    kb_id: str,
    permission_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """授予知识库权限"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        target_user_id = permission_data.get('user_id')
        permission_type = permission_data.get('permission_type', 'read')
        expires_at = permission_data.get('expires_at')
        
        if not target_user_id:
            raise HTTPException(status_code=400, detail="缺少目标用户ID")
        
        # 解析过期时间
        if expires_at:
            expires_at = datetime.fromisoformat(expires_at)
        
        success = await kb_manager.grant_kb_permission(
            kb_id, target_user_id, permission_type, user_id, expires_at
        )
        
        return {
            "message": "权限授予成功" if success else "权限授予失败",
            "status": "success" if success else "failed"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"授予权限失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"授予权限失败: {str(e)}")


@knowledge_router.delete("/databases/{kb_id}/permissions/{target_user_id}")
@require_kb_permission(Permission.ADMIN, "kb_id")
async def revoke_permission(
    kb_id: str,
    target_user_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """撤销知识库权限"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        success = await kb_manager.revoke_kb_permission(kb_id, target_user_id, user_id)
        
        return {
            "message": "权限撤销成功" if success else "权限撤销失败",
            "status": "success" if success else "failed"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"撤销权限失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"撤销权限失败: {str(e)}")


# 统计和监控接口

@knowledge_router.get("/databases/{kb_id}/statistics")
@require_kb_permission(Permission.READ, "kb_id")
async def get_statistics(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取知识库统计信息"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        stats = await kb_manager.get_knowledge_base_statistics(kb_id, user_id)
        
        return {
            "statistics": stats,
            "status": "success"
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


# 迁移和兼容性接口

@knowledge_router.post("/migrate-from-data-router")
@require_system_permission(Permission.ADMIN)
async def migrate_from_data_router(
    migration_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """从data router迁移文件到知识库系统 - 利用LightRAG集成优势"""
    try:
        kb_id = migration_data.get('kb_id')
        if not kb_id:
            raise HTTPException(status_code=400, detail="缺少知识库ID")
        
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        # 🔑 利用LightRAG适配器的优势：数据已经在LightRAG中
        from src import knowledge_base  # 复用全局LightRagBasedKB实例
        
        migrated_count = 0
        
        # 检查LightRAG中是否有该知识库的数据
        if kb_id in knowledge_base.databases_meta:
            # 获取LightRAG中的文件元数据
            lightrag_files = {}
            for file_id, file_info in knowledge_base.files_meta.items():
                if file_info.get("database_id") == kb_id:
                    lightrag_files[file_id] = file_info
            
            logger.info(f"发现LightRAG中有 {len(lightrag_files)} 个文件待迁移")
            
            # 确保新架构中存在对应的知识库
            kb = await kb_manager.get_knowledge_base(kb_id, user_id, include_files=False)
            if not kb:
                # 如果知识库不存在，从LightRAG元数据创建
                lightrag_kb_meta = knowledge_base.databases_meta[kb_id]
                kb_data = {
                    'db_id': kb_id,
                    'name': lightrag_kb_meta.get('name', kb_id),
                    'description': lightrag_kb_meta.get('description', ''),
                    'metadata': lightrag_kb_meta.get('metadata', {})
                }
                await kb_manager.create_knowledge_base(kb_data, user_id)
                logger.info(f"已在新架构中创建知识库: {kb_id}")
            
            # 迁移文件记录到新架构
            for file_id, file_info in lightrag_files.items():
                try:
                    # 检查文件是否已存在于新架构中
                    existing_file = await kb_manager.get_file_details(file_id, user_id, include_nodes=False)
                    if existing_file:
                        logger.info(f"文件 {file_id} 已存在，跳过迁移")
                        continue
                    
                    # 创建文件记录（使用MinIO存储类型）
                    file_record_data = {
                        'file_id': file_id,
                        'filename': file_info.get('filename', f'migrated_{file_id}'),
                        'path': file_info.get('path', ''),
                        'file_type': file_info.get('file_type', 'unknown'),
                        'status': 'completed',  # LightRAG中的文件已处理完成
                        'storage_type': 'minio',  # 标记为MinIO存储
                        'file_size': 0,  # 待获取实际大小
                        'metadata': {
                            'migrated_from': 'lightrag_data_router',
                            'original_created_at': file_info.get('created_at'),
                            'migration_timestamp': datetime.now().isoformat()
                        }
                    }
                    
                    # 使用文件仓储直接创建记录
                    migrated_file = await kb_manager.file_repo.create(file_record_data, kb_id, user_id)
                    migrated_count += 1
                    
                    logger.info(f"已迁移文件: {file_id} -> {migrated_file.file_id}")
                    
                except Exception as file_error:
                    logger.error(f"迁移文件 {file_id} 失败: {file_error}")
                    continue
            
            # 同步LightRAG知识库到新架构
            await kb_manager.lightrag_adapter.ensure_lightrag_sync(kb_id)
            
        else:
            logger.warning(f"LightRAG中未找到知识库 {kb_id} 的数据")
        
        return {
            "message": f"迁移完成，共迁移 {migrated_count} 个文件",
            "migrated_files": migrated_count,
            "kb_id": kb_id,
            "status": "success",
            "details": {
                "source": "lightrag_data_router",
                "target": "knowledge_base_manager",
                "lightrag_integration": "maintained"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"迁移失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"迁移失败: {str(e)}")


# 健康检查接口

@knowledge_router.get("/health")
async def health_check() -> Dict[str, Any]:
    """知识库系统健康检查"""
    try:
        kb_manager = await get_kb_manager()
        health = await kb_manager.health_check()
        
        return health
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}, {traceback.format_exc()}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# 模型配置管理接口

@knowledge_router.get("/databases/{kb_id}/model-config")
@require_kb_permission(Permission.READ, "kb_id")
async def get_kb_model_config(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取知识库的模型配置"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        config_info = await kb_manager.lightrag_adapter.get_kb_model_config(kb_id, user_id)
        
        if not config_info:
            raise HTTPException(status_code=404, detail="知识库不存在或无权限访问")
        
        return {
            "success": True,
            "data": config_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型配置失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取模型配置失败: {str(e)}")


@knowledge_router.put("/databases/{kb_id}/model-config")
@require_kb_permission(Permission.UPDATE, "kb_id")
async def set_kb_model_config(
    kb_id: str,
    config_data: Dict[str, Any],
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """设置知识库的模型配置"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        # 提取配置参数
        llm_provider = config_data.get('llm_provider')
        llm_model = config_data.get('llm_model')
        embed_provider = config_data.get('embed_provider')
        embed_model = config_data.get('embed_model')
        
        # 验证必要参数
        if not llm_provider and not embed_provider:
            raise HTTPException(status_code=400, detail="至少需要提供一种模型配置")
        
        success = await kb_manager.lightrag_adapter.set_kb_model_config(
            kb_id=kb_id,
            llm_provider=llm_provider,
            llm_model=llm_model,
            embed_provider=embed_provider,
            embed_model=embed_model,
            user_id=user_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="模型配置更新失败")
        
        return {
            "success": True,
            "message": "模型配置已更新",
            "kb_id": kb_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置模型配置失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"设置模型配置失败: {str(e)}")


@knowledge_router.get("/model-config/available")
@require_system_permission(Permission.READ)
async def get_available_models(
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取所有可用的模型配置"""
    try:
        from src.core.lightrag_model_adapter import get_lightrag_model_adapter
        
        adapter = get_lightrag_model_adapter()
        available_models = adapter.get_available_models()
        
        return {
            "success": True,
            "data": available_models
        }
        
    except Exception as e:
        logger.error(f"获取可用模型失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取可用模型失败: {str(e)}")


@knowledge_router.delete("/databases/{kb_id}/model-config")
@require_kb_permission(Permission.UPDATE, "kb_id")
async def reset_kb_model_config(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """重置知识库模型配置为系统默认"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        # 获取知识库
        kb = await kb_manager.kb_repo.get_by_id(kb_id, user_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        
        # 清除模型配置
        meta_info = getattr(kb, 'meta_info', {}) or {}
        if 'model_config' in meta_info:
            del meta_info['model_config']
            kb.meta_info = meta_info
            await kb_manager.kb_repo.update(kb)
        
        # 清除LightRAG缓存
        from src import knowledge_base
        if kb_id in knowledge_base.databases_meta:
            del knowledge_base.databases_meta[kb_id]
        if kb_id in knowledge_base.instances:
            del knowledge_base.instances[kb_id]
        
        logger.info(f"已重置知识库模型配置: {kb_id}")
        
        return {
            "success": True,
            "message": "已重置为系统默认配置",
            "kb_id": kb_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置模型配置失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"重置模型配置失败: {str(e)}")


# 文件状态管理接口

@knowledge_router.get("/databases/{kb_id}/files/status")
@require_kb_permission(Permission.READ, "kb_id")
async def get_files_status(
    kb_id: str,
    status_filter: Optional[str] = Query(None, description="状态过滤: all, uploaded, processing, completed, failed"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    include_stats: bool = Query(True, description="是否包含统计信息"),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取知识库文件状态 - 分页异步接口"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        # 获取文件状态列表（现在返回DTO对象）
        status_result = await kb_manager.status_manager.get_files_status_batch(
            kb_id=kb_id,
            user_id=user_id,
            status_filter=status_filter,
            page=page,
            page_size=page_size
        )
        
        response = {
            "success": True,
            "data": status_result.to_dict(),
            "kb_id": kb_id
        }
        
        # 如果需要包含统计信息
        if include_stats:
            summary = await kb_manager.status_manager.get_status_summary(kb_id, user_id)
            response["summary"] = summary.to_dict()
        
        return response
        
    except Exception as e:
        logger.error(f"获取文件状态失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取文件状态失败: {str(e)}")


@knowledge_router.get("/databases/{kb_id}/files/status/summary")
@require_kb_permission(Permission.READ, "kb_id")
async def get_files_status_summary(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取知识库文件状态摘要"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        summary = await kb_manager.status_manager.get_status_summary(kb_id, user_id)
        
        return {
            "success": True,
            "data": summary.to_dict(),
            "kb_id": kb_id
        }
        
    except Exception as e:
        logger.error(f"获取状态摘要失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取状态摘要失败: {str(e)}")


@knowledge_router.get("/databases/{kb_id}/files/status/stream")
@require_kb_permission(Permission.READ, "kb_id")
async def stream_files_status(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> StreamingResponse:
    """实时文件状态流 - Server-Sent Events"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        async def event_generator():
            """事件生成器"""
            try:
                async for event in kb_manager.status_manager.watch_status_changes(kb_id, user_id):
                    # 格式化为SSE格式
                    import json
                    event_data = json.dumps(event)
                    yield f"data: {event_data}\n\n"
                    
            except Exception as e:
                logger.error(f"状态流生成失败: {e}")
                error_event = {
                    "type": "error",
                    "data": {"error": str(e)},
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(error_event)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except Exception as e:
        logger.error(f"创建状态流失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建状态流失败: {str(e)}")


@knowledge_router.post("/databases/{kb_id}/files/{file_id}/reprocess")
@require_kb_permission(Permission.WRITE, "kb_id")
async def reprocess_file(
    kb_id: str,
    file_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """重新处理文件"""
    try:
        kb_manager = await get_kb_manager()
        user_id = get_user_id(current_user)
        
        # 检查文件是否存在
        file_obj = await kb_manager.get_file_details(file_id, user_id, include_nodes=False)
        if not file_obj:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 检查文件是否属于指定知识库
        if file_obj.database_id != kb_id:
            raise HTTPException(status_code=400, detail="文件不属于指定知识库")
        
        # 重置状态为uploaded并触发重新处理
        await kb_manager.status_manager.update_file_status_with_event(file_id, 'uploaded')
        
        # 异步启动文档处理
        import asyncio
        asyncio.create_task(kb_manager._process_document_async(file_id, user_id))
        
        return {
            "success": True,
            "message": "文件重新处理已启动",
            "file_id": file_id,
            "kb_id": kb_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新处理文件失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"重新处理文件失败: {str(e)}")


# 性能监控和调试接口

@knowledge_router.get("/databases/{kb_id}/files/status/health")
@require_kb_permission(Permission.READ, "kb_id")
async def get_status_system_health(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取状态系统健康检查"""
    try:
        kb_manager = await get_kb_manager()
        
        # 检查状态管理器健康状态
        health_status = await kb_manager.status_manager.health_check()
        
        # 检查Redis连接状态
        redis_adapter = await kb_manager.connection_manager.get_adapter('redis')
        redis_status = {
            "available": redis_adapter.is_available if redis_adapter else False,
            "pub_sub_enabled": hasattr(redis_adapter, 'publish') if redis_adapter else False
        }
        
        return {
            "success": True,
            "data": {
                "status_manager": health_status,
                "redis_adapter": redis_status,
                "kb_id": kb_id
            }
        }
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")


@knowledge_router.post("/databases/{kb_id}/files/status/cache/clear")
@require_kb_permission(Permission.ADMIN, "kb_id")
async def clear_status_cache(
    kb_id: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """清除知识库状态缓存（管理员功能）"""
    try:
        kb_manager = await get_kb_manager()
        
        # 清除状态缓存
        await kb_manager.status_manager.status_cache.invalidate_kb_cache(kb_id)
        
        return {
            "success": True,
            "message": "状态缓存已清除",
            "kb_id": kb_id
        }
        
    except Exception as e:
        logger.error(f"清除缓存失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"清除缓存失败: {str(e)}")


# 性能监控接口

@knowledge_router.get("/monitoring/metrics")
@require_system_permission(Permission.READ)
async def get_performance_metrics(
    operation: Optional[str] = Query(None, description="特定操作的指标"),
    time_window: int = Query(3600, description="时间窗口（秒）"),
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取性能监控指标"""
    try:
        kb_manager = await get_kb_manager()
        
        # 获取指标摘要
        metrics_summary = kb_manager.status_manager.performance_monitor.get_metrics_summary(
            operation=operation,
            time_window=time_window
        )
        
        # 获取系统指标
        system_metrics = kb_manager.status_manager.performance_monitor.get_system_metrics()
        
        return {
            "success": True,
            "data": {
                "metrics_summary": metrics_summary,
                "system_metrics": system_metrics.to_dict(),
                "time_window_hours": time_window / 3600
            }
        }
        
    except Exception as e:
        logger.error(f"获取性能指标失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取性能指标失败: {str(e)}")


@knowledge_router.get("/monitoring/operations")
@require_system_permission(Permission.READ)
async def get_operation_breakdown(
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取操作分解统计"""
    try:
        kb_manager = await get_kb_manager()
        
        breakdown = kb_manager.status_manager.performance_monitor.get_operation_breakdown()
        
        return {
            "success": True,
            "data": breakdown
        }
        
    except Exception as e:
        logger.error(f"获取操作分解失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取操作分解失败: {str(e)}")


@knowledge_router.get("/monitoring/errors")
@require_system_permission(Permission.READ)
async def get_error_analysis(
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """获取错误分析"""
    try:
        kb_manager = await get_kb_manager()
        
        error_analysis = kb_manager.status_manager.performance_monitor.get_error_analysis()
        
        return {
            "success": True,
            "data": error_analysis
        }
        
    except Exception as e:
        logger.error(f"获取错误分析失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取错误分析失败: {str(e)}")


@knowledge_router.get("/monitoring/health")
async def get_monitoring_health() -> Dict[str, Any]:
    """获取监控系统健康状态"""
    try:
        kb_manager = await get_kb_manager()
        
        # 检查状态管理器健康状态
        status_health = await kb_manager.status_manager.health_check()
        
        # 检查性能监控器健康状态
        monitor_health = await kb_manager.status_manager.performance_monitor.health_check()
        
        return {
            "success": True,
            "data": {
                "status_manager": status_health,
                "performance_monitor": monitor_health,
                "overall_status": "healthy" if (
                    status_health.get("status") == "healthy" and 
                    monitor_health.get("status") == "healthy"
                ) else "degraded"
            }
        }
        
    except Exception as e:
        logger.error(f"监控健康检查失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"监控健康检查失败: {str(e)}")