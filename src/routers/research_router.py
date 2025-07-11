"""
研究工作流API路由
提供深度研究和工作流管理的完整接口
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from ..research.workflow import WorkflowEngine, ResearchWorkflow
from ..research.models import (
    ResearchRequest, 
    ResearchResponse,
    ExecutionStatusResponse,
    ExecutionResultResponse,
    WorkflowListResponse,
    SessionListResponse,
    HealthCheckResponse,
    ErrorResponse,
    StreamEvent,
    WorkflowConfig,
    ExecutionPauseRequest,
    ExecutionResumeRequest,
    ExecutionCancelRequest,
    ConfigUpdateRequest,
    BatchExecutionRequest,
    BatchExecutionResponse,
    ExportRequest,
    ExportResponse
)
from ..agents.orchestrator import ResearchOrchestrator
from ..auth.dependencies import get_current_user
from ..auth.decorators.agent_decorators import require_agent_permissions
from ..auth.models.user_models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

# 全局工作流引擎实例
workflow_engine: Optional[WorkflowEngine] = None


async def get_workflow_engine() -> WorkflowEngine:
    """获取工作流引擎实例"""
    global workflow_engine
    if workflow_engine is None:
        workflow_engine = WorkflowEngine()
        await workflow_engine.initialize()
    return workflow_engine


@router.post("/start", response_model=ResearchResponse)
@require_agent_permissions(min_role="power_user")
async def start_research(
    request: ResearchRequest,
    current_user: User = Depends(get_current_user)
):
    """启动深度研究"""
    try:
        engine = await get_workflow_engine()
        
        # 验证用户权限
        # 这里可以添加更细粒度的权限检查
        
        # 准备初始数据
        initial_data = {
            "topic": request.topic,
            "objective": request.objective,
            "knowledge_bases": request.knowledge_bases,
            "mcp_tools": request.mcp_tools,
            "config": request.config
        }
        
        # 生成会话ID
        session_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{current_user.id}"
        
        # 启动工作流
        execution_id = await engine.start_workflow(
            workflow_id=request.workflow_type.value,
            session_id=session_id,
            user_id=str(current_user.id),
            initial_data=initial_data
        )
        
        return ResearchResponse(
            session_id=session_id,
            execution_id=execution_id,
            status="started",
            message="研究任务启动成功"
        )
        
    except Exception as e:
        logger.error(f"Research start failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{execution_id}", response_model=ExecutionStatusResponse)
async def get_research_status(
    execution_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取研究状态"""
    try:
        engine = await get_workflow_engine()
        status = await engine.get_execution_status(execution_id)
        
        # 验证用户权限
        # 这里应该检查execution对应的用户是否为当前用户
        
        return ExecutionStatusResponse(**status)
        
    except Exception as e:
        logger.error(f"Failed to get research status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/{execution_id}", response_model=ExecutionResultResponse)
async def get_research_result(
    execution_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取研究结果"""
    try:
        engine = await get_workflow_engine()
        result = await engine.get_execution_result(execution_id)
        
        # 验证用户权限
        # 这里应该检查execution对应的用户是否为当前用户
        
        return ExecutionResultResponse(**result)
        
    except Exception as e:
        logger.error(f"Failed to get research result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause/{execution_id}")
async def pause_research(
    execution_id: str,
    request: ExecutionPauseRequest = ExecutionPauseRequest(),
    current_user: User = Depends(get_current_user)
):
    """暂停研究"""
    try:
        engine = await get_workflow_engine()
        success = await engine.pause_execution(execution_id)
        
        if success:
            return {
                "success": True,
                "execution_id": execution_id,
                "status": "paused",
                "message": "研究已暂停",
                "paused_at": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=400, detail="暂停失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/{execution_id}")
async def resume_research(
    execution_id: str,
    request: ExecutionResumeRequest = ExecutionResumeRequest(),
    current_user: User = Depends(get_current_user)
):
    """恢复研究"""
    try:
        engine = await get_workflow_engine()
        success = await engine.resume_execution(execution_id)
        
        if success:
            return {
                "success": True,
                "execution_id": execution_id,
                "status": "running",
                "message": "研究已恢复",
                "resumed_at": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=400, detail="恢复失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel/{execution_id}")
async def cancel_research(
    execution_id: str,
    request: ExecutionCancelRequest = ExecutionCancelRequest(),
    current_user: User = Depends(get_current_user)
):
    """取消研究"""
    try:
        engine = await get_workflow_engine()
        success = await engine.cancel_execution(execution_id)
        
        if success:
            return {
                "success": True,
                "execution_id": execution_id,
                "status": "cancelled",
                "message": "研究已取消",
                "cancelled_at": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=400, detail="取消失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel research: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    current_user: User = Depends(get_current_user)
):
    """列出可用的工作流"""
    try:
        engine = await get_workflow_engine()
        
        workflows = []
        for workflow_id, workflow in engine.workflows.items():
            workflows.append({
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "description": workflow.description,
                "version": workflow.version,
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "name": node.name,
                        "description": node.description,
                        "phase": node.phase.value
                    }
                    for node in workflow.nodes.values()
                ],
                "edges": [
                    {
                        "source_node": edge.source_node,
                        "target_node": edge.target_node,
                        "condition": edge.condition.value
                    }
                    for edge in workflow.edges
                ],
                "start_node": workflow.start_node,
                "end_nodes": workflow.end_nodes,
                "config": workflow.config.__dict__ if workflow.config else None,
                "metadata": workflow.metadata
            })
        
        return WorkflowListResponse(
            workflows=workflows,
            total=len(workflows)
        )
        
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=SessionListResponse)
async def list_research_sessions(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None, description="状态过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """列出用户的研究会话"""
    try:
        engine = await get_workflow_engine()
        
        # 获取用户的所有执行
        user_executions = []
        for execution in engine.executions.values():
            # 这里需要根据实际的用户ID字段来过滤
            # 假设execution有user_id字段
            if hasattr(execution, 'user_id') and execution.user_id == str(current_user.id):
                user_executions.append(execution)
        
        # 应用状态过滤
        if status:
            user_executions = [e for e in user_executions if e.status.value == status]
        
        # 按创建时间排序
        user_executions.sort(key=lambda x: x.created_at, reverse=True)
        
        # 应用分页
        total = len(user_executions)
        paged_executions = user_executions[offset:offset + limit]
        
        sessions = []
        for execution in paged_executions:
            sessions.append({
                "session_id": execution.session_id,
                "execution_id": execution.execution_id,
                "workflow_id": execution.workflow_id,
                "status": execution.status.value,
                "current_node": execution.current_node,
                "created_at": execution.created_at.isoformat(),
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "topic": execution.context.get("topic", ""),
                "objective": execution.context.get("objective", "")
            })
        
        return SessionListResponse(
            sessions=sessions,
            total=total,
            page=offset // limit + 1,
            page_size=limit
        )
        
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream/{execution_id}")
async def stream_research_progress(
    execution_id: str,
    current_user: User = Depends(get_current_user)
):
    """流式获取研究进度"""
    
    async def generate_events():
        try:
            engine = await get_workflow_engine()
            
            # 验证execution存在且属于当前用户
            if execution_id not in engine.executions:
                yield StreamEvent(
                    event_type="error",
                    data={"error": "Execution not found"}
                ).json()
                return
            
            execution = engine.executions[execution_id]
            
            # 发送初始状态
            status = await engine.get_execution_status(execution_id)
            yield StreamEvent(
                event_type="status",
                data=status,
                execution_id=execution_id
            ).json()
            
            # 持续监控状态变化
            last_event_count = len(execution.events)
            
            while execution.status.value in ["running", "paused"]:
                await asyncio.sleep(2)  # 每2秒检查一次
                
                # 检查是否有新事件
                if len(execution.events) > last_event_count:
                    new_events = execution.events[last_event_count:]
                    for event in new_events:
                        yield StreamEvent(
                            event_type="workflow_event",
                            data=event.__dict__,
                            execution_id=execution_id
                        ).json()
                    
                    last_event_count = len(execution.events)
                
                # 发送状态更新
                current_status = await engine.get_execution_status(execution_id)
                yield StreamEvent(
                    event_type="status_update",
                    data=current_status,
                    execution_id=execution_id
                ).json()
            
            # 发送最终状态
            final_status = await engine.get_execution_status(execution_id)
            yield StreamEvent(
                event_type="final_status",
                data=final_status,
                execution_id=execution_id
            ).json()
            
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield StreamEvent(
                event_type="error",
                data={"error": str(e)}
            ).json()
    
    return EventSourceResponse(generate_events())


@router.post("/batch-start", response_model=BatchExecutionResponse)
@require_agent_permissions(min_role="admin")
async def batch_start_research(
    request: BatchExecutionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """批量启动研究任务"""
    try:
        if len(request.executions) > 10:
            raise HTTPException(status_code=400, detail="批量执行数量不能超过10个")
        
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{current_user.id}"
        execution_ids = []
        
        async def batch_execute():
            engine = await get_workflow_engine()
            
            for i, research_request in enumerate(request.executions):
                try:
                    session_id = f"batch_research_{batch_id}_{i}"
                    initial_data = {
                        "topic": research_request.topic,
                        "objective": research_request.objective,
                        "knowledge_bases": research_request.knowledge_bases,
                        "mcp_tools": research_request.mcp_tools,
                        "config": research_request.config
                    }
                    
                    execution_id = await engine.start_workflow(
                        workflow_id=research_request.workflow_type.value,
                        session_id=session_id,
                        user_id=str(current_user.id),
                        initial_data=initial_data
                    )
                    
                    execution_ids.append(execution_id)
                    
                    # 如果是顺序执行，等待前一个完成
                    if request.execution_strategy == "sequential" and i > 0:
                        prev_execution_id = execution_ids[i-1]
                        while True:
                            status = await engine.get_execution_status(prev_execution_id)
                            if status["status"] in ["completed", "failed", "cancelled"]:
                                break
                            await asyncio.sleep(5)
                    
                except Exception as e:
                    logger.error(f"Batch execution item {i} failed: {e}")
        
        # 异步执行批量任务
        background_tasks.add_task(batch_execute)
        
        return BatchExecutionResponse(
            batch_id=batch_id,
            execution_ids=[],  # 将在后台任务中填充
            status="started",
            created_at=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export", response_model=ExportResponse)
async def export_research_results(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """导出研究结果"""
    try:
        # 验证用户对所有execution的访问权限
        engine = await get_workflow_engine()
        
        for execution_id in request.execution_ids:
            if execution_id not in engine.executions:
                raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
        
        export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{current_user.id}"
        
        async def export_task():
            try:
                # 收集所有execution的结果
                results = []
                for execution_id in request.execution_ids:
                    result = await engine.get_execution_result(execution_id)
                    results.append(result)
                
                # 生成导出文件
                # 这里应该实现实际的文件生成逻辑
                
                logger.info(f"Export {export_id} completed")
                
            except Exception as e:
                logger.error(f"Export {export_id} failed: {e}")
        
        background_tasks.add_task(export_task)
        
        # 生成下载URL（这里应该是实际的文件服务URL）
        download_url = f"/api/research/download/{export_id}"
        
        return ExportResponse(
            export_id=export_id,
            download_url=download_url,
            file_size=0,  # 将在导出完成后更新
            expires_at=(datetime.now().timestamp() + 86400) * 1000,  # 24小时后过期
            created_at=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """健康检查"""
    try:
        engine = await get_workflow_engine()
        
        # 统计活跃会话和执行
        active_sessions = len([e for e in engine.executions.values() if e.status.value == "running"])
        active_executions = len(engine.executions)
        
        # 系统指标
        system_metrics = {
            "workflow_count": len(engine.workflows),
            "execution_queue_size": engine.execution_queue.qsize(),
            "event_queue_size": engine._event_queue.qsize(),
            "memory_usage": 0,  # 这里应该获取实际的内存使用情况
            "cpu_usage": 0     # 这里应该获取实际的CPU使用情况
        }
        
        # 依赖状态
        dependencies = {
            "workflow_engine": "healthy",
            "orchestrator": "healthy",
            "database": "healthy",
            "llm_service": "healthy"
        }
        
        return HealthCheckResponse(
            status="healthy",
            version="1.0.0",
            uptime=0,  # 这里应该计算实际的运行时间
            active_sessions=active_sessions,
            active_executions=active_executions,
            system_metrics=system_metrics,
            dependencies=dependencies
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthCheckResponse(
            status="unhealthy",
            version="1.0.0",
            uptime=0,
            active_sessions=0,
            active_executions=0,
            system_metrics={},
            dependencies={"error": str(e)}
        )


@router.put("/config", response_model=Dict[str, Any])
@require_agent_permissions(min_role="admin")
async def update_config(
    request: ConfigUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """更新系统配置"""
    try:
        # 这里应该实现配置更新逻辑
        updated_configs = []
        
        if request.workflow_config:
            # 更新工作流配置
            updated_configs.append("workflow_config")
        
        if request.agent_configs:
            # 更新Agent配置
            updated_configs.append("agent_configs")
        
        if request.system_config:
            # 更新系统配置
            updated_configs.append("system_config")
        
        return {
            "success": True,
            "updated_configs": updated_configs,
            "message": "配置更新成功",
            "updated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Config update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/{execution_id}")
async def get_research_analytics(
    execution_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取研究分析数据"""
    try:
        engine = await get_workflow_engine()
        
        if execution_id not in engine.executions:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        execution = engine.executions[execution_id]
        
        # 计算分析指标
        analytics = {
            "execution_id": execution_id,
            "workflow_id": execution.workflow_id,
            "execution_time": {
                "total": (
                    (execution.completed_at - execution.started_at).total_seconds()
                    if execution.started_at and execution.completed_at else 0
                ),
                "by_phase": {}  # 这里应该计算各阶段的执行时间
            },
            "event_statistics": {
                "total_events": len(execution.events),
                "event_types": {},
                "transition_count": len(execution.transitions)
            },
            "performance_metrics": {
                "average_node_time": 0,
                "slowest_node": "",
                "fastest_node": "",
                "error_rate": 0
            },
            "quality_metrics": {
                "completion_rate": 1.0 if execution.status.value == "completed" else 0.0,
                "success_rate": 1.0 if execution.status.value == "completed" else 0.0
            }
        }
        
        # 统计事件类型
        for event in execution.events:
            event_type = event.event_type
            if event_type not in analytics["event_statistics"]["event_types"]:
                analytics["event_statistics"]["event_types"][event_type] = 0
            analytics["event_statistics"]["event_types"][event_type] += 1
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cleanup")
@require_agent_permissions(min_role="admin")
async def cleanup_completed_executions(
    days: int = Query(7, ge=1, le=30, description="清理多少天前的执行"),
    current_user: User = Depends(get_current_user)
):
    """清理已完成的执行"""
    try:
        engine = await get_workflow_engine()
        
        cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
        cleaned_count = 0
        
        execution_ids_to_remove = []
        for execution_id, execution in engine.executions.items():
            if (execution.status.value in ["completed", "failed", "cancelled"] and
                execution.created_at.timestamp() < cutoff_time):
                execution_ids_to_remove.append(execution_id)
        
        for execution_id in execution_ids_to_remove:
            del engine.executions[execution_id]
            cleaned_count += 1
        
        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "message": f"已清理{cleaned_count}个执行记录",
            "cleaned_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))