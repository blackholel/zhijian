import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from src.utils.logging_config import logger

DEFAULT_MOCK_API = 'this_is_mock_api_key_in_frontend'

class DatabaseConfig:
    """数据库配置管理类"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or str(Path("src/static/database.yaml"))
        self.config_data = {}
        self.current_environment = "development"
        self.load_config()
    
    def load_config(self):
        """加载数据库配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config_data = yaml.safe_load(f)
                
                # 设置当前环境
                self.current_environment = os.getenv('ENVIRONMENT', 
                                                    self.config_data.get('default_environment', 'development'))
                
                logger.info(f"Loaded database config from {self.config_path}, environment: {self.current_environment}")
            else:
                logger.warning(f"Database config file not found: {self.config_path}")
                self.config_data = self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading database config: {e}")
            self.config_data = self._get_default_config()
    
    def _get_default_config(self):
        """获取默认配置"""
        return {
            'environments': {
                'development': {
                    'server_db': {
                        'type': 'postgresql',
                        'host': 'localhost',
                        'port': 5432,
                        'database': 'yuxi_dev',
                        'username': 'yuxi_user',
                        'password': 'yuxi_password',
                        'pool_size': 10,
                        'max_overflow': 20
                    }
                }
            },
            'default_environment': 'development'
        }
    
    def get_db_config(self, db_name: str) -> Dict[str, Any]:
        """获取指定数据库的配置"""
        env_config = self.config_data.get('environments', {}).get(self.current_environment, {})
        db_config = env_config.get(db_name, {})
        
        # 处理环境变量替换
        return self._resolve_env_variables(db_config)
    
    def _resolve_env_variables(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解析环境变量"""
        resolved_config = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                # 处理环境变量格式 ${VAR_NAME:-default_value}
                env_expr = value[2:-1]  # 去掉 ${ 和 }
                if ':-' in env_expr:
                    var_name, default_value = env_expr.split(':-', 1)
                    resolved_config[key] = os.getenv(var_name, default_value)
                else:
                    resolved_config[key] = os.getenv(env_expr, value)
            else:
                resolved_config[key] = value
        return resolved_config
    
    def get_connection_string(self, db_name: str) -> str:
        """获取数据库连接字符串"""
        config = self.get_db_config(db_name)
        db_type = config.get('type', 'postgresql')
        
        if db_type == 'postgresql':
            from urllib.parse import quote_plus
            # 对用户名和密码进行URL编码以处理特殊字符（如@符号）
            encoded_username = quote_plus(str(config['username']))
            encoded_password = quote_plus(str(config['password']))
            return f"postgresql://{encoded_username}:{encoded_password}@{config['host']}:{config['port']}/{config['database']}"
        elif db_type == 'sqlite':
            return f"sqlite:///{config.get('path', 'database.db')}"
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
    
    def get_neo4j_uri(self, db_name: str = 'neo4j') -> str:
        """获取Neo4j连接URI"""
        config = self.get_db_config(db_name)
        uri = config.get('uri', 'bolt://localhost:7687')
        return uri
    
    def get_redis_url(self, db_name: str = 'redis') -> str:
        """获取Redis连接URL"""
        config = self.get_db_config(db_name)
        host = config.get('host', 'localhost')
        port = config.get('port', 6379)
        password = config.get('password', '')
        db = config.get('db', 0)
        
        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        else:
            return f"redis://{host}:{port}/{db}"
    
    def get_milvus_config(self, db_name: str = 'milvus') -> Dict[str, Any]:
        """获取Milvus配置"""
        config = self.get_db_config(db_name)
        return {
            'uri': config.get('uri', 'http://localhost:19530'),
            'user': config.get('user', ''),
            'password': config.get('password', ''),
            'db_name': config.get('db_name', 'default'),
            'timeout': config.get('timeout', 30)
        }
    
    def get_minio_config(self, db_name: str = 'minio') -> Dict[str, Any]:
        """获取MinIO配置"""
        config = self.get_db_config(db_name)
        uri = config.get('uri', 'http://localhost:9000')
        
        # 解析URI以确定是否使用HTTPS
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        secure = parsed.scheme == 'https'
        
        return {
            'endpoint': uri,
            'access_key': config.get('access_key', 'minioadmin'),
            'secret_key': config.get('secret_key', 'minioadmin'),
            'secure': config.get('secure', secure),
            'region': config.get('region', 'us-east-1')
        }
    
    def validate_config(self, db_name: str) -> bool:
        """验证数据库配置"""
        try:
            config = self.get_db_config(db_name)
            required_fields = ['type', 'host', 'port', 'database', 'username', 'password']
            
            for field in required_fields:
                if field not in config or not config[field]:
                    logger.error(f"Missing required field '{field}' in {db_name} config")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Error validating {db_name} config: {e}")
            return False
    
    def set_environment(self, environment: str):
        """设置当前环境"""
        if environment in self.config_data.get('environments', {}):
            self.current_environment = environment
            logger.info(f"Environment set to: {environment}")
        else:
            logger.warning(f"Environment '{environment}' not found in config")
    
    def get_all_db_names(self) -> list:
        """获取所有数据库名称"""
        env_config = self.config_data.get('environments', {}).get(self.current_environment, {})
        return list(env_config.keys())

class SimpleConfig(dict):

    def __key(self, key):
        return "" if key is None else key  # 目前忘记了这里为什么要 lower 了，只能说配置项最好不要有大写的

    def __str__(self):
        return json.dumps(self)

    def __setattr__(self, key, value):
        self[self.__key(key)] = value

    def __getattr__(self, key):
        return self.get(self.__key(key))

    def __getitem__(self, key):
        return self.get(self.__key(key))

    def __setitem__(self, key, value):
        return super().__setitem__(self.__key(key), value)

    def __dict__(self):
        return {k: v for k, v in self.items()}

    def update(self, other):
        for key, value in other.items():
            self[key] = value


class Config(SimpleConfig):

    def __init__(self):
        super().__init__()
        self._config_items = {}
        self.save_dir = os.getenv('SAVE_DIR', 'saves')
        self.filename = str(Path(f"{self.save_dir}/config/base.yaml"))
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        
        # 初始化数据库配置
        self.database = DatabaseConfig()
        logger.info(f"Database config initialized with environment: {self.database.current_environment}")

        self._update_models_from_file()

        ### >>> 默认配置
        # 功能选项
        self.add_item("enable_reranker", default=False, des="是否开启重排序")
        self.add_item("enable_web_search", default=False, des="是否开启网页搜索（注：现阶段会根据 TAVILY_API_KEY 自动开启，无法手动配置，将会在下个版本移除此配置项）")  # noqa: E501
        # 默认智能体配置
        self.add_item("default_agent_id", default="", des="默认智能体ID")
        # 模型配置
        ## 注意这里是模型名，而不是具体的模型路径，默认使用 HuggingFace 的路径
        ## 如果需要自定义本地模型路径，则在 src/.env 中配置 MODEL_DIR
        self.add_item("model_provider", default="siliconflow", des="模型提供商", choices=list(self.model_names.keys()))
        self.add_item("model_name", default="Qwen/Qwen3-32B", des="模型名称")

        self.add_item("embed_model", default="siliconflow/BAAI/bge-m3", des="Embedding 模型", choices=list(self.embed_model_names.keys()))
        self.add_item("reranker", default="siliconflow/BAAI/bge-reranker-v2-m3", des="Re-Ranker 模型", choices=list(self.reranker_names.keys()))  # noqa: E501
        ### <<< 默认配置结束

        self.load()
        self.handle_self()

    def add_item(self, key, default, des=None, choices=None):
        self.__setattr__(key, default)
        self._config_items[key] = {
            "default": default,
            "des": des,
            "choices": choices
        }

    def __dict__(self):
        blocklist = [
            "_config_items",
            "model_names",
            "model_provider_status",
            "embed_model_names",
            "reranker_names",
        ]
        return {k: v for k, v in self.items() if k not in blocklist}

    def _update_models_from_file(self):
        """
        从 models.yaml 和 models.private.yml 中更新 MODEL_NAMES
        """

        with open(Path("src/static/models.yaml"), encoding='utf-8') as f:
            _models = yaml.safe_load(f)

        # 尝试打开一个 models.private.yml 文件，用来覆盖 models.yaml 中的配置
        try:
            with open(Path("src/static/models.private.yml"), encoding='utf-8') as f:
                _models_private = yaml.safe_load(f)
        except FileNotFoundError:
            _models_private = {}

        # 修改为按照子元素合并
        # _models = {**_models, **_models_private}

        self.model_names = {**_models["MODEL_NAMES"], **_models_private.get("MODEL_NAMES", {})}
        self.embed_model_names = {**_models["EMBED_MODEL_INFO"], **_models_private.get("EMBED_MODEL_INFO", {})}
        self.reranker_names = {**_models["RERANKER_LIST"], **_models_private.get("RERANKER_LIST", {})}

    def _save_models_to_file(self):
        _models = {
            "MODEL_NAMES": self.model_names,
            "EMBED_MODEL_INFO": self.embed_model_names,
            "RERANKER_LIST": self.reranker_names,
        }
        with open(Path("src/static/models.private.yml"), 'w', encoding='utf-8') as f:
            yaml.dump(_models, f, indent=2, allow_unicode=True)

    def handle_self(self):
        """
        处理配置
        """
        self.model_dir = os.environ.get("MODEL_DIR", "")

        if self.model_dir:
            if os.path.exists(self.model_dir):
                logger.debug(f"The model directory （{self.model_dir}） contains the following folders: {os.listdir(self.model_dir)}")
            else:
                logger.warning(f"Warning: The model directory （{self.model_dir}） does not exist. If not configured, please ignore it. If configured, please check if the configuration is correct;"
                               "For example, the mapping in the docker-compose file")

        # 检查模型提供商的环境变量
        conds = {}
        self.model_provider_status = {}
        for provider in self.model_names:
            conds[provider] = self.model_names[provider]["env"]
            conds_bool = [bool(os.getenv(_k)) for _k in conds[provider]]
            self.model_provider_status[provider] = all(conds_bool)

        if os.getenv("TAVILY_API_KEY"):
            self.enable_web_search = True

        self.valuable_model_provider = [k for k, v in self.model_provider_status.items() if v]
        assert len(self.valuable_model_provider) > 0, f"No model provider available, please check your `.env` file. API_KEY_LIST: {conds}"

    def load(self):
        """根据传入的文件覆盖掉默认配置"""
        logger.info(f"Loading config from {self.filename}")
        if self.filename is not None and os.path.exists(self.filename):

            if self.filename.endswith(".json"):
                with open(self.filename) as f:
                    content = f.read()
                    if content:
                        local_config = json.loads(content)
                        self.update(local_config)
                    else:
                        print(f"{self.filename} is empty.")

            elif self.filename.endswith(".yaml"):
                with open(self.filename) as f:
                    content = f.read()
                    if content:
                        local_config = yaml.safe_load(content)
                        self.update(local_config)
                    else:
                        print(f"{self.filename} is empty.")
            else:
                logger.warning(f"Unknown config file type {self.filename}")

    def save(self):
        logger.info(f"Saving config to {self.filename}")
        if self.filename is None:
            logger.warning("Config file is not specified, save to default config/base.yaml")
            self.filename = os.path.join(self.save_dir, "config", "base.yaml")
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)

        if self.filename.endswith(".json"):
            with open(self.filename, 'w+') as f:
                json.dump(self.__dict__(), f, indent=4, ensure_ascii=False)
        elif self.filename.endswith(".yaml"):
            with open(self.filename, 'w+') as f:
                yaml.dump(self.__dict__(), f, indent=2, allow_unicode=True)
        else:
            logger.warning(f"Unknown config file type {self.filename}, save as json")
            with open(self.filename, 'w+') as f:
                json.dump(self, f, indent=4)

        logger.info(f"Config file {self.filename} saved")

    def dump_config(self):
        return json.loads(str(self))

    def compare_custom_models(self, value):
        """
        比较 custom_models 中的 api_key，如果输入的 api_key 与当前的 api_key 相同，则不修改
        如果输入的 api_key 为 DEFAULT_MOCK_API，则使用当前的 api_key
        """
        current_models_dict = {model["custom_id"]: model.get("api_key") for model in self.get("custom_models", [])}

        for i, model in enumerate(value):
            input_custom_id = model.get("custom_id")
            input_api_key = model.get("api_key")

            if input_custom_id in current_models_dict:
                current_api_key = current_models_dict[input_custom_id]
                if input_api_key == DEFAULT_MOCK_API or input_api_key == current_api_key:
                    value[i]["api_key"] = current_api_key

        return value
    
    def get_database_config(self, db_name: str) -> Dict[str, Any]:
        """获取数据库配置"""
        return self.database.get_db_config(db_name)
    
    def get_database_connection_string(self, db_name: str) -> str:
        """获取数据库连接字符串"""
        return self.database.get_connection_string(db_name)
    
    def validate_database_config(self, db_name: str) -> bool:
        """验证数据库配置"""
        return self.database.validate_config(db_name)
    
    def set_database_environment(self, environment: str):
        """设置数据库环境"""
        self.database.set_environment(environment)
    
    def get_all_database_names(self) -> list:
        """获取所有数据库名称"""
        return self.database.get_all_db_names()
    
    def is_database_available(self, db_name: str) -> bool:
        """检查数据库配置是否可用"""
        try:
            config = self.database.get_db_config(db_name)
            return bool(config and config.get('host') and config.get('database'))
        except Exception as e:
            logger.error(f"Error checking database availability for {db_name}: {e}")
            return False
