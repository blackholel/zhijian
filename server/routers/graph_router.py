import json
import os
import asyncio
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException, Depends, Body
from pydantic import BaseModel

from server.auth.middleware.rbac_middleware import get_required_user, get_admin_user
from server.auth.permission_framework import (
    require_kb_permission, require_system_permission, Permission
)
from server.auth.models.user_models import User
from src import knowledge_base
from src.core.graph_adapter import get_unified_graph_adapter
from src.database.manager import get_database_manager_dependency
from src.database.repositories.graph_repository import GraphTriple
from src.utils.logging_config import logger

graph = APIRouter(prefix="/graph")


# Pydantic模型
class CreateTripleRequest(BaseModel):
    head: str
    relation: str
    tail: str


class CreateTriplesRequest(BaseModel):
    kb_id: str
    triples: List[CreateTripleRequest]


class EntityQueryRequest(BaseModel):
    kb_id: str
    entity_name: str
    hops: int = 2
    limit: int = 100


def get_user_id(user: User) -> str:
    """获取用户ID，优先使用external_user_id（外部JWT用户）"""
    return getattr(user, 'external_user_id', None) or str(user.id)


# 新的基于权限控制的图数据库API

@graph.post("/triples")
@require_kb_permission(Permission.WRITE)
async def create_graph_triples(
    request: CreateTriplesRequest = Body(...),
    current_user: User = Depends(get_required_user),
    graph_adapter = Depends(get_unified_graph_adapter)
):
    """
    创建图数据库三元组（需要知识库写入权限）
    """
    try:
        user_id = get_user_id(current_user)
        kb_id = request.kb_id
        
        logger.info(f"创建图三元组 - user_id: {user_id}, kb_id: {kb_id}, triples_count: {len(request.triples)}")
        
        # 转换为内部格式
        triples = []
        for triple_req in request.triples:
            triples.append({
                'h': triple_req.head,
                'r': triple_req.relation,
                't': triple_req.tail
            })
        
        # 使用统一图适配器创建三元组
        success = await graph_adapter.txt_add_entity_with_user(user_id, kb_id, triples)
        
        if success:
            return {
                "success": True,
                "message": f"成功创建 {len(triples)} 个三元组",
                "data": {
                    "kb_id": kb_id,
                    "triples_count": len(triples)
                }
            }
        else:
            raise HTTPException(status_code=500, detail="创建三元组失败")
            
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"创建图三元组失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建图三元组失败: {str(e)}")


@graph.post("/query")
@require_kb_permission(Permission.READ)
async def query_graph_entities(
    request: EntityQueryRequest = Body(...),
    current_user: User = Depends(get_required_user),
    graph_adapter = Depends(get_unified_graph_adapter)
):
    """
    查询图数据库实体（需要知识库读取权限）
    """
    try:
        user_id = get_user_id(current_user)
        kb_id = request.kb_id
        
        logger.info(f"查询图实体 - user_id: {user_id}, kb_id: {kb_id}, entity: {request.entity_name}")
        
        # 使用统一图适配器查询实体
        results = await graph_adapter.query_user_entities(
            user_id, kb_id, request.entity_name, request.hops, request.limit
        )
        
        return {
            "success": True,
            "data": {
                "kb_id": kb_id,
                "entity_name": request.entity_name,
                "results": results,
                "count": len(results)
            }
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"查询图实体失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询图实体失败: {str(e)}")


@graph.get("/entities")
@require_system_permission(Permission.READ)
async def get_user_accessible_entities(
    kb_ids: Optional[str] = Query(None, description="知识库ID列表（逗号分隔）"),
    current_user: User = Depends(get_required_user),
    graph_adapter = Depends(get_unified_graph_adapter)
):
    """
    获取用户可访问的图实体列表
    """
    try:
        user_id = get_user_id(current_user)
        kb_id_list = kb_ids.split(',') if kb_ids else None
        
        logger.info(f"获取用户可访问实体 - user_id: {user_id}, kb_ids: {kb_id_list}")
        
        # 获取用户可访问的实体
        entities = await graph_adapter.get_user_accessible_entities(user_id, kb_id_list)
        
        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "kb_ids": kb_id_list,
                "entities": [entity.to_dict() for entity in entities],
                "count": len(entities)
            }
        }
        
    except Exception as e:
        logger.error(f"获取用户可访问实体失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取用户可访问实体失败: {str(e)}")


@graph.post("/kb/{kb_id}/vector-index")
@require_kb_permission(Permission.WRITE)
async def create_vector_index(
    kb_id: str,
    dimension: int = Query(1024, description="向量维度"),
    current_user: User = Depends(get_required_user),
    graph_adapter = Depends(get_unified_graph_adapter)
):
    """
    为知识库创建向量索引（需要知识库写入权限）
    """
    try:
        user_id = get_user_id(current_user)
        
        logger.info(f"创建向量索引 - user_id: {user_id}, kb_id: {kb_id}, dimension: {dimension}")
        
        success = await graph_adapter.create_vector_index_for_kb(user_id, kb_id, dimension)
        
        if success:
            return {
                "success": True,
                "message": f"成功为知识库 {kb_id} 创建向量索引",
                "data": {
                    "kb_id": kb_id,
                    "dimension": dimension
                }
            }
        else:
            raise HTTPException(status_code=500, detail="创建向量索引失败")
            
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"创建向量索引失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建向量索引失败: {str(e)}")


@graph.get("/kb/{kb_id}/statistics")
@require_kb_permission(Permission.READ)
async def get_kb_graph_statistics(
    kb_id: str,
    current_user: User = Depends(get_required_user),
    graph_adapter = Depends(get_unified_graph_adapter)
):
    """
    获取知识库图数据统计（需要知识库读取权限）
    """
    try:
        user_id = get_user_id(current_user)
        
        logger.info(f"获取知识库图统计 - user_id: {user_id}, kb_id: {kb_id}")
        
        stats = await graph_adapter.get_kb_statistics(user_id, kb_id)
        
        return {
            "success": True,
            "data": stats
        }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"获取知识库图统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取知识库图统计失败: {str(e)}")


@graph.delete("/kb/{kb_id}")
@require_kb_permission(Permission.DELETE)
async def delete_kb_graph_data(
    kb_id: str,
    current_user: User = Depends(get_required_user),
    graph_adapter = Depends(get_unified_graph_adapter)
):
    """
    删除知识库的所有图数据（需要知识库删除权限）
    """
    try:
        user_id = get_user_id(current_user)
        
        logger.info(f"删除知识库图数据 - user_id: {user_id}, kb_id: {kb_id}")
        
        success = await graph_adapter.delete_kb_data(user_id, kb_id)
        
        if success:
            return {
                "success": True,
                "message": f"成功删除知识库 {kb_id} 的图数据",
                "data": {
                    "kb_id": kb_id
                }
            }
        else:
            raise HTTPException(status_code=500, detail="删除图数据失败")
            
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"删除知识库图数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除知识库图数据失败: {str(e)}")


# 兼容性API - LightRAG子图查询（保留原有功能）

@graph.get("/subgraph")
@require_kb_permission(Permission.READ)
async def get_subgraph_lightrag(
    db_id: str = Query(..., description="数据库ID"),
    node_label: str = Query(..., description="节点标签或实体名称"),
    max_depth: int = Query(2, description="最大深度", ge=1, le=5),
    max_nodes: int = Query(100, description="最大节点数", ge=1, le=1000),
    current_user: User = Depends(get_required_user)
):
    """
    使用 LightRAG 原生方法获取知识图谱子图（需要知识库读取权限）
    """
    try:
        user_id = get_user_id(current_user)
        logger.info(f"获取LightRAG子图数据 - user_id: {user_id}, db_id: {db_id}, node_label: {node_label}")

        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"数据库 {db_id} 不存在")

        # 使用 LightRAG 的原生 get_knowledge_graph 方法
        knowledge_graph = await rag_instance.get_knowledge_graph(
            node_label=node_label,
            max_depth=max_depth,
            max_nodes=max_nodes
        )

        # 将 LightRAG 的 KnowledgeGraph 格式转换为前端需要的格式
        nodes = []
        for node in knowledge_graph.nodes:
            nodes.append({
                "id": node.id,
                "labels": node.labels,
                "entity_type": node.properties.get("entity_type", "unknown"),
                "properties": node.properties
            })

        edges = []
        for edge in knowledge_graph.edges:
            edges.append({
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "type": edge.type,
                "properties": edge.properties
            })

        result = {
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges,
                "is_truncated": knowledge_graph.is_truncated,
                "total_nodes": len(nodes),
                "total_edges": len(edges)
            }
        }

        logger.info(f"成功获取LightRAG子图 - 节点数: {len(nodes)}, 边数: {len(edges)}")
        return result

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"获取LightRAG子图数据失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取LightRAG子图数据失败: {str(e)}")


# 系统管理相关API

@graph.get("/health")
async def get_graph_health(
    current_user: User = Depends(get_required_user),
    graph_adapter = Depends(get_unified_graph_adapter)
):
    """
    获取图数据库健康状态
    """
    try:
        health = await graph_adapter.health_check()
        return {
            "success": True,
            "data": health
        }
    except Exception as e:
        logger.error(f"获取图数据库健康状态失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": {"status": "error"}
        }


@graph.get("/databases")
@require_system_permission(Permission.READ)
async def get_available_databases(
    current_user: User = Depends(get_required_user)
):
    """
    获取所有可用的数据库列表（需要系统读取权限）
    """
    try:
        user_id = get_user_id(current_user)
        logger.info(f"获取数据库列表 - user_id: {user_id}")
        
        # 获取用户可访问的知识库
        from src.database.manager import get_database_manager_dependency
        db_manager = await get_database_manager_dependency()
        kb_repo = db_manager.get_knowledge_repository()
        
        accessible_kbs = await kb_repo.get_user_accessible_kbs(user_id)
        
        return {
            "success": True,
            "data": {
                "databases": [
                    {
                        "db_id": kb.db_id,
                        "name": kb.name,
                        "description": kb.description,
                        "owner_id": kb.owner_id,
                        "is_public": kb.is_public
                    } for kb in accessible_kbs
                ],
                "count": len(accessible_kbs)
            }
        }

    except Exception as e:
        logger.error(f"获取数据库列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取数据库列表失败: {str(e)}")


# 健康检查和监控API

@graph.get("/system/status")
@require_system_permission(Permission.READ)
async def get_system_status(
    current_user: User = Depends(get_required_user)
):
    """
    获取图数据库系统状态（需要系统读取权限）
    """
    try:
        user_id = get_user_id(current_user)
        logger.info(f"获取系统状态 - user_id: {user_id}")
        
        from src.database.manager import get_database_manager_dependency
        db_manager = await get_database_manager_dependency()
        
        # 获取数据库健康状态
        health_status = await db_manager.health_check()
        
        # 获取Neo4j连接信息
        neo4j_adapter = await db_manager.get_neo4j_adapter()
        neo4j_info = await neo4j_adapter.get_connection_info() if neo4j_adapter else {}
        
        return {
            "success": True,
            "data": {
                "overall_status": health_status.get("status", "unknown"),
                "neo4j_connection": neo4j_info,
                "unified_manager": {
                    "initialized": db_manager._initialized,
                    "environment": db_manager.config_manager.environment
                },
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取系统状态失败: {str(e)}")


# 向后兼容的统计API (LightRAG)

@graph.get("/lightrag/{db_id}/stats")
@require_kb_permission(Permission.READ)
async def get_lightrag_stats(
    db_id: str,
    current_user: User = Depends(get_required_user)
):
    """
    获取LightRAG知识图谱统计信息（需要知识库读取权限）
    """
    try:
        user_id = get_user_id(current_user)
        logger.info(f"获取LightRAG图谱统计 - user_id: {user_id}, db_id: {db_id}")

        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"数据库 {db_id} 不存在")

        # 通过获取全图来统计节点和边的数量
        knowledge_graph = await rag_instance.get_knowledge_graph(
            node_label="*",
            max_depth=1,
            max_nodes=10000  # 设置较大值以获取完整统计
        )

        # 统计实体类型分布
        entity_types = {}
        for node in knowledge_graph.nodes:
            entity_type = node.properties.get("entity_type", "unknown")
            entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

        entity_types_list = [
            {"type": k, "count": v}
            for k, v in sorted(entity_types.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "success": True,
            "data": {
                "db_id": db_id,
                "total_nodes": len(knowledge_graph.nodes),
                "total_edges": len(knowledge_graph.edges),
                "entity_types": entity_types_list,
                "is_truncated": knowledge_graph.is_truncated,
                "user_id": user_id
            }
        }

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"获取LightRAG图谱统计失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取LightRAG图谱统计失败: {str(e)}")
