"""
数据库统一管理模块

提供统一的数据库连接、配置管理和数据访问接口
"""

from .base import DatabaseAdapter, DatabaseType, ConnectionStatus
from .connection_manager import DatabaseConnectionManager
from .config_manager import DatabaseConfigManager

__all__ = [
    'DatabaseAdapter',
    'DatabaseType', 
    'ConnectionStatus',
    'DatabaseConnectionManager',
    'DatabaseConfigManager'
]