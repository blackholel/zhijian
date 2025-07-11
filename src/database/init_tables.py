"""
数据库表初始化脚本
"""

import asyncio
from src.database.models import Base
from src.database.manager import get_database_manager
from src.utils.logging_config import logger

# 导入所有模型以确保它们被注册到Base.metadata
from src.auth.models.user_models import User, Role, Permission, UserRole, RolePermission, UserPermissionCache, OperationLog
from src.auth.models.agent_models import AgentDefinition, AgentSession, AgentPermission, AgentTask
from src.knowledge_base.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode, KnowledgeDatabasePermission


async def initialize_database_tables():
    """初始化数据库表"""
    try:
        # 获取数据库管理器
        db_manager = get_database_manager()
        if not db_manager._initialized:
            await db_manager.initialize()
        
        # 获取PostgreSQL适配器
        pg_adapter = await db_manager.get_postgresql_adapter('server_db')
        
        # 创建所有表
        await pg_adapter.create_tables_if_not_exists(Base.metadata)
        logger.info("Database tables initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(initialize_database_tables())