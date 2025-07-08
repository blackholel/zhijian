"""
数据库管理器兼容性模块

为了保持向后兼容，提供原有db_manager接口的兼容实现
使用延迟导入避免循环依赖
"""

import warnings
import asyncio
from typing import Optional

# 发出兼容性警告
warnings.warn(
    "server.db_manager is deprecated. Please use src.database.manager instead.",
    DeprecationWarning,
    stacklevel=2
)

# 全局实例缓存
_db_manager = None
_engine = None
_Session = None

def _get_database_manager():
    """延迟导入数据库管理器"""
    global _db_manager
    if _db_manager is None:
        from src.database.manager import get_database_manager
        _db_manager = get_database_manager()
    return _db_manager

# 兼容性接口 - 作为模块属性延迟初始化
class _LazyDBManager:
    """延迟初始化的数据库管理器代理"""
    
    def __getattr__(self, name):
        manager = _get_database_manager()
        return getattr(manager, name)

db_manager = _LazyDBManager()

@property
def engine():
    return _get_database_manager().engine

@property  
def Session():
    return _get_database_manager().Session

def get_session():
    """获取数据库会话（兼容接口）"""
    return _get_database_manager().get_session_sync()

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
    return asyncio.run(_get_database_manager().health_check())

def create_tables():
    """创建数据库表（兼容接口）"""
    _get_database_manager().create_tables()

def get_connection_info():
    """获取连接信息（兼容接口）"""
    return _get_database_manager().get_database_config('server_db')

def validate_database_config(db_name: str):
    """验证数据库配置（兼容接口）"""
    return _get_database_manager().validate_database_config(db_name)

def get_database_connection_string(db_name: str):
    """获取数据库连接字符串（兼容接口）"""
    return _get_database_manager().get_connection_string(db_name)