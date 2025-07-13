"""
企业级智能体API路由
提供完整的企业级智能体管理功能
"""

import asyncio
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from datetime import datetime

from server.auth.auth_middleware import verify_token
from server.auth.rbac_middleware import require_permission
from server.models.user_model import User
from server.auth.permission_framework.decorators import require_system_permission
from src.agents.enterprise_manager import get_enterprise_agent_manager, AgentSession
from src.agents.enterprise_base import EnterpriseAgentContext
from src.utils import logger


# 请求/响应模型
class CreateSessionRequest(BaseModel):
    agent_name: str = Field(..., description="智能体名称")
    organization_id: Optional[str] = Field(None, description="组织ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="会话元数据")


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    agent_name: str
    thread_id: str
    created_at: datetime
    last_activity: datetime
    organization_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    message: str = Field(..., description="消息内容")
    config: Optional[Dict[str, Any]] = Field(None, description="配置参数")


class AgentInfoResponse(BaseModel):
    name: str
    description: str
    config_schema: Dict[str, Any]
    requirements: List[str]
    enterprise_features: Dict[str, Any]
    metrics: Dict[str, Any]


class SystemMetricsResponse(BaseModel):
    total_sessions: int
    active_sessions: int
    total_agents: int
    agent_metrics: Dict[str, Any]
    system_health: Dict[str, Any]


# 创建路由
router = APIRouter(prefix="/api/enterprise/agents", tags=["企业级智能体"])


@router.get("/", response_model=List[str])
@require_system_permission("agent_list")
async def list_agents(current_user: User = Depends(verify_token)):
    """列出所有可用的企业级智能体"""
    try:
        manager = await get_enterprise_agent_manager()
        agents = await manager.list_agents()
        return agents
    except Exception as e:
        logger.error(f"列出智能体失败: {e}")
        raise HTTPException(status_code=500, detail="获取智能体列表失败")


@router.get("/{agent_name}/info", response_model=AgentInfoResponse)
@require_system_permission("agent_info")
async def get_agent_info(agent_name: str, current_user: User = Depends(verify_token)):
    """获取智能体详细信息"""
    try:
        manager = await get_enterprise_agent_manager()
        info = await manager.get_agent_info(agent_name)
        
        if not info:
            raise HTTPException(status_code=404, detail=f"智能体 {agent_name} 不存在")
        
        return AgentInfoResponse(**info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体信息失败: {e}")
        raise HTTPException(status_code=500, detail="获取智能体信息失败")


@router.post("/sessions", response_model=SessionResponse)
@require_system_permission("agent_session_create")
async def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(verify_token)
):
    """创建智能体会话"""
    try:
        manager = await get_enterprise_agent_manager()
        
        session = await manager.create_session(
            user_id=current_user.id,
            agent_name=request.agent_name,
            organization_id=request.organization_id,
            metadata=request.metadata
        )
        
        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            agent_name=session.agent_name,
            thread_id=session.thread_id,
            created_at=session.created_at,
            last_activity=session.last_activity,
            organization_id=session.organization_id,
            metadata=session.metadata
        )
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise HTTPException(status_code=500, detail="创建会话失败")


@router.get("/sessions", response_model=List[SessionResponse])
@require_system_permission("agent_session_list")
async def list_user_sessions(current_user: User = Depends(verify_token)):
    """列出用户的所有会话"""
    try:
        manager = await get_enterprise_agent_manager()
        sessions = await manager.list_user_sessions(current_user.id)
        
        return [
            SessionResponse(
                session_id=session.session_id,
                user_id=session.user_id,
                agent_name=session.agent_name,
                thread_id=session.thread_id,
                created_at=session.created_at,
                last_activity=session.last_activity,
                organization_id=session.organization_id,
                metadata=session.metadata
            )
            for session in sessions
        ]
        
    except Exception as e:
        logger.error(f"获取用户会话失败: {e}")
        raise HTTPException(status_code=500, detail="获取用户会话失败")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
@require_system_permission("agent_session_view")
async def get_session(session_id: str, current_user: User = Depends(verify_token)):
    """获取会话信息"""
    try:
        manager = await get_enterprise_agent_manager()
        session = await manager.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")
        
        # 检查用户权限
        if session.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            agent_name=session.agent_name,
            thread_id=session.thread_id,
            created_at=session.created_at,
            last_activity=session.last_activity,
            organization_id=session.organization_id,
            metadata=session.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话信息失败: {e}")
        raise HTTPException(status_code=500, detail="获取会话信息失败")


@router.post("/sessions/{session_id}/messages")
@require_system_permission("agent_message_send")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    current_user: User = Depends(verify_token)
):
    """发送消息到智能体（流式响应）"""
    try:
        manager = await get_enterprise_agent_manager()
        session = await manager.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")
        
        # 检查用户权限
        if session.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        async def message_generator():
            """消息生成器"""
            try:
                async for msg, metadata in manager.send_message(
                    session_id, request.message, request.config
                ):
                    if hasattr(msg, 'content'):
                        yield f"data: {msg.content}\n\n"
                    elif hasattr(msg, 'tool_calls'):
                        yield f"data: [工具调用] {msg.tool_calls}\n\n"
                    else:
                        yield f"data: {str(msg)}\n\n"
                        
                yield "data: [DONE]\n\n"
                
            except Exception as e:
                logger.error(f"消息处理错误: {e}")
                yield f"data: [ERROR] {str(e)}\n\n"
        
        return StreamingResponse(
            message_generator(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        raise HTTPException(status_code=500, detail="发送消息失败")


@router.get("/sessions/{session_id}/history")
@require_system_permission("agent_session_history")
async def get_session_history(
    session_id: str,
    current_user: User = Depends(verify_token)
):
    """获取会话历史记录"""
    try:
        manager = await get_enterprise_agent_manager()
        session = await manager.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")
        
        # 检查用户权限
        if session.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        history = await manager.get_session_history(session_id)
        return {"session_id": session_id, "history": history}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话历史失败: {e}")
        raise HTTPException(status_code=500, detail="获取会话历史失败")


@router.delete("/sessions/{session_id}")
@require_system_permission("agent_session_delete")
async def delete_session(
    session_id: str,
    current_user: User = Depends(verify_token)
):
    """删除会话"""
    try:
        manager = await get_enterprise_agent_manager()
        session = await manager.get_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")
        
        # 检查用户权限
        if session.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        await manager.cleanup_session(session_id)
        return {"message": "会话已删除"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail="删除会话失败")


@router.get("/metrics", response_model=SystemMetricsResponse)
@require_system_permission("agent_metrics")
async def get_system_metrics(current_user: User = Depends(verify_token)):
    """获取系统指标"""
    try:
        manager = await get_enterprise_agent_manager()
        metrics = await manager.get_system_metrics()
        
        return SystemMetricsResponse(**metrics)
        
    except Exception as e:
        logger.error(f"获取系统指标失败: {e}")
        raise HTTPException(status_code=500, detail="获取系统指标失败")


@router.post("/cleanup")
@require_system_permission("agent_admin")
async def cleanup_expired_sessions(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(verify_token)
):
    """清理过期会话"""
    try:
        manager = await get_enterprise_agent_manager()
        
        # 在后台任务中执行清理
        async def cleanup_task():
            await manager.cleanup_expired_sessions()
        
        background_tasks.add_task(cleanup_task)
        
        return {"message": "清理任务已启动"}
        
    except Exception as e:
        logger.error(f"清理过期会话失败: {e}")
        raise HTTPException(status_code=500, detail="清理过期会话失败")


@router.get("/health")
async def health_check():
    """健康检查"""
    try:
        manager = await get_enterprise_agent_manager()
        health = await manager._get_system_health()
        
        # 检查关键组件
        is_healthy = all(
            status == "healthy" 
            for status in health.values() 
            if isinstance(status, str)
        )
        
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "details": health,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# WebSocket支持（可选）
@router.websocket("/sessions/{session_id}/ws")
async def websocket_endpoint(websocket, session_id: str):
    """WebSocket端点（可选实现）"""
    await websocket.accept()
    
    try:
        # 这里可以实现WebSocket的实时通信
        # 由于需要处理认证，这里先提供基本框架
        
        while True:
            data = await websocket.receive_text()
            
            # 处理消息...
            response = f"收到消息: {data}"
            await websocket.send_text(response)
            
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        await websocket.close(code=1000)


# 管理员专用端点
@router.post("/admin/register-agent")
@require_system_permission("agent_admin")
async def register_new_agent(
    agent_config: Dict[str, Any],
    current_user: User = Depends(verify_token)
):
    """注册新的智能体（管理员功能）"""
    try:
        # 这里可以实现动态注册智能体的功能
        # 需要根据配置创建智能体实例
        
        return {"message": "功能开发中"}
        
    except Exception as e:
        logger.error(f"注册智能体失败: {e}")
        raise HTTPException(status_code=500, detail="注册智能体失败")


@router.get("/admin/audit-logs")
@require_system_permission("agent_admin")
async def get_audit_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_name: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(verify_token)
):
    """获取审计日志（管理员功能）"""
    try:
        # 这里可以实现审计日志查询功能
        # 需要从数据库中查询审计记录
        
        return {"message": "功能开发中"}
        
    except Exception as e:
        logger.error(f"获取审计日志失败: {e}")
        raise HTTPException(status_code=500, detail="获取审计日志失败")


# 导出路由
__all__ = ["router"] 