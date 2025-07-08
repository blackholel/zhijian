"""
数据库管理API路由

提供统一的数据库状态查询和管理接口
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

from src.database.manager import (
    get_database_manager_dependency,
    get_user_repository_dependency,
    UnifiedDatabaseManager
)
from server.auth.rbac_middleware import get_admin_user, get_superadmin_user
from server.models.user_model import User
from src.utils.logging_config import logger

router = APIRouter(prefix="/database", tags=["Database Management"])


@router.get("/health")
async def get_database_health(
    db_manager: UnifiedDatabaseManager = Depends(get_database_manager_dependency)
) -> Dict[str, Any]:
    """获取数据库健康状态"""
    try:
        health_status = await db_manager.health_check()
        return {
            "success": True,
            "data": health_status
        }
    except Exception as e:
        logger.error(f"Failed to get database health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database health: {str(e)}"
        )


@router.get("/connections")
async def get_database_connections(
    current_user: User = Depends(get_admin_user),
    db_manager: UnifiedDatabaseManager = Depends(get_database_manager_dependency)
) -> Dict[str, Any]:
    """获取数据库连接状态（需要管理员权限）"""
    try:
        connection_summary = db_manager.connection_manager.get_connection_summary()
        return {
            "success": True,
            "data": connection_summary
        }
    except Exception as e:
        logger.error(f"Failed to get database connections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database connections: {str(e)}"
        )


@router.get("/adapters")
async def get_database_adapters(
    current_user: User = Depends(get_admin_user),
    db_manager: UnifiedDatabaseManager = Depends(get_database_manager_dependency)
) -> Dict[str, Any]:
    """获取数据库适配器信息（需要管理员权限）"""
    try:
        adapters_info = {}
        
        # 获取所有适配器的连接信息
        adapter_names = ['server_db', 'lightrag_db', 'neo4j', 'redis', 'milvus', 'minio']
        
        for adapter_name in adapter_names:
            try:
                adapter = await db_manager.connection_manager.get_adapter(adapter_name)
                if adapter:
                    info = await adapter.get_connection_info()
                    metrics = adapter.get_metrics()
                    adapters_info[adapter_name] = {
                        "connection_info": info,
                        "metrics": metrics,
                        "status": "available"
                    }
                else:
                    adapters_info[adapter_name] = {
                        "status": "not_available"
                    }
            except Exception as e:
                adapters_info[adapter_name] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "success": True,
            "data": adapters_info
        }
    except Exception as e:
        logger.error(f"Failed to get database adapters: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database adapters: {str(e)}"
        )


@router.post("/reconnect")
async def reconnect_databases(
    current_user: User = Depends(get_superadmin_user),
    db_manager: UnifiedDatabaseManager = Depends(get_database_manager_dependency)
) -> Dict[str, Any]:
    """重连所有数据库（需要超级管理员权限）"""
    try:
        reconnect_results = await db_manager.connection_manager.reconnect_all()
        
        return {
            "success": True,
            "data": {
                "reconnect_results": reconnect_results,
                "message": "Database reconnection completed"
            }
        }
    except Exception as e:
        logger.error(f"Failed to reconnect databases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reconnect databases: {str(e)}"
        )


@router.get("/config")
async def get_database_config(
    current_user: User = Depends(get_admin_user),
    db_manager: UnifiedDatabaseManager = Depends(get_database_manager_dependency)
) -> Dict[str, Any]:
    """获取数据库配置信息（需要管理员权限）"""
    try:
        config_info = {
            "environment": db_manager.config_manager.environment,
            "available_databases": db_manager.config_manager.get_all_database_names(),
            "config_validation": {}
        }
        
        # 验证所有数据库配置
        for db_name in config_info["available_databases"]:
            try:
                is_valid = db_manager.config_manager.validate_database_config(db_name)
                config_info["config_validation"][db_name] = {
                    "valid": is_valid,
                    "status": "valid" if is_valid else "invalid"
                }
            except Exception as e:
                config_info["config_validation"][db_name] = {
                    "valid": False,
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "success": True,
            "data": config_info
        }
    except Exception as e:
        logger.error(f"Failed to get database config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database config: {str(e)}"
        )


@router.get("/repositories")
async def get_repository_status(
    current_user: User = Depends(get_admin_user),
    db_manager: UnifiedDatabaseManager = Depends(get_database_manager_dependency)
) -> Dict[str, Any]:
    """获取仓储状态（需要管理员权限）"""
    try:
        repository_status = {}
        
        # 检查各个仓储的健康状态
        repositories = [
            ("user", db_manager.get_user_repository()),
            ("knowledge", db_manager.get_knowledge_repository()),
            ("graph", db_manager.get_graph_repository()),
            ("file", db_manager.get_file_repository())
        ]
        
        for repo_name, repo in repositories:
            try:
                health = await repo.health_check()
                repository_status[repo_name] = health
            except Exception as e:
                repository_status[repo_name] = {
                    "status": "error",
                    "error": str(e),
                    "repository": repo.__class__.__name__
                }
        
        return {
            "success": True,
            "data": repository_status
        }
    except Exception as e:
        logger.error(f"Failed to get repository status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get repository status: {str(e)}"
        )


# 用户仓储示例接口

@router.get("/users/count")
async def get_user_count(
    user_repo = Depends(get_user_repository_dependency)
) -> Dict[str, Any]:
    """获取用户数量"""
    try:
        count = await user_repo.count()
        return {
            "success": True,
            "data": {
                "user_count": count
            }
        }
    except Exception as e:
        logger.error(f"Failed to get user count: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user count: {str(e)}"
        )


@router.get("/users/statistics")
async def get_user_statistics(
    current_user: User = Depends(get_admin_user),
    user_repo = Depends(get_user_repository_dependency)
) -> Dict[str, Any]:
    """获取用户统计信息（需要管理员权限）"""
    try:
        stats = await user_repo.get_user_statistics()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"Failed to get user statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user statistics: {str(e)}"
        )