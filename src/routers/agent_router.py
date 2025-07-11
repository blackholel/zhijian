"""
智能体管理 API 路由

提供智能体的完整 REST API 接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from src.agents.manager import agent_manager
from src.agents.config.agent_config import AgentConfig, AgentType
from src.auth.dependencies import get_current_user
from src.auth.decorators.permission_decorators import require_permission
from src.auth.models.user_models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["智能体管理"])


# Pydantic 模型用于 API 请求和响应
from pydantic import BaseModel, Field

class AgentCreateRequest(BaseModel):
    """创建智能体请求"""
    name: str = Field(..., min_length=1, max_length=100, description="智能体名称")
    description: str = Field(..., min_length=1, max_length=500, description="智能体描述")
    agent_type: AgentType = Field(..., description="智能体类型")
    selected_knowledge_bases: List[str] = Field(default_factory=list, description="选中的知识库")
    selected_mcp_tools: List[str] = Field(default_factory=list, description="选中的MCP工具")
    llm_provider: str = Field(default="openai", description="LLM提供商")
    llm_model: str = Field(default="gpt-4", description="LLM模型")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(default=2000, gt=0, description="最大令牌数")
    auto_start: bool = Field(default=False, description="自动启动")
    tags: List[str] = Field(default_factory=list, description="标签")


class AgentUpdateRequest(BaseModel):
    """更新智能体请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="智能体名称")
    description: Optional[str] = Field(None, min_length=1, max_length=500, description="智能体描述")
    selected_knowledge_bases: Optional[List[str]] = Field(None, description="选中的知识库")
    selected_mcp_tools: Optional[List[str]] = Field(None, description="选中的MCP工具")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(None, gt=0, description="最大令牌数")
    tags: Optional[List[str]] = Field(None, description="标签")


class AgentTaskRequest(BaseModel):
    """智能体任务请求"""
    task_type: str = Field(..., description="任务类型")
    task_data: Dict[str, Any] = Field(default_factory=dict, description="任务数据")
    priority: int = Field(default=0, description="优先级")


class AgentResponse(BaseModel):
    """智能体响应"""
    agent_id: str
    name: str
    description: str
    agent_type: str
    status: Dict[str, Any]
    created_at: str
    updated_at: str


@router.post("/create", response_model=Dict[str, Any])
@require_permission("agent:create")
async def create_agent(
    request: AgentCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """创建智能体"""
    try:
        logger.info(f"用户 {current_user.username} 请求创建智能体: {request.name}")
        
        # 构建智能体配置
        from src.agents.config.agent_config import LLMConfig, LLMProvider
        
        llm_config = LLMConfig(
            provider=LLMProvider(request.llm_provider),
            model=request.llm_model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        config = AgentConfig(
            name=request.name,
            description=request.description,
            agent_type=request.agent_type,
            user_id=str(current_user.id),
            selected_knowledge_bases=request.selected_knowledge_bases,
            selected_mcp_tools=request.selected_mcp_tools,
            llm_config=llm_config,
            auto_start=request.auto_start,
            tags=request.tags
        )
        
        # 创建智能体
        agent = await agent_manager.create_agent(config)
        
        # 如果设置了自动启动，则启动智能体
        if request.auto_start:
            await agent_manager.start_agent(agent.agent_id)
        
        return {
            "success": True,
            "agent_id": agent.agent_id,
            "message": "智能体创建成功",
            "status": await agent.get_status()
        }
        
    except Exception as e:
        logger.error(f"创建智能体失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/list", response_model=List[AgentResponse])
async def list_agents(
    agent_type: Optional[AgentType] = Query(None, description="按类型筛选"),
    current_user: User = Depends(get_current_user)
):
    """获取智能体列表"""
    try:
        if agent_type:
            agents = await agent_manager.list_agents_by_type(agent_type, str(current_user.id))
        else:
            agents = await agent_manager.list_agents(str(current_user.id))
        
        responses = []
        for agent in agents:
            status = await agent.get_status()
            responses.append(AgentResponse(
                agent_id=agent.agent_id,
                name=agent.config.name,
                description=agent.config.description,
                agent_type=agent.config.agent_type.value,
                status=status,
                created_at=agent.config.created_at.isoformat(),
                updated_at=agent.config.updated_at.isoformat()
            ))
        
        return responses
        
    except Exception as e:
        logger.error(f"获取智能体列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取智能体详情"""
    try:
        agent = await agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        
        # 验证权限
        if agent.config.user_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="没有权限访问此智能体")
        
        status = await agent.get_status()
        
        return AgentResponse(
            agent_id=agent.agent_id,
            name=agent.config.name,
            description=agent.config.description,
            agent_type=agent.config.agent_type.value,
            status=status,
            created_at=agent.config.created_at.isoformat(),
            updated_at=agent.config.updated_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{agent_id}", response_model=Dict[str, Any])
async def update_agent(
    agent_id: str,
    request: AgentUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """更新智能体配置"""
    try:
        agent = await agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        
        # 验证权限
        if agent.config.user_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="没有权限修改此智能体")
        
        # 构建更新数据
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.description is not None:
            update_data["description"] = request.description
        if request.selected_knowledge_bases is not None:
            update_data["selected_knowledge_bases"] = request.selected_knowledge_bases
        if request.selected_mcp_tools is not None:
            update_data["selected_mcp_tools"] = request.selected_mcp_tools
        if request.temperature is not None:
            update_data["llm_config"] = agent.config.llm_config.dict()
            update_data["llm_config"]["temperature"] = request.temperature
        if request.max_tokens is not None:
            if "llm_config" not in update_data:
                update_data["llm_config"] = agent.config.llm_config.dict()
            update_data["llm_config"]["max_tokens"] = request.max_tokens
        if request.tags is not None:
            update_data["tags"] = request.tags
        
        # 更新智能体
        success = await agent_manager.update_agent_config(agent_id, update_data)
        
        if success:
            return {
                "success": True,
                "message": "智能体更新成功",
                "status": await agent.get_status()
            }
        else:
            raise HTTPException(status_code=400, detail="智能体更新失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新智能体失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{agent_id}", response_model=Dict[str, Any])
async def delete_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user)
):
    """删除智能体"""
    try:
        success = await agent_manager.remove_agent(agent_id, str(current_user.id))
        
        if success:
            return {
                "success": True,
                "message": "智能体删除成功"
            }
        else:
            raise HTTPException(status_code=400, detail="智能体删除失败")
        
    except Exception as e:
        logger.error(f"删除智能体失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/start", response_model=Dict[str, Any])
async def start_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user)
):
    """启动智能体"""
    try:
        agent = await agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        
        # 验证权限
        if agent.config.user_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="没有权限操作此智能体")
        
        success = await agent_manager.start_agent(agent_id)
        
        if success:
            return {
                "success": True,
                "message": "智能体启动成功",
                "status": await agent.get_status()
            }
        else:
            raise HTTPException(status_code=400, detail="智能体启动失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动智能体失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/stop", response_model=Dict[str, Any])
async def stop_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user)
):
    """停止智能体"""
    try:
        agent = await agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        
        # 验证权限
        if agent.config.user_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="没有权限操作此智能体")
        
        success = await agent_manager.stop_agent(agent_id)
        
        if success:
            return {
                "success": True,
                "message": "智能体停止成功",
                "status": await agent.get_status()
            }
        else:
            raise HTTPException(status_code=400, detail="智能体停止失败")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止智能体失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/execute", response_model=Dict[str, Any])
async def execute_agent_task(
    agent_id: str,
    request: AgentTaskRequest,
    current_user: User = Depends(get_current_user)
):
    """执行智能体任务"""
    try:
        # 构建任务数据
        task = {
            "task_id": f"task_{datetime.now().timestamp()}",
            "task_type": request.task_type,
            "priority": request.priority,
            **request.task_data
        }
        
        result = await agent_manager.execute_agent_task(
            agent_id, task, str(current_user.id)
        )
        
        return {
            "success": True,
            "task_id": task["task_id"],
            "result": result
        }
        
    except Exception as e:
        logger.error(f"执行智能体任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}/status", response_model=Dict[str, Any])
async def get_agent_status(
    agent_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取智能体状态"""
    try:
        status = await agent_manager.get_agent_status(agent_id)
        if not status:
            raise HTTPException(status_code=404, detail="智能体不存在")
        
        # 验证权限（通过状态中的用户信息）
        agent = await agent_manager.get_agent(agent_id)
        if agent and agent.config.user_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="没有权限访问此智能体")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取智能体状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/knowledge-bases", response_model=List[Dict[str, Any]])
async def get_available_knowledge_bases(
    current_user: User = Depends(get_current_user)
):
    """获取可用的知识库"""
    try:
        knowledge_bases = await agent_manager.get_available_knowledge_bases(str(current_user.id))
        return knowledge_bases
        
    except Exception as e:
        logger.error(f"获取可用知识库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/mcp-tools", response_model=List[Dict[str, Any]])
async def get_available_mcp_tools(
    current_user: User = Depends(get_current_user)
):
    """获取可用的MCP工具"""
    try:
        mcp_tools = await agent_manager.get_available_mcp_tools(str(current_user.id))
        return mcp_tools
        
    except Exception as e:
        logger.error(f"获取可用MCP工具失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types", response_model=List[Dict[str, str]])
async def get_agent_types():
    """获取智能体类型列表"""
    try:
        types = []
        for agent_type in AgentType:
            types.append({
                "value": agent_type.value,
                "name": agent_type.value.replace("_", " ").title(),
                "description": _get_agent_type_description(agent_type)
            })
        
        return types
        
    except Exception as e:
        logger.error(f"获取智能体类型失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_agent_type_description(agent_type: AgentType) -> str:
    """获取智能体类型描述"""
    descriptions = {
        AgentType.COORDINATOR: "协调器智能体，负责任务分解和流程控制",
        AgentType.RESEARCHER: "研究员智能体，负责信息收集和分析",
        AgentType.ANALYZER: "分析员智能体，负责数据分析和洞察",
        AgentType.REPORTER: "报告员智能体，负责报告生成和总结",
        AgentType.SPECIALIST: "专家智能体，负责特定领域的专业任务",
        AgentType.CUSTOM: "自定义智能体，支持用户自定义功能"
    }
    
    return descriptions.get(agent_type, "智能体类型")


@router.get("/health", response_model=Dict[str, Any])
async def get_agent_health():
    """获取智能体系统健康状态"""
    try:
        all_status = await agent_manager.get_all_agent_status()
        
        total_agents = len(all_status)
        running_agents = len([s for s in all_status.values() if s.get("running")])
        error_agents = len([s for s in all_status.values() if s.get("state") == "error"])
        
        return {
            "total_agents": total_agents,
            "running_agents": running_agents,
            "error_agents": error_agents,
            "health_percentage": (running_agents / total_agents * 100) if total_agents > 0 else 100,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取系统健康状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))