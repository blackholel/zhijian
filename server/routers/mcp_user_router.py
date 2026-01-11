from __future__ import annotations

import asyncio
import ipaddress
import socket
import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from src.agents.common.mcp import clear_mcp_cache, get_mcp_tools
from src.storage.db.models import MCPMarketplace, User, UserMCPConfig
from src.utils import logger
from src.utils.mcp_utils import build_env_status, decrypt_env_values, encrypt_env_values

mcp_user = APIRouter(prefix="/mcp/user", tags=["mcp-user"])


def _is_private_or_reserved_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, link-local, or otherwise reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return False


def _validate_streamable_http_url(raw_url: str) -> None:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="url must start with http/https")
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(status_code=422, detail="url host is required")

    # Block localhost and .local domains
    if host in {"localhost"} or host.endswith(".local"):
        raise HTTPException(status_code=422, detail="localhost/.local is not allowed")

    # Check if host is an IP address directly
    if _is_private_or_reserved_ip(host):
        raise HTTPException(status_code=422, detail="private/reserved IP addresses are not allowed")

    # Resolve hostname and check all resolved IPs
    try:
        resolved_ips = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            if _is_private_or_reserved_ip(ip_str):
                raise HTTPException(status_code=422, detail="hostname resolves to private/reserved IP")
    except socket.gaierror:
        # DNS resolution failed - allow the request (will fail at connection time)
        pass


def _validate_stdio_command(command: str) -> None:
    if command not in {"npx", "uvx"}:
        raise HTTPException(status_code=422, detail="Only npx/uvx are allowed for stdio MCP")


def _infer_transport(config: dict[str, Any]) -> str:
    transport = config.get("transport")
    if transport in {"streamable_http", "stdio"}:
        return transport
    if config.get("url"):
        return "streamable_http"
    if config.get("command"):
        return "stdio"
    raise HTTPException(status_code=422, detail="transport/url/command is required")


def _normalize_args(args: Any) -> list[str] | None:
    if args is None:
        return None
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise HTTPException(status_code=422, detail="args must be a list of strings")
    return args


def _normalize_env(env: Any) -> dict[str, object]:
    if env is None:
        return {}
    if not isinstance(env, dict):
        raise HTTPException(status_code=422, detail="env must be an object")
    return env


def _server_config_from_template(config_template: dict[str, Any], env_values: dict[str, object]) -> dict[str, Any]:
    cfg: dict[str, Any] = {"transport": config_template.get("transport")}
    if config_template.get("url"):
        cfg["url"] = config_template.get("url")
        cfg["transport"] = "streamable_http"
        _validate_streamable_http_url(str(cfg["url"]))
    if config_template.get("command"):
        cfg["command"] = config_template.get("command")
        _validate_stdio_command(str(cfg["command"]))
        cfg["transport"] = "stdio"
    if "args" in config_template:
        cfg["args"] = _normalize_args(config_template.get("args")) or []
    if env_values:
        cfg["env"] = env_values
    return cfg


def _ensure_required_env(config_template: dict[str, Any], env_values: dict[str, object]) -> None:
    required = config_template.get("env_required") or []
    if not isinstance(required, list):
        return
    missing = [key for key in required if isinstance(key, str) and not env_values.get(key)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required env: {', '.join(missing)}")


class InstallRequest(BaseModel):
    mcp_id: str
    custom_name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


@mcp_user.post("/configs")
async def install_tool(
    payload: InstallRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (
        await db.execute(
            select(MCPMarketplace).where(MCPMarketplace.mcp_id == payload.mcp_id, MCPMarketplace.status == "active")
        )
    ).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")

    env_values = _normalize_env((payload.config or {}).get("env"))
    _ensure_required_env(tool.config_template or {}, env_values)
    try:
        env_values = encrypt_env_values(env_values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    stored_config = _server_config_from_template(tool.config_template or {}, env_values)
    user_config = UserMCPConfig(
        user_id=current_user.id,
        mcp_id=tool.mcp_id,
        custom_name=payload.custom_name,
        config=stored_config,
        is_enabled=True,
        status="active",
    )
    db.add(user_config)
    await db.flush()
    user_config.server_name = f"user_{user_config.id}"

    # Use atomic increment to avoid race condition
    await db.execute(
        update(MCPMarketplace)
        .where(MCPMarketplace.mcp_id == tool.mcp_id)
        .values(install_count=MCPMarketplace.install_count + 1)
    )

    return {"config_id": user_config.id, "mcp_id": tool.mcp_id, "server_name": user_config.server_name}


class UpdateRequest(BaseModel):
    custom_name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


@mcp_user.put("/configs/{config_id}")
async def update_config(
    config_id: int,
    payload: UpdateRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    user_config = (
        await db.execute(
            select(UserMCPConfig).where(UserMCPConfig.id == config_id, UserMCPConfig.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if user_config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    tool = (
        await db.execute(select(MCPMarketplace).where(MCPMarketplace.mcp_id == user_config.mcp_id))
    ).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")

    env_patch = _normalize_env((payload.config or {}).get("env"))
    try:
        env_patch = {k: v for k, v in env_patch.items() if v is not None and v != ""}
        env_patch = encrypt_env_values(env_patch)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    current_cfg = user_config.config or {}
    current_env = current_cfg.get("env") if isinstance(current_cfg, dict) else None
    merged_env = dict(current_env) if isinstance(current_env, dict) else {}
    merged_env.update(env_patch)

    if payload.custom_name is not None:
        user_config.custom_name = payload.custom_name

    updated_cfg = dict(current_cfg) if isinstance(current_cfg, dict) else {}
    updated_cfg["env"] = merged_env
    user_config.config = updated_cfg
    clear_mcp_cache(user_config.server_name or f"user_{user_config.id}")
    return {"success": True}


class ToggleRequest(BaseModel):
    is_enabled: bool


@mcp_user.patch("/configs/{config_id}/toggle")
async def toggle_config(
    config_id: int,
    payload: ToggleRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        update(UserMCPConfig)
        .where(UserMCPConfig.id == config_id, UserMCPConfig.user_id == current_user.id)
        .values(is_enabled=payload.is_enabled)
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Config not found")
    return {"success": True}


@mcp_user.delete("/configs/{config_id}")
async def delete_config(
    config_id: int,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    user_config = (
        await db.execute(
            select(UserMCPConfig).where(UserMCPConfig.id == config_id, UserMCPConfig.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if user_config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    tool = (
        await db.execute(select(MCPMarketplace).where(MCPMarketplace.mcp_id == user_config.mcp_id))
    ).scalar_one_or_none()

    await db.execute(
        delete(UserMCPConfig).where(UserMCPConfig.id == config_id, UserMCPConfig.user_id == current_user.id)
    )
    clear_mcp_cache(user_config.server_name or f"user_{user_config.id}")

    if tool is not None and tool.status == "private" and tool.created_by == current_user.id:
        await db.execute(delete(MCPMarketplace).where(MCPMarketplace.mcp_id == tool.mcp_id))

    return {"success": True}


@mcp_user.get("/configs")
async def list_my_configs(current_user: User = Depends(get_required_user), db: AsyncSession = Depends(get_db)):
    stmt = (
        select(UserMCPConfig, MCPMarketplace)
        .join(MCPMarketplace, MCPMarketplace.mcp_id == UserMCPConfig.mcp_id)
        .where(UserMCPConfig.user_id == current_user.id)
        .order_by(UserMCPConfig.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    result: list[dict[str, Any]] = []
    for user_config, tool in rows:
        result.append(
            {
                "id": user_config.id,
                "server_name": user_config.server_name or f"user_{user_config.id}",
                "mcp_id": user_config.mcp_id,
                "custom_name": user_config.custom_name,
                "is_enabled": user_config.is_enabled,
                "status": user_config.status,
                "last_error": user_config.last_error,
                "tool": {
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category,
                    "status": tool.status,
                    "icon_url": tool.icon_url,
                },
                "config_env": build_env_status(tool.config_template or {}, user_config.config or {}),
            }
        )
    return result


@mcp_user.get("/available")
async def list_available(current_user: User = Depends(get_required_user), db: AsyncSession = Depends(get_db)):
    from src.agents.common.mcp import MCP_SERVERS

    stmt = select(UserMCPConfig).where(UserMCPConfig.user_id == current_user.id, UserMCPConfig.is_enabled.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    items = [{"server_name": name, "source": "builtin"} for name in MCP_SERVERS.keys()]
    items.extend(
        [{"server_name": row.server_name or f"user_{row.id}", "source": "user", "mcp_id": row.mcp_id} for row in rows]
    )
    return {"items": items}


class TestResponse(BaseModel):
    success: bool
    tools_count: int | None = None
    error: str | None = None


@mcp_user.post("/configs/{config_id}/test", response_model=TestResponse)
async def test_config(
    config_id: int,
    timeout: float = Query(10.0, gt=0, le=30),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    user_config = (
        await db.execute(
            select(UserMCPConfig).where(UserMCPConfig.id == config_id, UserMCPConfig.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if user_config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    cfg = user_config.config or {}
    env = cfg.get("env") if isinstance(cfg, dict) else None
    env_map = env if isinstance(env, dict) else {}
    try:
        decrypted_env = decrypt_env_values(env_map)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    server_cfg = dict(cfg)
    if decrypted_env:
        server_cfg["env"] = decrypted_env

    server_name = user_config.server_name or f"user_{user_config.id}"
    try:
        clear_mcp_cache(server_name)
        tools = await asyncio.wait_for(
            get_mcp_tools(server_name, additional_servers={server_name: server_cfg}), timeout=timeout
        )
        return {"success": True, "tools_count": len(tools)}
    except TimeoutError:
        return {"success": False, "error": "Connection timeout"}
    except ConnectionError as exc:
        logger.warning(f"Failed to test MCP config {config_id}: {exc}")
        return {"success": False, "error": "Connection failed"}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to test MCP config {config_id}: {exc}")
        # Sanitize error message to avoid leaking sensitive information
        error_msg = str(exc)
        if any(kw in error_msg.lower() for kw in ("password", "secret", "token", "key", "credential")):
            error_msg = "Configuration error"
        return {"success": False, "error": error_msg}


class ManualAddRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = ""
    custom_name: str | None = None
    config: dict[str, Any]


@mcp_user.post("/manual")
async def manual_add(
    payload: ManualAddRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    config = payload.config or {}
    transport = _infer_transport(config)

    env_values = _normalize_env(config.get("env"))
    try:
        env_values = encrypt_env_values(env_values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    tool_mcp_id = f"manual_{current_user.id}_{uuid.uuid4().hex}"
    config_template: dict[str, Any] = {
        "transport": transport,
        "env_required": [],
        "env_optional": sorted(env_values.keys()),
    }

    server_cfg: dict[str, Any] = {"transport": transport}
    if transport == "streamable_http":
        url = config.get("url")
        if not isinstance(url, str) or not url:
            raise HTTPException(status_code=422, detail="url is required for streamable_http")
        _validate_streamable_http_url(url)
        server_cfg["url"] = url
        config_template["url"] = url
    else:
        command = config.get("command")
        if not isinstance(command, str) or not command:
            raise HTTPException(status_code=422, detail="command is required for stdio")
        _validate_stdio_command(command)
        server_cfg["command"] = command
        config_template["command"] = command
        args = _normalize_args(config.get("args")) or []
        server_cfg["args"] = args
        config_template["args"] = args

    if env_values:
        server_cfg["env"] = env_values

    marketplace = MCPMarketplace(
        mcp_id=tool_mcp_id,
        name=payload.name,
        description=payload.description or "",
        category="private",
        tags=[],
        transport=transport,
        config_template=config_template,
        status="private",
        is_official=False,
        created_by=current_user.id,
    )
    db.add(marketplace)
    user_config = UserMCPConfig(
        user_id=current_user.id,
        mcp_id=tool_mcp_id,
        custom_name=payload.custom_name or payload.name,
        config=server_cfg,
        is_enabled=True,
        status="active",
    )
    db.add(user_config)
    await db.flush()
    user_config.server_name = f"user_{user_config.id}"
    return {"config_id": user_config.id, "mcp_id": tool_mcp_id}


@mcp_user.get("/tools/{mcp_id}")
async def get_user_visible_tool_detail(
    mcp_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    tool = (await db.execute(select(MCPMarketplace).where(MCPMarketplace.mcp_id == mcp_id))).scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    if tool.status == "private" and tool.created_by != current_user.id:
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
    }
