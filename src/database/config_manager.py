"""
统一数据库配置管理器
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse, quote_plus

from .base import ConfigurationError

logger = logging.getLogger(__name__)


class DatabaseConfigManager:
    """数据库配置管理器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为 src/static/database.yaml
        """
        self.config_path = config_path or str(Path("src/static/database.yaml"))
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self._config = None
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Database config file not found: {self.config_path}")
                self._config = self._get_default_config()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config or 'environments' not in config:
                raise ConfigurationError("Invalid config file format")
            
            # 设置当前环境
            self.environment = os.getenv('ENVIRONMENT', config.get('default_environment', 'development'))
            
            if self.environment not in config['environments']:
                logger.warning(f"Environment '{self.environment}' not found, using 'development'")
                self.environment = 'development'
            
            self._config = config['environments'][self.environment]
            logger.info(f"Loaded database config from {self.config_path}, environment: {self.environment}")
            
        except Exception as e:
            logger.error(f"Failed to load database config: {e}")
            raise ConfigurationError(f"Failed to load database config: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'server_db': {
                'type': 'postgresql',
                'host': 'localhost',
                'port': 5432,
                'database': 'yuxi_dev',
                'username': 'postgres',
                'password': 'password',
                'pool_size': 10,
                'max_overflow': 20
            },
            'neo4j': {
                'uri': 'bolt://localhost:7687',
                'username': 'neo4j',
                'password': 'password',
                'encrypted': False
            },
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'password': '',
                'db': 0
            }
        }
    
    def get_database_config(self, db_name: str) -> Dict[str, Any]:
        """
        获取指定数据库配置
        
        Args:
            db_name: 数据库名称
            
        Returns:
            Dict[str, Any]: 数据库配置
            
        Raises:
            ConfigurationError: 当数据库配置不存在时
        """
        if not self._config:
            raise ConfigurationError("Database config not loaded")
        
        if db_name not in self._config:
            raise ConfigurationError(f"Database '{db_name}' not found in config")
        
        config = self._config[db_name].copy()
        
        # 处理环境变量替换
        return self._resolve_env_vars(config)
    
    def _resolve_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析环境变量
        
        支持格式:
        - ${VAR_NAME} : 直接替换
        - ${VAR_NAME:-default_value} : 如果环境变量不存在，使用默认值
        """
        resolved = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                # 环境变量格式: ${VAR_NAME:-default_value}
                env_expr = value[2:-1]
                if ':-' in env_expr:
                    env_name, default_val = env_expr.split(':-', 1)
                    resolved[key] = os.getenv(env_name, default_val)
                else:
                    resolved[key] = os.getenv(env_expr, value)
            else:
                resolved[key] = value
        return resolved
    
    def get_postgresql_connection_string(self, db_name: str) -> str:
        """获取PostgreSQL连接字符串"""
        config = self.get_database_config(db_name)
        
        # URL编码用户名和密码以处理特殊字符
        username = quote_plus(str(config['username']))
        password = quote_plus(str(config['password']))
        host = config['host']
        port = config['port']
        database = config['database']
        
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"
    
    def get_neo4j_config(self, db_name: str = 'neo4j') -> Dict[str, Any]:
        """获取Neo4j配置"""
        config = self.get_database_config(db_name)
        return {
            'uri': config.get('uri', 'bolt://localhost:7687'),
            'username': config.get('username', 'neo4j'),
            'password': config.get('password', 'password'),
            'encrypted': config.get('encrypted', False),
            'trust': config.get('trust', 'TRUST_ALL_CERTIFICATES'),
            'connection_timeout': config.get('connection_timeout', 30),
            'max_connection_lifetime': config.get('max_connection_lifetime', 3600),
            'max_connection_pool_size': config.get('max_connection_pool_size', 100),
            'connection_acquisition_timeout': config.get('connection_acquisition_timeout', 60)
        }
    
    def get_redis_config(self, db_name: str = 'redis') -> Dict[str, Any]:
        """获取Redis配置"""
        config = self.get_database_config(db_name)
        return {
            'host': config.get('host', 'localhost'),
            'port': config.get('port', 6379),
            'password': config.get('password', ''),
            'db': config.get('db', 0),
            'max_connections': config.get('max_connections', 20),
            'decode_responses': config.get('decode_responses', True),
            'retry_on_timeout': config.get('retry_on_timeout', True),
            'connection_timeout': config.get('connection_timeout', 30),
            'socket_timeout': config.get('socket_timeout', 30)
        }
    
    def get_redis_url(self, db_name: str = 'redis') -> str:
        """获取Redis连接URL"""
        config = self.get_redis_config(db_name)
        host = config['host']
        port = config['port']
        password = config['password']
        db = config['db']
        
        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        else:
            return f"redis://{host}:{port}/{db}"
    
    def get_milvus_config(self, db_name: str = 'milvus') -> Dict[str, Any]:
        """获取Milvus配置"""
        config = self.get_database_config(db_name)
        return {
            'uri': config.get('uri', 'http://localhost:19530'),
            'user': config.get('user', ''),
            'password': config.get('password', ''),
            'db_name': config.get('db_name', 'default'),
            'timeout': config.get('timeout', 30)
        }
    
    def get_minio_config(self, db_name: str = 'minio') -> Dict[str, Any]:
        """获取MinIO配置"""
        config = self.get_database_config(db_name)
        uri = config.get('uri', 'http://localhost:9000')
        
        # 解析URI以确定是否使用HTTPS
        parsed = urlparse(uri)
        secure = parsed.scheme == 'https'
        
        # 提取endpoint（去掉协议前缀）
        if uri.startswith(('http://', 'https://')):
            endpoint = parsed.netloc
        else:
            endpoint = uri
        
        return {
            'endpoint': endpoint,
            'access_key': config.get('access_key', 'minioadmin'),
            'secret_key': config.get('secret_key', 'minioadmin'),
            'secure': config.get('secure', secure),
            'region': config.get('region', 'us-east-1')
        }
    
    def validate_database_config(self, db_name: str) -> bool:
        """
        验证数据库配置
        
        Args:
            db_name: 数据库名称
            
        Returns:
            bool: 配置有效返回True，无效返回False
        """
        try:
            config = self.get_database_config(db_name)
            
            # 通用必填字段检查
            if db_name in ['server_db', 'lightrag_db']:
                required_fields = ['type', 'host', 'port', 'database', 'username', 'password']
            elif db_name == 'neo4j':
                required_fields = ['uri', 'username', 'password']
            elif db_name == 'redis':
                required_fields = ['host', 'port']
            elif db_name == 'milvus':
                required_fields = ['uri']
            elif db_name == 'minio':
                required_fields = ['uri', 'access_key', 'secret_key']
            else:
                logger.warning(f"Unknown database type: {db_name}")
                return False
            
            for field in required_fields:
                if field not in config:
                    logger.error(f"Missing required field '{field}' in {db_name} config")
                    return False
                if config[field] is None or (isinstance(config[field], str) and not config[field].strip()):
                    logger.error(f"Empty required field '{field}' in {db_name} config")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating {db_name} config: {e}")
            return False
    
    def get_all_database_names(self) -> list:
        """获取所有数据库名称"""
        if not self._config:
            return []
        return list(self._config.keys())
    
    def set_environment(self, environment: str):
        """设置当前环境"""
        if environment != self.environment:
            self.environment = environment
            self._load_config()
            logger.info(f"Environment changed to: {environment}")
    
    def reload_config(self):
        """重新加载配置"""
        self._load_config()
        logger.info("Database config reloaded")
    
    def get_retry_config(self) -> Dict[str, Any]:
        """获取重试配置"""
        if not self._config:
            return {'max_retries': 3, 'retry_delay': 1, 'backoff_factor': 2}
        
        # 查找全局重试配置
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f)
            return full_config.get('retry_config', {
                'max_retries': 3,
                'retry_delay': 1,
                'backoff_factor': 2
            })
        except:
            return {'max_retries': 3, 'retry_delay': 1, 'backoff_factor': 2}
    
    def get_health_check_config(self) -> Dict[str, Any]:
        """获取健康检查配置"""
        if not self._config:
            return {'enabled': True, 'interval': 60, 'timeout': 10}
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f)
            return full_config.get('health_check', {
                'enabled': True,
                'interval': 60,
                'timeout': 10
            })
        except:
            return {'enabled': True, 'interval': 60, 'timeout': 10}