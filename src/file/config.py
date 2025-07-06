"""
文件管理系统配置加载器

从现有的配置文件加载存储配置
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .models import StorageConfig
from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化配置加载器
        
        Args:
            config_path: 配置文件路径，默认使用项目中的database.yaml
        """
        if config_path is None:
            # 使用项目中的默认配置文件
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "src" / "static" / "database.yaml"
        
        self.config_path = Path(config_path)
        self.config_data = None
        self.environment = os.getenv('ENVIRONMENT', 'development')
        
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if not self.config_path.exists():
                raise ConfigurationError(f"配置文件不存在: {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f)
            
            logger.info(f"配置文件加载成功: {self.config_path}")
            
        except yaml.YAMLError as e:
            raise ConfigurationError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise ConfigurationError(f"加载配置文件失败: {e}")
    
    def _resolve_env_vars(self, value: Any) -> Any:
        """解析环境变量"""
        if isinstance(value, str):
            # 处理 ${ENV_VAR:-default} 格式
            if value.startswith('${') and '}' in value:
                # 提取环境变量名和默认值
                env_expr = value[2:-1]  # 移除 ${ 和 }
                
                if ':-' in env_expr:
                    env_name, default_value = env_expr.split(':-', 1)
                    return os.getenv(env_name, default_value)
                else:
                    env_name = env_expr
                    env_value = os.getenv(env_name)
                    if env_value is None:
                        raise ConfigurationError(f"环境变量未设置: {env_name}")
                    return env_value
            
            # 处理简单的环境变量引用
            elif value.startswith('$'):
                env_name = value[1:]
                env_value = os.getenv(env_name)
                if env_value is None:
                    raise ConfigurationError(f"环境变量未设置: {env_name}")
                return env_value
        
        return value
    
    def _get_env_config(self, env_name: str) -> Dict[str, Any]:
        """获取指定环境的配置"""
        if not self.config_data:
            raise ConfigurationError("配置数据未加载")
        
        environments = self.config_data.get('environments', {})
        if env_name not in environments:
            raise ConfigurationError(f"环境配置不存在: {env_name}")
        
        env_config = environments[env_name]
        
        # 递归解析环境变量
        def resolve_recursive(obj):
            if isinstance(obj, dict):
                return {k: resolve_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_recursive(item) for item in obj]
            else:
                return self._resolve_env_vars(obj)
        
        return resolve_recursive(env_config)
    
    def get_storage_config(self, environment: Optional[str] = None) -> StorageConfig:
        """获取存储配置
        
        Args:
            environment: 环境名称，默认使用实例化时的环境
            
        Returns:
            StorageConfig对象
        """
        if environment is None:
            environment = self.environment
        
        try:
            env_config = self._get_env_config(environment)
            
            # 构建PostgreSQL URL
            postgres_config = env_config.get('lightrag_db', {})
            postgres_url = self._build_postgres_url(postgres_config)
            
            # 构建MinIO配置
            minio_config = env_config.get('minio', {})
            minio_endpoint = minio_config.get('uri', 'http://localhost:9001')
            # 移除协议前缀用于endpoint
            if minio_endpoint.startswith(('http://', 'https://')):
                from urllib.parse import urlparse
                parsed = urlparse(minio_endpoint)
                minio_endpoint_clean = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
                minio_secure = parsed.scheme == 'https'
            else:
                minio_endpoint_clean = minio_endpoint
                minio_secure = minio_config.get('secure', False)
            
            # 构建Redis URL
            redis_config = env_config.get('redis', {})
            redis_url = self._build_redis_url(redis_config)
            
            storage_config = StorageConfig(
                minio_endpoint=minio_endpoint_clean,
                minio_access_key=minio_config.get('access_key', 'minioadmin'),
                minio_secret_key=minio_config.get('secret_key', 'minioadmin'),
                minio_bucket='yuxi-know-files',  # 使用专门的存储桶
                minio_secure=minio_secure,
                postgres_url=postgres_url,
                redis_url=redis_url,
                redis_password=redis_config.get('password')
            )
            
            logger.info(f"存储配置构建成功，环境: {environment}")
            return storage_config
            
        except Exception as e:
            logger.error(f"构建存储配置失败: {e}")
            raise ConfigurationError(f"构建存储配置失败: {e}")
    
    def _build_postgres_url(self, postgres_config: Dict[str, Any]) -> str:
        """构建PostgreSQL连接URL"""
        host = postgres_config.get('host', 'localhost')
        port = postgres_config.get('port', 5432)
        database = postgres_config.get('database', 'lightrag')
        username = postgres_config.get('username', 'postgres')
        password = postgres_config.get('password', '')
        
        if not password:
            raise ConfigurationError("PostgreSQL密码未配置")
        
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"
    
    def _build_redis_url(self, redis_config: Dict[str, Any]) -> str:
        """构建Redis连接URL"""
        host = redis_config.get('host', 'localhost')
        port = redis_config.get('port', 6379)
        db = redis_config.get('db', 0)
        password = redis_config.get('password')
        
        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        else:
            return f"redis://{host}:{port}/{db}"
    
    def get_processing_config(self, environment: Optional[str] = None) -> Dict[str, Any]:
        """获取文档处理配置"""
        if environment is None:
            environment = self.environment
        
        # 默认处理配置
        default_config = {
            'chunk_size': 500,
            'chunk_overlap': 50,
            'enable_ocr': 'disable',
            'max_file_size': 100 * 1024 * 1024,  # 100MB
            'supported_file_types': [
                'pdf', 'docx', 'doc', 'txt', 'md', 
                'html', 'htm', 'csv', 'json',
                'png', 'jpg', 'jpeg', 'gif', 'bmp'
            ],
            'processing_timeout': 300,  # 5分钟
            'max_concurrent_processing': 5
        }
        
        try:
            env_config = self._get_env_config(environment)
            processing_config = env_config.get('processing', {})
            
            # 合并默认配置和环境配置
            result_config = {**default_config, **processing_config}
            
            logger.debug(f"处理配置获取成功，环境: {environment}")
            return result_config
            
        except Exception as e:
            logger.warning(f"获取处理配置失败，使用默认配置: {e}")
            return default_config


def load_storage_config(environment: Optional[str] = None, 
                       config_path: Optional[str] = None) -> StorageConfig:
    """便捷函数：加载存储配置
    
    Args:
        environment: 环境名称
        config_path: 配置文件路径
        
    Returns:
        StorageConfig对象
    """
    loader = ConfigLoader(config_path)
    return loader.get_storage_config(environment)


def load_processing_config(environment: Optional[str] = None,
                          config_path: Optional[str] = None) -> Dict[str, Any]:
    """便捷函数：加载处理配置
    
    Args:
        environment: 环境名称
        config_path: 配置文件路径
        
    Returns:
        处理配置字典
    """
    loader = ConfigLoader(config_path)
    return loader.get_processing_config(environment)