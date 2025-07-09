"""
知识库集合管理API路由
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from server.auth.rbac_middleware import require_permission, get_required_user
from server.models.user_model import User
from src.database.managers.kb_collection_manager import get_kb_collection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kb-collections", tags=["知识库集合管理"])


class CollectionCreateRequest(BaseModel):
    """集合创建请求"""
    kb_id: str
    force_recreate: bool = False


class CollectionDeleteRequest(BaseModel):
    """集合删除请求"""
    kb_id: str
    confirm: bool = False


class CollectionMigrationRequest(BaseModel):
    """集合迁移请求"""
    kb_id: str
    global_collection_mapping: Optional[Dict[str, str]] = None


@router.get("/health")
async def collection_manager_health():
    """集合管理器健康检查"""
    try:
        manager = await get_kb_collection_manager()
        health_info = await manager.health_check()
        return health_info
    except Exception as e:
        logger.error(f"Collection manager health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/summary")
async def get_all_collections_summary(
    current_user: User = Depends(require_permission("kb:read"))
):
    """获取所有知识库集合摘要"""
    try:
        manager = await get_kb_collection_manager()
        summary = await manager.get_all_kb_collections_summary()
        return summary
    except Exception as e:
        logger.error(f"Failed to get collections summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")


@router.get("/{kb_id}")
async def get_kb_collection_info(
    kb_id: str,
    current_user: User = Depends(require_permission("kb:read"))
):
    """获取指定知识库的集合信息"""
    try:
        manager = await get_kb_collection_manager()
        collection_info = await manager.get_kb_collection_info(kb_id)
        return collection_info
    except Exception as e:
        logger.error(f"Failed to get collection info for KB {kb_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get collection info: {str(e)}")


@router.post("/{kb_id}/create")
async def create_kb_collections(
    kb_id: str,
    force_recreate: bool = Query(False, description="是否强制重新创建"),
    current_user: User = Depends(require_permission("kb:create"))
):
    """为知识库创建集合"""
    try:
        manager = await get_kb_collection_manager()
        result = await manager.create_kb_collections(kb_id, force_recreate=force_recreate)
        
        if result['success']:
            return result
        else:
            raise HTTPException(status_code=400, detail=result['message'])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create collections for KB {kb_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create collections: {str(e)}")


@router.delete("/{kb_id}")
async def delete_kb_collections(
    kb_id: str,
    confirm: bool = Query(False, description="确认删除操作"),
    current_user: User = Depends(require_permission("kb:delete"))
):
    """删除知识库的所有集合"""
    try:
        manager = await get_kb_collection_manager()
        result = await manager.delete_kb_collections(kb_id, confirm=confirm)
        
        if result['success']:
            return result
        else:
            raise HTTPException(status_code=400, detail=result['message'])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete collections for KB {kb_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete collections: {str(e)}")


@router.post("/{kb_id}/migrate")
async def migrate_collections(
    kb_id: str,
    global_collection_mapping: Optional[Dict[str, str]] = None,
    current_user: User = Depends(require_permission("kb:update"))
):
    """从全局集合迁移数据到知识库专用集合"""
    try:
        manager = await get_kb_collection_manager()
        result = await manager.migrate_from_global_collections(
            kb_id, 
            global_collection_mapping=global_collection_mapping
        )
        
        if result['success']:
            return result
        else:
            raise HTTPException(status_code=400, detail=result['message'])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to migrate collections for KB {kb_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to migrate collections: {str(e)}")


@router.get("/{kb_id}/stats")
async def get_kb_collection_stats(
    kb_id: str,
    current_user: User = Depends(require_permission("kb:read"))
):
    """获取知识库集合的详细统计信息"""
    try:
        manager = await get_kb_collection_manager()
        collection_info = await manager.get_kb_collection_info(kb_id)
        
        if 'error' in collection_info:
            raise HTTPException(status_code=404, detail=collection_info['error'])
        
        # 构造详细统计信息
        stats = {
            'kb_id': kb_id,
            'collections': collection_info['collections'],
            'summary': {
                'total_collections': collection_info['total_collections'],
                'existing_collections': collection_info['existing_collections'],
                'missing_collections': collection_info['missing_collections']
            },
            'collection_details': {}
        }
        
        # 添加每个集合的详细信息
        for collection in collection_info['collections']:
            collection_type = collection['type']
            stats['collection_details'][collection_type] = {
                'name': collection['name'],
                'exists': collection['exists'],
                'stats': collection.get('stats', {}),
                'row_count': collection.get('stats', {}).get('row_count', 0)
            }
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection stats for KB {kb_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get collection stats: {str(e)}")


@router.post("/batch-create")
async def batch_create_collections(
    kb_ids: List[str],
    force_recreate: bool = Query(False, description="是否强制重新创建"),
    current_user: User = Depends(require_permission("kb:create"))
):
    """批量为多个知识库创建集合"""
    try:
        manager = await get_kb_collection_manager()
        results = []
        
        for kb_id in kb_ids:
            try:
                result = await manager.create_kb_collections(kb_id, force_recreate=force_recreate)
                results.append({
                    'kb_id': kb_id,
                    'success': result['success'],
                    'message': result['message']
                })
            except Exception as e:
                results.append({
                    'kb_id': kb_id,
                    'success': False,
                    'message': str(e)
                })
        
        # 统计成功和失败的数量
        success_count = sum(1 for r in results if r['success'])
        
        return {
            'total_requested': len(kb_ids),
            'success_count': success_count,
            'failed_count': len(kb_ids) - success_count,
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Failed to batch create collections: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to batch create collections: {str(e)}")


@router.get("/global/collections")
async def list_global_collections(
    current_user: User = Depends(require_permission("system:read"))
):
    """列出当前的全局集合（用于迁移参考）"""
    try:
        manager = await get_kb_collection_manager()
        await manager.ensure_initialized()
        
        # 获取所有集合
        all_collections = await manager.milvus_adapter.list_collections()
        
        # 分类：知识库专用集合 vs 全局集合
        kb_collections = []
        global_collections = []
        
        for collection_name in all_collections:
            if collection_name.startswith('kb_') and collection_name.count('_') >= 2:
                # 知识库专用集合
                kb_id = manager.milvus_adapter._get_kb_id_from_collection_name(collection_name)
                collection_type = manager.milvus_adapter._get_collection_type_from_name(collection_name)
                
                kb_collections.append({
                    'name': collection_name,
                    'kb_id': kb_id,
                    'type': collection_type
                })
            else:
                # 全局集合
                stats = await manager.milvus_adapter.get_collection_stats(collection_name)
                global_collections.append({
                    'name': collection_name,
                    'stats': stats
                })
        
        return {
            'total_collections': len(all_collections),
            'kb_collections': {
                'count': len(kb_collections),
                'collections': kb_collections
            },
            'global_collections': {
                'count': len(global_collections),
                'collections': global_collections
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to list global collections: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")