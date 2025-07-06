"""
数据库管理器兼容性模块

为了保持向后兼容，提供原有db_manager接口的兼容实现
"""

import warnings
from src.database.manager import get_database_manager

# 发出兼容性警告
warnings.warn(
    "server.db_manager is deprecated. Please use src.database.manager instead.",
    DeprecationWarning,
    stacklevel=2
)

# 获取统一数据库管理器实例
_db_manager = get_database_manager()

# 兼容性接口
db_manager = _db_manager
engine = _db_manager.engine
Session = _db_manager.Session

def get_session():
    """获取数据库会话（兼容接口）"""
    return _db_manager.get_session_sync()

def get_db():
    """获取数据库会话生成器（兼容FastAPI依赖注入）"""
    session = get_session()
    try:
        yield session
    finally:
        session.close()

# 健康检查
def health_check():
    """数据库健康检查（兼容接口）"""
    import asyncio
    return asyncio.run(_db_manager.health_check())

def create_tables():
    """创建数据库表（兼容接口）"""
    _db_manager.create_tables()

def get_connection_info():
    """获取连接信息（兼容接口）"""
    return _db_manager.get_connection_info('server_db')

def validate_database_config(db_name: str):
    """验证数据库配置（兼容接口）"""
    return _db_manager.validate_database_config(db_name)

def get_database_connection_string(db_name: str):
    """获取数据库连接字符串（兼容接口）"""
    return _db_manager.get_connection_string(db_name)