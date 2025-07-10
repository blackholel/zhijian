"""
权限框架管理API
提供权限系统状态查询、缓存管理等功能
"""

from fastapi import APIRouter, HTTPException, Depends, Body, Query
from typing import Optional, List
from datetime import datetime

from src.auth.permission_framework import (
    get_permission_framework, require_system_permission, Permission
)
from src.auth.models.user_models import User
from src.auth.middleware.rbac_middleware import get_required_user

permission_mgmt = APIRouter(prefix="/permission-framework")

@permission_mgmt.get("/status")
@require_system_permission(Permission.READ)
async def get_system_status(current_user: User = Depends(get_required_user)):
    """获取权限系统状态"""
    framework = get_permission_framework()
    return framework.get_system_status()

@permission_mgmt.post("/cache/invalidate-user")
@require_system_permission(Permission.ADMIN)
async def invalidate_user_cache(
    user_id: str = Body(...),
    current_user: User = Depends(get_required_user)
):
    """清除指定用户的权限缓存"""
    framework = get_permission_framework()
    await framework.invalidate_user_cache(user_id)
    return {"message": f"Invalidated cache for user {user_id}", "status": "success"}

@permission_mgmt.post("/cache/invalidate-resource")
@require_system_permission(Permission.ADMIN)
async def invalidate_resource_cache(
    resource_uri: str = Body(...),
    current_user: User = Depends(get_required_user)
):
    """清除指定资源的权限缓存"""
    framework = get_permission_framework()
    await framework.invalidate_resource_cache(resource_uri)
    return {"message": f"Invalidated cache for resource {resource_uri}", "status": "success"}

@permission_mgmt.get("/audit/logs")
@require_system_permission(Permission.READ)
async def get_audit_logs(
    user_id: Optional[str] = Query(None),
    resource_uri: Optional[str] = Query(None),
    permission: Optional[str] = Query(None),
    result: Optional[bool] = Query(None),
    limit: int = Query(100, le=1000),
    current_user: User = Depends(get_required_user)
):
    """查询权限审计日志"""
    framework = get_permission_framework()
    audit_logger = framework.get_audit_logger()
    
    if not audit_logger:
        raise HTTPException(404, "Audit logging is not enabled")
    
    logs = await audit_logger.query_audit_logs(
        user_id=user_id,
        resource_uri=resource_uri,
        permission=permission,
        result=result,
        limit=limit
    )
    
    return {
        "logs": logs,
        "count": len(logs),
        "filters": {
            "user_id": user_id,
            "resource_uri": resource_uri,
            "permission": permission,
            "result": result
        }
    }

@permission_mgmt.get("/performance/report")
@require_system_permission(Permission.READ)
async def get_performance_report(current_user: User = Depends(get_required_user)):
    """获取权限系统性能报告"""
    framework = get_permission_framework()
    monitor = framework.get_performance_monitor()
    
    if not monitor:
        raise HTTPException(404, "Performance monitoring is not enabled")
    
    return monitor.get_performance_report()

@permission_mgmt.get("/cache/stats")
@require_system_permission(Permission.READ)
async def get_cache_stats(current_user: User = Depends(get_required_user)):
    """获取缓存统计信息"""
    framework = get_permission_framework()
    cache_manager = framework.get_cache_manager()
    
    if not cache_manager:
        raise HTTPException(404, "Cache is not enabled")
    
    return cache_manager.get_cache_stats()

@permission_mgmt.post("/test-permission")
@require_system_permission(Permission.READ)
async def test_permission(
    target_user_id: str = Body(...),
    resource_uri: Optional[str] = Body(None),
    permission: str = Body(...),
    current_user: User = Depends(get_required_user)
):
    """测试指定用户对资源的权限"""
    from src.auth.permission_framework import (
        PermissionEngine, ResourceFactory, ResourceIdentifier, Permission as PermEnum
    )
    
    try:
        # 解析权限
        perm = PermEnum(permission)
        
        # 创建资源（如果提供了资源URI）
        resource = None
        if resource_uri:
            try:
                identifier = ResourceIdentifier.parse(resource_uri)
                resource = ResourceFactory.create_resource(identifier)
            except Exception as e:
                raise HTTPException(400, f"Invalid resource URI: {e}")
        
        # 执行权限检查
        engine = PermissionEngine.get_instance()
        result = await engine.check_permission_simple(target_user_id, resource, perm)
        
        return {
            "user_id": target_user_id,
            "resource_uri": resource_uri,
            "permission": permission,
            "allowed": result,
            "status": "success"
        }
        
    except ValueError as e:
        raise HTTPException(400, f"Invalid permission: {permission}")
    except Exception as e:
        raise HTTPException(500, f"Permission check failed: {e}")

@permission_mgmt.get("/supported-resources")
async def get_supported_resources():
    """获取支持的资源类型"""
    from src.auth.permission_framework import ResourceFactory, ResourceType
    
    supported_types = ResourceFactory.get_supported_types()
    return {
        "supported_types": [rt.value for rt in supported_types],
        "type_descriptions": {
            ResourceType.KNOWLEDGE_BASE.value: "知识库资源",
            ResourceType.CHAT_SESSION.value: "对话会话资源", 
            ResourceType.GRAPH_DATA.value: "图谱数据资源",
            ResourceType.MCP_TOOL.value: "MCP工具资源",
            ResourceType.FILE_SYSTEM.value: "文件系统资源",
            ResourceType.USER_PROFILE.value: "用户资料资源",
            ResourceType.SYSTEM_CONFIG.value: "系统配置资源",
            ResourceType.API_ENDPOINT.value: "API端点资源"
        }
    }

@permission_mgmt.get("/permissions")
async def get_available_permissions():
    """获取可用的权限类型"""
    from src.auth.permission_framework import Permission as PermEnum
    
    return {
        "permissions": [p.value for p in PermEnum],
        "permission_descriptions": {
            PermEnum.READ.value: "读取权限",
            PermEnum.WRITE.value: "写入权限",
            PermEnum.CREATE.value: "创建权限",
            PermEnum.UPDATE.value: "更新权限",
            PermEnum.DELETE.value: "删除权限",
            PermEnum.ADMIN.value: "管理权限",
            PermEnum.EXECUTE.value: "执行权限",
            PermEnum.SHARE.value: "分享权限"
        }
    }