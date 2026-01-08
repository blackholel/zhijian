from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from src.storage.db.models import MCPMarketplace, MCPRating, User

mcp_market = APIRouter(prefix="/mcp-market", tags=["mcp-market"])


class MarketToolListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[dict]


@mcp_market.get("/tools", response_model=MarketToolListResponse)
async def list_market_tools(
    category: str | None = Query(None),
    search: str | None = Query(None),
    sort: Literal["popular", "latest", "rating"] = Query("popular"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MCPMarketplace).where(MCPMarketplace.status == "active")
    if category:
        stmt = stmt.where(MCPMarketplace.category == category)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where((MCPMarketplace.name.ilike(like)) | (MCPMarketplace.description.ilike(like)))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await db.execute(count_stmt)).scalar() or 0)

    if sort == "latest":
        stmt = stmt.order_by(MCPMarketplace.created_at.desc())
    elif sort == "rating":
        stmt = stmt.order_by(func.coalesce(MCPMarketplace.rating_avg, 0).desc(), MCPMarketplace.rating_count.desc())
    else:
        stmt = stmt.order_by(MCPMarketplace.install_count.desc(), MCPMarketplace.created_at.desc())

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        {
            "mcp_id": row.mcp_id,
            "name": row.name,
            "description": row.description,
            "category": row.category,
            "status": row.status,
            "icon_url": row.icon_url,
            "install_count": row.install_count,
            "rating_avg": row.rating_avg,
            "rating_count": row.rating_count,
            "author": row.author,
            "version": row.version,
            "is_official": row.is_official,
        }
        for row in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@mcp_market.get("/tools/{mcp_id}")
async def get_market_tool_detail(mcp_id: str, db: AsyncSession = Depends(get_db)):
    tool = (
        await db.execute(
            select(MCPMarketplace).where(MCPMarketplace.mcp_id == mcp_id, MCPMarketplace.status == "active")
        )
    ).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {
        "mcp_id": tool.mcp_id,
        "name": tool.name,
        "description": tool.description,
        "category": tool.category,
        "tags": tool.tags or [],
        "icon_url": tool.icon_url,
        "transport": tool.transport,
        "config_template": tool.config_template or {},
        "author": tool.author,
        "version": tool.version,
        "homepage_url": tool.homepage_url,
        "documentation_url": tool.documentation_url,
        "examples": tool.examples or [],
        "status": tool.status,
        "is_official": tool.is_official,
        "install_count": tool.install_count,
        "rating_avg": tool.rating_avg,
        "rating_count": tool.rating_count,
        "created_at": tool.created_at,
        "updated_at": tool.updated_at,
    }


@mcp_market.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(MCPMarketplace.category, func.count().label("count"))
        .where(MCPMarketplace.status == "active")
        .group_by(MCPMarketplace.category)
        .order_by(func.count().desc())
    )
    rows = (await db.execute(stmt)).all()
    items = [{"category": category, "count": int(count)} for category, count in rows if category]
    return {"items": items}


class RatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


@mcp_market.post("/tools/{mcp_id}/rating")
async def submit_rating(
    mcp_id: str,
    payload: RatingRequest = Body(...),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(
            select(MCPMarketplace).where(MCPMarketplace.mcp_id == mcp_id, MCPMarketplace.status == "active")
        )
    ).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")

    existing = (
        await db.execute(select(MCPRating).where(MCPRating.mcp_id == mcp_id, MCPRating.user_id == current_user.id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(MCPRating(mcp_id=mcp_id, user_id=current_user.id, rating=payload.rating, comment=payload.comment))
    else:
        existing.rating = payload.rating
        existing.comment = payload.comment

    await db.flush()
    stats_stmt = select(func.avg(MCPRating.rating), func.count(MCPRating.id)).where(MCPRating.mcp_id == mcp_id)
    avg_rating, count_rating = (await db.execute(stats_stmt)).one()
    tool.rating_avg = float(avg_rating) if avg_rating is not None else None
    tool.rating_count = int(count_rating or 0)
    return {"success": True, "rating_avg": tool.rating_avg, "rating_count": tool.rating_count}
