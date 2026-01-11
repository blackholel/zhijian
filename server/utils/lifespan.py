import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.services import tasker
from src.agents import agent_manager
from src.agents.sync_service import on_startup_sync_agents
from src.storage.db.manager import db_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await tasker.start()
    """FastAPI lifespan事件管理器"""
    await asyncio.to_thread(db_manager.create_tables)
    # 同步内置智能体到数据库
    await on_startup_sync_agents()
    yield
    await tasker.shutdown()
    for agent in agent_manager.get_agents():
        await agent.aclose()
