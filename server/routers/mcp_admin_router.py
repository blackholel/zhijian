from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_admin_user, get_db
from src.storage.db.models import MCPMarketplace, User

mcp_admin = APIRouter(prefix="/mcp/admin", tags=["mcp-admin"])


class MarketplaceUpsert(BaseModel):
    mcp_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = ""
    category: str | None = None
    tags: list[str] | None = None
    icon_url: str | None = None

    transport: str = "streamable_http"
    config_template: dict[str, Any] = Field(default_factory=dict)

    author: str | None = None
    version: str | None = None
    homepage_url: str | None = None
    documentation_url: str | None = None
    examples: list[Any] | None = None

    status: str = "active"
    is_official: bool = False


@mcp_admin.post("/marketplace")
async def admin_create_marketplace(
    payload: MarketplaceUpsert = Body(...),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(select(MCPMarketplace).where(MCPMarketplace.mcp_id == payload.mcp_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="mcp_id already exists")

    tool = MCPMarketplace(
        mcp_id=payload.mcp_id,
        name=payload.name,
        description=payload.description or "",
        category=payload.category,
        tags=payload.tags or [],
        icon_url=payload.icon_url,
        transport=payload.transport,
        config_template=payload.config_template or {},
        author=payload.author,
        version=payload.version,
        homepage_url=payload.homepage_url,
        documentation_url=payload.documentation_url,
        examples=payload.examples or [],
        status=payload.status,
        is_official=payload.is_official,
        created_by=current_user.id,
    )
    db.add(tool)
    return {"success": True, "mcp_id": tool.mcp_id}


@mcp_admin.put("/marketplace/{mcp_id}")
async def admin_update_marketplace(
    mcp_id: str,
    payload: MarketplaceUpsert = Body(...),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (await db.execute(select(MCPMarketplace).where(MCPMarketplace.mcp_id == mcp_id))).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool.name = payload.name
    tool.description = payload.description or ""
    tool.category = payload.category
    tool.tags = payload.tags or []
    tool.icon_url = payload.icon_url
    tool.transport = payload.transport
    tool.config_template = payload.config_template or {}
    tool.author = payload.author
    tool.version = payload.version
    tool.homepage_url = payload.homepage_url
    tool.documentation_url = payload.documentation_url
    tool.examples = payload.examples or []
    tool.status = payload.status
    tool.is_official = payload.is_official
    tool.created_by = tool.created_by or current_user.id
    return {"success": True}


@mcp_admin.delete("/marketplace/{mcp_id}")
async def admin_delete_marketplace(
    mcp_id: str, current_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)
):
    tool = (await db.execute(select(MCPMarketplace).where(MCPMarketplace.mcp_id == mcp_id))).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.status == "private":
        raise HTTPException(status_code=400, detail="Cannot delete private tools via admin")
    await db.execute(delete(MCPMarketplace).where(MCPMarketplace.mcp_id == mcp_id))
    return {"success": True}
