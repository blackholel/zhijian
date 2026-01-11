"""智能体管理 API 路由"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from src.storage.db.models import Agent, MCPMarketplace, User, UserMCPConfig
from src.utils import logger

agent_manage = APIRouter(prefix="/agents", tags=["agent-manage"])

# 允许更新的字段白名单
_ALLOWED_UPDATE_FIELDS = {
    "name",
    "description",
    "icon",
    "system_prompt",
    "model",
    "tools",
    "mcps",
    "knowledges",
    "examples",
    "visibility",
}


# ==================== Pydantic 模型 ====================


class AgentCreate(BaseModel):
    """创建智能体请求"""

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)
    icon: str | None = Field(None, max_length=512)
    base_agent_id: str = "ChatbotAgent"
    system_prompt: str | None = Field(None, max_length=50000)
    model: str | None = None
    tools: list[str] | None = None
    mcps: list[str] | None = None
    knowledges: list[str] | None = None
    examples: list[str] | None = None
    visibility: Literal["private", "public"] = "private"


class AgentUpdate(BaseModel):
    """更新智能体请求"""

    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=2000)
    icon: str | None = Field(None, max_length=512)
    system_prompt: str | None = Field(None, max_length=50000)
    model: str | None = None
    tools: list[str] | None = None
    mcps: list[str] | None = None
    knowledges: list[str] | None = None
    examples: list[str] | None = None
    visibility: Literal["private", "public"] | None = None


# ==================== 辅助函数 ====================


async def _validate_knowledges_access(
    knowledges: list[str] | None,
    user_id: int,
    is_admin: bool = False,
) -> None:
    """验证用户对知识库的访问权限"""
    if not knowledges:
        return

    from src.knowledge import knowledge_base

    for db_id in knowledges:
        db_info = knowledge_base.get_database_info(db_id)
        if db_info is None:
            raise HTTPException(status_code=400, detail=f"知识库 {db_id} 不存在")

        if is_admin:
            continue

        # 默认拒绝：只有明确的所有者才能访问
        owner_user_id = db_info.get("owner_user_id")
        if owner_user_id is None or owner_user_id != user_id:
            raise HTTPException(status_code=403, detail=f"无权访问知识库 {db_id}")


async def _validate_mcps_access(
    db: AsyncSession,
    mcps: list[str] | None,
    user_id: int,
) -> None:
    """验证用户对 MCP 配置的访问权限"""
    if not mcps:
        return

    for mcp_ref in mcps:
        # MCP 引用格式: user_{config_id} 或直接是 mcp_id（市场 MCP）
        if mcp_ref.startswith("user_"):
            # 用户自定义 MCP 配置
            try:
                config_id = int(mcp_ref.replace("user_", ""))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的 MCP 配置引用: {mcp_ref}")

            stmt = select(UserMCPConfig).where(
                UserMCPConfig.id == config_id,
                UserMCPConfig.user_id == user_id,
            )
            result = await db.execute(stmt)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=403, detail=f"无权访问 MCP 配置 {mcp_ref}")
        else:
            # 市场 MCP，验证是否存在且可用
            stmt = select(MCPMarketplace).where(
                MCPMarketplace.mcp_id == mcp_ref,
                MCPMarketplace.status == "active",
            )
            result = await db.execute(stmt)
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail=f"无效的 MCP: {mcp_ref}")


async def _get_agent_with_permission(
    db: AsyncSession,
    agent_id: str,
    user_id: int,
    require_owner: bool = False,
) -> Agent:
    """获取智能体并检查权限"""
    stmt = select(Agent).where(Agent.agent_id == agent_id, Agent.status == "active")
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")

    # 权限检查
    has_access = agent.agent_type == "builtin" or agent.owner_id == user_id or agent.visibility == "public"

    if not has_access:
        raise HTTPException(status_code=403, detail="无权访问此智能体")

    if require_owner and agent.owner_id != user_id:
        raise HTTPException(status_code=403, detail="只有创建者可以执行此操作")

    return agent


# ==================== API 端点 ====================


@agent_manage.get("/base-agents")
async def list_base_agents(
    current_user: User = Depends(get_required_user),
):
    """获取可用的底层智能体列表（用于创建自定义智能体时选择）"""
    from src.agents import agent_manager

    base_agents = []
    for agent in agent_manager.get_agents():
        base_agents.append(
            {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description or "",
            }
        )

    return {"base_agents": base_agents}


@agent_manage.get("")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """获取用户可见的智能体列表"""
    user_id = current_user.id

    # 查询条件：内置智能体 OR 自己创建的 OR 公开的
    stmt = (
        select(Agent)
        .where(
            Agent.status == "active",
            or_(
                Agent.agent_type == "builtin",
                Agent.owner_id == user_id,
                Agent.visibility == "public",
            ),
        )
        .order_by(Agent.agent_type.desc(), Agent.created_at.desc())
    )

    result = await db.execute(stmt)
    agents = result.scalars().all()

    # 分组返回
    builtin_agents = []
    my_agents = []
    public_agents = []

    for agent in agents:
        agent_dict = agent.to_dict()
        agent_dict["is_owner"] = agent.owner_id == user_id

        if agent.agent_type == "builtin":
            builtin_agents.append(agent_dict)
        elif agent.owner_id == user_id:
            my_agents.append(agent_dict)
        else:
            public_agents.append(agent_dict)

    return {
        "builtin": builtin_agents,
        "my_agents": my_agents,
        "public": public_agents,
    }


@agent_manage.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """获取单个智能体详情"""
    agent = await _get_agent_with_permission(db, agent_id, current_user.id)
    result = agent.to_dict(include_config=True)
    result["is_owner"] = agent.owner_id == current_user.id
    return result


@agent_manage.post("")
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """创建自定义智能体"""
    # 验证用户对知识库和 MCP 的访问权限
    is_admin = current_user.role == "admin"
    await _validate_knowledges_access(data.knowledges, current_user.id, is_admin)
    await _validate_mcps_access(db, data.mcps, current_user.id)

    # 生成唯一 agent_id
    agent_id = f"custom_{uuid.uuid4().hex[:12]}"

    # 验证 base_agent_id 是否有效
    from src.agents import agent_manager

    try:
        base_agent = agent_manager.get_agent(data.base_agent_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"无效的底层智能体: {data.base_agent_id}")

    # 获取底层智能体的 capabilities
    capabilities = getattr(base_agent, "capabilities", [])

    agent = Agent(
        agent_id=agent_id,
        name=data.name,
        description=data.description,
        icon=data.icon,
        agent_type="custom",
        owner_id=current_user.id,
        base_agent_id=data.base_agent_id,
        system_prompt=data.system_prompt,
        model=data.model,
        tools=data.tools or [],
        mcps=data.mcps or [],
        knowledges=data.knowledges or [],
        capabilities=capabilities,
        examples=data.examples or [],
        visibility=data.visibility,
        status="active",
    )

    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info(f"User {current_user.id} created agent {agent_id}")

    result = agent.to_dict(include_config=True)
    result["is_owner"] = True
    return result


@agent_manage.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    data: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """更新智能体配置"""
    agent = await _get_agent_with_permission(db, agent_id, current_user.id, require_owner=True)

    # 内置智能体不允许修改
    if agent.agent_type == "builtin":
        raise HTTPException(status_code=403, detail="内置智能体不允许修改")

    # 验证用户对知识库和 MCP 的访问权限
    is_admin = current_user.role == "admin"
    await _validate_knowledges_access(data.knowledges, current_user.id, is_admin)
    await _validate_mcps_access(db, data.mcps, current_user.id)

    # 更新字段（使用白名单过滤）
    update_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _ALLOWED_UPDATE_FIELDS}
    for key, value in update_fields.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)

    logger.info(f"User {current_user.id} updated agent {agent_id}")

    result = agent.to_dict(include_config=True)
    result["is_owner"] = True
    return result


@agent_manage.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """删除智能体（软删除）"""
    agent = await _get_agent_with_permission(db, agent_id, current_user.id, require_owner=True)

    if agent.agent_type == "builtin":
        raise HTTPException(status_code=403, detail="内置智能体不允许删除")

    agent.status = "deleted"
    await db.commit()

    logger.info(f"User {current_user.id} deleted agent {agent_id}")

    return {"message": "删除成功"}


@agent_manage.post("/{agent_id}/duplicate")
async def duplicate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """复制智能体"""
    source_agent = await _get_agent_with_permission(db, agent_id, current_user.id)

    # 生成新的 agent_id
    new_agent_id = f"custom_{uuid.uuid4().hex[:12]}"

    # 判断是否为自己的智能体
    is_own_agent = source_agent.owner_id == current_user.id

    # 如果复制的是其他用户的智能体，清除敏感配置（mcps 和 knowledges）
    # 因为这些资源可能是用户私有的，复制者可能没有访问权限
    new_agent = Agent(
        agent_id=new_agent_id,
        name=f"{source_agent.name} (副本)",
        description=source_agent.description,
        icon=source_agent.icon,
        agent_type="custom",
        owner_id=current_user.id,
        base_agent_id=source_agent.base_agent_id,
        system_prompt=source_agent.system_prompt,
        model=source_agent.model,
        tools=source_agent.tools or [],
        mcps=source_agent.mcps or [] if is_own_agent else [],
        knowledges=source_agent.knowledges or [] if is_own_agent else [],
        capabilities=source_agent.capabilities or [],
        examples=source_agent.examples or [],
        visibility="private",
        status="active",
    )

    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    logger.info(f"User {current_user.id} duplicated agent {agent_id} to {new_agent_id}")

    result = new_agent.to_dict(include_config=True)
    result["is_owner"] = True
    return result
