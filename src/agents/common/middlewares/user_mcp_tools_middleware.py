from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from sqlalchemy import select

from src.agents.common.mcp import MCP_SERVERS, get_mcp_tools
from src.storage.db.manager import db_manager
from src.storage.db.models import UserMCPConfig
from src.utils import logger
from src.utils.mcp_utils import decrypt_env_values

# langchain_mcp_adapters 支持的配置字段
_MCP_ALLOWED_KEYS = {"url", "transport", "command", "args", "env", "headers", "timeout", "sse_read_timeout"}


class UserMCPToolsMiddleware(AgentMiddleware):
    """Inject MCP tools at runtime based on `context.mcps` (including `user_{config_id}`)."""

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        selected_mcps = getattr(request.runtime.context, "mcps", None)
        if not selected_mcps or not isinstance(selected_mcps, list):
            return await handler(request)

        user_id_raw = getattr(request.runtime.context, "user_id", None)
        try:
            user_id = int(user_id_raw) if user_id_raw is not None else None
        except (TypeError, ValueError):
            user_id = None

        user_config_ids: list[int] = []
        static_servers: list[str] = []
        for name in selected_mcps:
            if not isinstance(name, str) or not name:
                continue
            if name.startswith("user_"):
                try:
                    user_config_ids.append(int(name.removeprefix("user_")))
                except ValueError:
                    continue
            else:
                static_servers.append(name)

        injected_tools: list[Any] = []

        for server_name in static_servers:
            if server_name not in MCP_SERVERS:
                continue
            injected_tools.extend(await get_mcp_tools(server_name))

        if user_id is not None and user_config_ids:
            async with db_manager.get_async_session_context() as session:
                stmt = select(UserMCPConfig).where(
                    UserMCPConfig.user_id == user_id,
                    UserMCPConfig.is_enabled.is_(True),
                    UserMCPConfig.id.in_(user_config_ids),
                )
                user_configs = (await session.execute(stmt)).scalars().all()

            for user_config in user_configs:
                server_name = user_config.server_name or f"user_{user_config.id}"
                cfg = user_config.config or {}
                if not isinstance(cfg, dict):
                    continue
                env = cfg.get("env")
                if isinstance(env, dict) and env:
                    try:
                        cfg = {**cfg, "env": decrypt_env_values(env)}
                    except ValueError as exc:
                        logger.warning(f"Failed to decrypt MCP env for {server_name}: {exc}")
                        continue
                # 过滤掉 langchain_mcp_adapters 不支持的字段
                filtered_cfg = {k: v for k, v in cfg.items() if k in _MCP_ALLOWED_KEYS}
                injected_tools.extend(await get_mcp_tools(server_name, additional_servers={server_name: filtered_cfg}))

        if not injected_tools:
            return await handler(request)

        base_tools = list(request.tools or [])
        by_name: dict[str, Any] = {}
        for idx, tool in enumerate(base_tools):
            name = getattr(tool, "name", None) or str(idx)
            by_name[name] = tool
        for tool in injected_tools:
            name = getattr(tool, "name", None)
            if not name:
                continue
            by_name[name] = tool

        request = request.override(tools=list(by_name.values()))
        return await handler(request)
