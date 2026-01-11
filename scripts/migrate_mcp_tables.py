#!/usr/bin/env python3
"""
MCP 市场相关表迁移脚本

该脚本用于为 PostgreSQL 数据库添加 MCP 市场功能所需的表和字段：
- mcp_marketplace: MCP 工具市场表
- user_mcp_configs: 用户 MCP 配置表
- mcp_ratings: MCP 评分表

使用方法:
    # 本地执行
    uv run python scripts/migrate_mcp_tables.py

    # Docker 容器内执行
    docker compose exec api uv run python scripts/migrate_mcp_tables.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 将项目根目录加入到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402
from src.storage.db.manager import db_manager  # noqa: E402


async def check_table_exists(session, table_name: str) -> bool:
    """检查表是否存在"""
    result = await session.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    )
    return result.scalar()


async def check_column_exists(session, table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    result = await session.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = :table_name
                AND column_name = :column_name
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar()


async def run_migration():
    """执行迁移"""
    print("开始 MCP 表迁移...")

    async with db_manager.get_async_session_context() as session:
        # 1. 创建 mcp_marketplace 表
        if not await check_table_exists(session, "mcp_marketplace"):
            print("创建 mcp_marketplace 表...")
            await session.execute(
                text(
                    """
                    CREATE TABLE mcp_marketplace (
                        id SERIAL PRIMARY KEY,
                        mcp_id VARCHAR(128) NOT NULL UNIQUE,
                        name VARCHAR(255) NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        category VARCHAR(64),
                        tags JSONB,
                        icon_url VARCHAR(512),
                        transport VARCHAR(32) NOT NULL DEFAULT 'streamable_http',
                        config_template JSONB NOT NULL DEFAULT '{}',
                        author VARCHAR(255),
                        version VARCHAR(32),
                        homepage_url VARCHAR(512),
                        documentation_url VARCHAR(512),
                        examples JSONB,
                        status VARCHAR(32) NOT NULL DEFAULT 'active',
                        is_official BOOLEAN NOT NULL DEFAULT FALSE,
                        install_count INTEGER NOT NULL DEFAULT 0,
                        rating_avg FLOAT,
                        rating_count INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        created_by INTEGER REFERENCES users(id)
                    )
                    """
                )
            )
            # 创建索引
            await session.execute(text("CREATE INDEX ix_mcp_marketplace_mcp_id ON mcp_marketplace(mcp_id)"))
            await session.execute(text("CREATE INDEX ix_mcp_marketplace_category ON mcp_marketplace(category)"))
            await session.execute(text("CREATE INDEX ix_mcp_marketplace_status ON mcp_marketplace(status)"))
            print("  mcp_marketplace 表创建成功")
        else:
            print("  mcp_marketplace 表已存在，检查缺失列...")
            # 检查并添加缺失的列
            if not await check_column_exists(session, "mcp_marketplace", "id"):
                print("    添加 id 列...")
                await session.execute(text("ALTER TABLE mcp_marketplace ADD COLUMN id SERIAL"))
            if not await check_column_exists(session, "mcp_marketplace", "transport"):
                print("    添加 transport 列...")
                await session.execute(
                    text(
                        "ALTER TABLE mcp_marketplace ADD COLUMN transport VARCHAR(32) NOT NULL DEFAULT 'streamable_http'"
                    )
                )

        # 2. 创建 user_mcp_configs 表
        if not await check_table_exists(session, "user_mcp_configs"):
            print("创建 user_mcp_configs 表...")
            await session.execute(
                text(
                    """
                    CREATE TABLE user_mcp_configs (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        mcp_id VARCHAR(128) NOT NULL REFERENCES mcp_marketplace(mcp_id),
                        server_name VARCHAR(128) UNIQUE,
                        custom_name VARCHAR(255),
                        config JSONB NOT NULL DEFAULT '{}',
                        is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        status VARCHAR(32) NOT NULL DEFAULT 'active',
                        last_error TEXT,
                        last_used_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        CONSTRAINT uq_user_mcp UNIQUE (user_id, mcp_id)
                    )
                    """
                )
            )
            # 创建索引
            await session.execute(text("CREATE INDEX ix_user_mcp_configs_user_id ON user_mcp_configs(user_id)"))
            await session.execute(text("CREATE INDEX ix_user_mcp_configs_mcp_id ON user_mcp_configs(mcp_id)"))
            await session.execute(text("CREATE INDEX ix_user_mcp_configs_server_name ON user_mcp_configs(server_name)"))
            await session.execute(text("CREATE INDEX ix_user_mcp_configs_is_enabled ON user_mcp_configs(is_enabled)"))
            print("  user_mcp_configs 表创建成功")
        else:
            print("  user_mcp_configs 表已存在，检查缺失列...")
            # 检查并添加缺失的列
            if not await check_column_exists(session, "user_mcp_configs", "server_name"):
                print("    添加 server_name 列...")
                await session.execute(text("ALTER TABLE user_mcp_configs ADD COLUMN server_name VARCHAR(128) UNIQUE"))

        # 3. 创建 mcp_ratings 表
        if not await check_table_exists(session, "mcp_ratings"):
            print("创建 mcp_ratings 表...")
            await session.execute(
                text(
                    """
                    CREATE TABLE mcp_ratings (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        mcp_id VARCHAR(128) NOT NULL REFERENCES mcp_marketplace(mcp_id),
                        rating INTEGER NOT NULL,
                        comment TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        CONSTRAINT uq_mcp_rating_user UNIQUE (user_id, mcp_id)
                    )
                    """
                )
            )
            # 创建索引
            await session.execute(text("CREATE INDEX ix_mcp_ratings_user_id ON mcp_ratings(user_id)"))
            await session.execute(text("CREATE INDEX ix_mcp_ratings_mcp_id ON mcp_ratings(mcp_id)"))
            print("  mcp_ratings 表创建成功")
        else:
            print("  mcp_ratings 表已存在")

        await session.commit()
        print("\nMCP 表迁移完成!")


def main():
    asyncio.run(run_migration())


if __name__ == "__main__":
    main()
