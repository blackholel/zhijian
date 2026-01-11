"""内置智能体同步服务 - 将代码定义的智能体同步到数据库"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.db.models import Agent
from src.utils import logger


async def sync_builtin_agents(db: AsyncSession) -> None:
    """
    同步系统内置智能体到数据库

    策略：
    1. 遍历代码中注册的所有智能体
    2. 检查数据库中是否存在对应记录
    3. 不存在则创建，存在则更新元数据（不覆盖用户可能的修改）
    """
    from src.agents import agent_manager

    code_agents = agent_manager.get_agents()

    # 批量查询所有已存在的内置智能体（避免 N+1 查询）
    stmt = select(Agent).where(Agent.agent_type == "builtin")
    result = await db.execute(stmt)
    existing_agents = {a.agent_id: a for a in result.scalars().all()}

    for code_agent in code_agents:
        agent_id = code_agent.id  # 类名，如 ChatbotAgent
        existing = existing_agents.get(agent_id)

        # 获取智能体信息
        info = await code_agent.get_info()

        if existing:
            # 更新元数据（保留用户可能的自定义）
            existing.name = info.get("name", existing.name)
            existing.description = info.get("description", existing.description)
            existing.capabilities = info.get("capabilities", [])
            existing.examples = info.get("examples", [])
            logger.info(f"Updated builtin agent: {agent_id}")
        else:
            # 创建新记录
            new_agent = Agent(
                agent_id=agent_id,
                name=info.get("name", agent_id),
                description=info.get("description", ""),
                agent_type="builtin",
                owner_id=None,
                base_agent_id=agent_id,  # 内置智能体的 base 就是自己
                capabilities=info.get("capabilities", []),
                examples=info.get("examples", []),
                visibility="public",
                status="active",
            )
            db.add(new_agent)
            logger.info(f"Created builtin agent: {agent_id}")

    await db.commit()
    logger.info("Builtin agents sync completed")


async def on_startup_sync_agents():
    """应用启动时同步内置智能体"""
    from src.storage.db.manager import db_manager

    async with db_manager.get_async_session_context() as db:
        await sync_builtin_agents(db)
