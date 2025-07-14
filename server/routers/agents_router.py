"""
企业级智能体路由器

基于重构后的智能体系统，提供完整的权限控制、用户上下文管理和企业级功能。
集成统一数据库管理、权限框架和知识库系统。
"""

import asyncio
import json
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from src.utils.logging_config import logger
from server.auth.rbac_middleware import get_required_user, get_admin_user
from server.models.user_model import User
from src.agents.context import UserContext
from src.agents.dependencies import get_agent_dependencies

# 创建智能体路由器
agents = APIRouter(prefix="/agents", tags=["智能体管理"])

# ==================== 请求响应模型 ====================

class AgentExecuteRequest(BaseModel):
    """智能体执行请求"""
    agent_name: str = Field(..., description="智能体名称")
    messages: List[Dict[str, str]] = Field(..., description="消息列表")
    config: Optional[Dict[str, Any]] = Field(None, description="运行时配置")
    stream: bool = Field(False, description="是否流式返回")
    stream_mode: str = Field("messages", description="流模式: messages 或 values")

class AgentConfigRequest(BaseModel):
    """智能体配置请求"""
    model: Optional[str] = Field(None, description="模型名称")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(None, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大令牌数")
    tools: Optional[List[str]] = Field(None, description="工具列表")

class AgentInfoResponse(BaseModel):
    """智能体信息响应"""
    name: str
    description: str
    status: str
    permissions: Optional[Dict[str, bool]] = None
    available_tools: Optional[List[str]] = None

class ClearCacheRequest(BaseModel):
    """清除缓存请求"""
    cache_type: str = Field("all", description="缓存类型: all, instances, tools")
    user_id: Optional[str] = Field(None, description="目标用户ID（管理员可用）")

# ==================== 智能体信息API ====================

@agents.get("/info")
async def get_agents_info(
    current_user: User = Depends(get_required_user)
) -> List[AgentInfoResponse]:
    """
    获取智能体信息 - 权限过滤
    
    返回用户有权限访问的智能体列表，包含权限信息和可用工具。
    """
    try:
        # 创建用户上下文
        user_context = UserContext.from_user_sync(current_user)
        
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        await dependencies.ensure_initialized()
        
        agent_manager = await dependencies.agent_manager
        
        # 获取智能体信息（自动权限过滤）
        agents_info = await agent_manager.get_agents_info(user_context)
        
        # 转换为响应格式
        response = []
        for agent_info in agents_info:
            response.append(AgentInfoResponse(
                name=agent_info.get("name", "unknown"),
                description=agent_info.get("description", ""),
                status=agent_info.get("status", "unknown"),
                permissions=agent_info.get("permissions", {}),
                available_tools=agent_info.get("available_tools", []),
                config=agent_info.get("config", {})
            ))
        
        logger.info(f"用户 {current_user.id} 获取智能体信息，返回 {len(response)} 个智能体")
        return response
        
    except Exception as e:
        logger.error(f"获取智能体信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取智能体信息失败: {str(e)}")

@agents.get("/{agent_name}/info")
async def get_agent_info(
    agent_name: str,
    current_user: User = Depends(get_required_user)
) -> AgentInfoResponse:
    """
    获取特定智能体信息
    
    返回指定智能体的详细信息，需要访问权限。
    """
    try:
        # 创建用户上下文
        user_context = UserContext.from_user_sync(current_user)
        
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        await dependencies.ensure_initialized()
        
        agent_manager = await dependencies.agent_manager
        
        # 获取智能体实例（自动权限检查）
        agent = await agent_manager.get_agent(agent_name, user_context)
        agent_info = await agent.get_info()
        
        # 获取用户可用工具
        available_tools = await agent_manager.get_available_tools(user_context)
        
        return AgentInfoResponse(
            name=agent_info.get("name", agent_name),
            description=agent_info.get("description", ""),
            status=agent_info.get("status", "ready"),
            permissions={
                "access": True,  # 能获取到说明有访问权限
                "execute": await agent_manager._check_agent_permission(user_context, agent_name, "execute")
            },
            available_tools=list(available_tools.keys()),
            config=agent_info.get("config", {})
        )
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取智能体 {agent_name} 信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取智能体信息失败: {str(e)}")

# ==================== 智能体执行API ====================

@agents.post("/chat")
async def execute_agent(
    request: AgentExecuteRequest,
    current_user: User = Depends(get_required_user)
):
    """
    执行智能体 - 企业级权限控制
    
    支持流式和非流式响应，自动进行权限检查和工具过滤。
    """
    try:
        # 创建用户上下文
        user_context = UserContext.from_user_sync(current_user)
        
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        await dependencies.ensure_initialized()
        
        agent_manager = await dependencies.agent_manager
        
        # 构建运行配置
        from langchain_core.runnables import RunnableConfig
        config = request.config or {}
        
        # 构建符合LangGraph要求的RunnableConfig
        runnable_config = RunnableConfig(
            configurable={
                "user_id": current_user.id,
                "thread_id": config.get("thread_id") or str(uuid.uuid4()),
                **config  # 合并请求中的配置
            }
        )
        
        if request.stream:
            # 流式响应
            return StreamingResponse(
                _stream_agent_response(
                    agent_manager,
                    request.agent_name,
                    request.messages,
                    user_context,
                    runnable_config,
                    request.stream_mode
                ),
                media_type='application/json'
            )
        else:
            # 非流式响应
            result = await agent_manager.execute_agent(
                request.agent_name,
                request.messages,
                user_context,
                runnable_config,
                stream_mode=request.stream_mode,
                stream=False
            )
            
            return {
                "success": True,
                "agent_name": request.agent_name,
                "result": result,
                "config": runnable_config
            }
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"执行智能体 {request.agent_name} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行智能体失败: {str(e)}")

async def _stream_agent_response(
    agent_manager,
    agent_name: str,
    messages: List[Dict[str, str]],
    user_context: UserContext,
    config: RunnableConfig,
    stream_mode: str
):
    """智能体流式响应生成器"""
    
    def make_chunk(**kwargs):
        return json.dumps(kwargs, ensure_ascii=False).encode('utf-8') + b"\n"
    
    try:
        # 发送初始状态
        yield make_chunk(
            status="init",
            agent_name=agent_name,
            user_id=user_context.user_id,
            config=getattr(config, 'configurable', {}) if config else {}
        )
        
        # 执行智能体
        stream_generator = await agent_manager.execute_agent(
            agent_name, messages, user_context, config, stream_mode, stream=True
        )
        async for chunk in stream_generator:
            if hasattr(chunk, 'content'):
                yield make_chunk(
                    status="streaming",
                    content=chunk.content,
                    chunk_type=type(chunk).__name__
                )
            else:
                yield make_chunk(
                    status="streaming",
                    data=chunk
                )
        
        # 发送完成状态
        yield make_chunk(status="finished")
        
    except Exception as e:
        logger.error(f"智能体流式执行失败: {e}")
        yield make_chunk(
            status="error",
            error=str(e)
        )

# ==================== 工具管理API ====================

@agents.get("/tools/available")
async def get_available_tools(
    current_user: User = Depends(get_required_user)
) -> Dict[str, List[str]]:
    """
    获取用户可用工具
    
    返回用户有权限使用的所有工具，按类别分组。
    """
    try:
        # 创建用户上下文
        user_context = UserContext.from_user_sync(current_user)
        
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        await dependencies.ensure_initialized()
        
        agent_manager = await dependencies.agent_manager
        
        # 获取用户可用工具
        available_tools = await agent_manager.get_available_tools(user_context)
        
        # 按类别分组
        categorized_tools = {
            "basic": [],
            "knowledge": [],
            "web": [],
            "other": []
        }
        
        for tool_name in available_tools.keys():
            if tool_name in ["calculator", "query_knowledge_graph"]:
                categorized_tools["basic"].append(tool_name)
            elif tool_name.startswith("retrieve_"):
                categorized_tools["knowledge"].append(tool_name)
            elif "web" in tool_name.lower() or "search" in tool_name.lower():
                categorized_tools["web"].append(tool_name)
            else:
                categorized_tools["other"].append(tool_name)
        
        logger.info(f"用户 {current_user.id} 获取可用工具，共 {len(available_tools)} 个")
        return categorized_tools
        
    except Exception as e:
        logger.error(f"获取用户可用工具失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取可用工具失败: {str(e)}")

# ==================== 配置管理API ====================

@agents.get("/{agent_name}/config")
async def get_agent_config(
    agent_name: str,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """
    获取智能体配置
    
    返回用户对该智能体的个性化配置。
    """
    try:
        # 创建用户上下文
        user_context = UserContext.from_user_sync(current_user)
        
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        await dependencies.ensure_initialized()
        
        agent_manager = await dependencies.agent_manager
        
        # 获取智能体实例（自动权限检查）
        agent = await agent_manager.get_agent(agent_name, user_context)
        
        # 获取配置
        config = await agent.config_schema.from_runnable_config(
            config={},
            agent_name=agent_name,
            user_context=user_context
        )
        
        logger.info(f"用户 {current_user.id} 获取智能体 {agent_name} 配置")
        return config.__dict__ if hasattr(config, '__dict__') else config
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"获取智能体 {agent_name} 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")

@agents.put("/{agent_name}/config")
async def update_agent_config(
    agent_name: str,
    config: AgentConfigRequest,
    current_user: User = Depends(get_admin_user)  # 需要管理员权限
) -> Dict[str, Any]:
    """
    更新智能体配置
    
    管理员专用，更新智能体的全局配置。
    """
    try:
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        await dependencies.ensure_initialized()
        
        agent_manager = await dependencies.agent_manager
        
        # 获取智能体实例
        user_context = UserContext.from_user(current_user)
        agent = await agent_manager.get_agent(agent_name, user_context)
        
        # 更新配置
        config_dict = config.dict(exclude_none=True)
        result = agent.config_schema.save_to_file(config_dict, agent_name)
        
        if result:
            logger.info(f"管理员 {current_user.id} 更新智能体 {agent_name} 配置")
            return {
                "success": True,
                "message": f"智能体 {agent_name} 配置已更新",
                "config": config_dict
            }
        else:
            raise HTTPException(status_code=500, detail="配置保存失败")
        
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"更新智能体 {agent_name} 配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")

# ==================== 缓存管理API ====================

@agents.post("/cache/clear")
async def clear_cache(
    request: ClearCacheRequest,
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """
    清除用户缓存
    
    普通用户只能清除自己的缓存，管理员可以清除指定用户的缓存。
    """
    try:
        # 确定目标用户
        target_user_id = request.user_id
        if target_user_id and target_user_id != current_user.id:
            # 需要管理员权限才能清除其他用户缓存
            if not current_user.is_admin:
                raise HTTPException(status_code=403, detail="无权限清除其他用户缓存")
        else:
            target_user_id = current_user.id
        
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        await dependencies.ensure_initialized()
        
        agent_manager = await dependencies.agent_manager
        
        # 清除缓存
        if request.cache_type in ["all", "instances"]:
            agent_manager.clear_user_cache(target_user_id)
        
        if request.cache_type in ["all", "tools"]:
            tools_factory = agent_manager._tools_factory
            if tools_factory:
                tools_factory.clear_cache(target_user_id)
        
        logger.info(f"用户 {current_user.id} 清除了用户 {target_user_id} 的 {request.cache_type} 缓存")
        return {
            "success": True,
            "message": f"已清除用户 {target_user_id} 的 {request.cache_type} 缓存"
        }
        
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"清除缓存失败: {str(e)}")

# ==================== 系统管理API ====================

@agents.get("/health")
async def health_check(
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """
    智能体系统健康检查
    
    返回智能体系统的健康状态和统计信息。
    """
    try:
        # 获取智能体管理器
        dependencies = get_agent_dependencies()
        
        # 基础健康检查
        health_status = await dependencies.health_check()
        
        # 智能体管理器健康检查
        if dependencies._agent_manager:
            agent_manager = await dependencies.agent_manager
            agent_health = await agent_manager.health_check()
            health_status["agent_manager"] = agent_health
        
        logger.debug(f"用户 {current_user.id} 请求智能体系统健康检查")
        return health_status
        
    except Exception as e:
        logger.error(f"智能体系统健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")

@agents.post("/reinitialize")
async def reinitialize_agents(
    current_user: User = Depends(get_admin_user)  # 需要管理员权限
) -> Dict[str, Any]:
    """
    重新初始化智能体管理器
    
    管理员专用，用于系统维护和故障恢复。
    """
    try:
        # 获取依赖管理器
        dependencies = get_agent_dependencies()
        
        # 重新初始化
        await dependencies.initialize_all()
        
        # 获取新状态
        health_status = await dependencies.health_check()
        
        logger.info(f"管理员 {current_user.id} 重新初始化智能体系统")
        return {
            "success": True,
            "message": "智能体系统已重新初始化",
            "health": health_status
        }
        
    except Exception as e:
        logger.error(f"重新初始化智能体系统失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新初始化失败: {str(e)}")

# ==================== 根路由 ====================

@agents.get("/")
async def agents_root(
    current_user: User = Depends(get_required_user)
) -> Dict[str, Any]:
    """
    智能体系统根路由
    
    返回系统基本信息和用户权限概要。
    """
    try:
        # 创建用户上下文
        user_context = UserContext.from_user_sync(current_user)
        
        # 获取基本信息
        dependencies = get_agent_dependencies()
        health = await dependencies.health_check()
        
        return {
            "system": "Enterprise Agent System",
            "version": "2.0.0",
            "user": {
                "id": user_context.user_id,
                "username": user_context.username,
                "roles": user_context.roles,
                "permissions_count": len(user_context.permissions)
            },
            "status": health.get("overall", False),
            "message": "企业级智能体系统已就绪"
        }
        
    except Exception as e:
        logger.error(f"获取智能体系统信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"系统信息获取失败: {str(e)}")

# ==================== 路由器导出 ====================

# 为了兼容性，同时导出 agents 和 router
router = agents