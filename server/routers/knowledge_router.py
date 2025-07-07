"""
知识库API路由 - 使用新的架构
"""

import logging
import traceback
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Body, Query, File, UploadFile

from server.auth.rbac_middleware import get_required_user
from server.auth.permission_framework import require_kb_permission, require_system_permission, Permission
from server.models.user_model import User
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
@require_system_permission(Permission.READ)
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
    """上传文档到知识库"""
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
        
        # 上传文档
        uploaded_file = await kb_manager.upload_document(
            kb_id, file_content, file.filename, file_type, user_id, file_metadata
        )
        
        return {
            "message": "文档上传成功",
            "file": uploaded_file.to_dict(),
            "status": "success"
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