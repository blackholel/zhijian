"""
智能体配置加载器

参考 DeerFlow 的配置加载策略，支持多层配置源
"""

import os
import yaml
import json
from typing import Dict, Any, Optional, Union
from pathlib import Path
import logging
from .agent_config import AgentConfig, LLMConfig, AgentType
from ..base.exceptions import AgentConfigError

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent.parent / "static" / "agents"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
    def load_from_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """从文件加载配置"""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise AgentConfigError(f"配置文件不存在: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yml', '.yaml']:
                    return yaml.safe_load(f) or {}
                elif file_path.suffix.lower() == '.json':
                    return json.load(f)
                else:
                    raise AgentConfigError(f"不支持的配置文件格式: {file_path.suffix}")
        except Exception as e:
            raise AgentConfigError(f"加载配置文件失败: {e}")
    
    def load_from_env(self, prefix: str = "AGENT_") -> Dict[str, Any]:
        """从环境变量加载配置"""
        config = {}
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                
                # 处理嵌套配置
                if "__" in config_key:
                    parts = config_key.split("__")
                    current = config
                    for part in parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = self._convert_env_value(value)
                else:
                    config[config_key] = self._convert_env_value(value)
        
        return config
    
    def _convert_env_value(self, value: str) -> Union[str, int, float, bool, list]:
        """转换环境变量值"""
        # 布尔值
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # 数字
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass
        
        # 列表 (逗号分隔)
        if ',' in value:
            return [item.strip() for item in value.split(',') if item.strip()]
        
        return value
    
    def load_default_config(self, agent_type: AgentType) -> Dict[str, Any]:
        """加载默认配置"""
        defaults = {
            "agent_type": agent_type.value,
            "version": "1.0.0",
            "llm_config": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 2000,
                "timeout": 30,
                "retry_attempts": 3
            },
            "resource_limits": {
                "max_knowledge_bases": 10,
                "max_mcp_tools": 20,
                "max_concurrent_tasks": 5,
                "max_execution_time": 300,
                "max_memory_usage": 1024
            },
            "security_config": {
                "enable_sandbox": True,
                "allowed_domains": [],
                "blocked_domains": [],
                "max_file_size": 10485760,
                "allowed_file_types": [".txt", ".md", ".pdf", ".doc", ".docx"]
            },
            "auto_start": False,
            "enable_logging": True,
            "log_level": "INFO",
            "tags": [],
            "metadata": {}
        }
        
        # 根据智能体类型设置特定默认值
        type_specific_defaults = self._get_type_specific_defaults(agent_type)
        defaults.update(type_specific_defaults)
        
        return defaults
    
    def _get_type_specific_defaults(self, agent_type: AgentType) -> Dict[str, Any]:
        """获取类型特定的默认配置"""
        type_defaults = {
            AgentType.COORDINATOR: {
                "description": "协调器智能体，负责任务分解和流程控制",
                "capabilities": [
                    {
                        "name": "task_coordination",
                        "description": "任务协调能力",
                        "required_permissions": ["agent:coordinate"],
                        "supported_knowledge_bases": ["*"],
                        "supported_mcp_tools": ["*"]
                    }
                ]
            },
            AgentType.RESEARCHER: {
                "description": "研究员智能体，负责信息收集和分析", 
                "capabilities": [
                    {
                        "name": "information_research",
                        "description": "信息研究能力",
                        "required_permissions": ["kb:read", "mcp_tool:search"],
                        "supported_knowledge_bases": ["*"],
                        "supported_mcp_tools": ["search", "crawler", "api"]
                    }
                ]
            },
            AgentType.ANALYZER: {
                "description": "分析员智能体，负责数据分析和洞察",
                "capabilities": [
                    {
                        "name": "data_analysis", 
                        "description": "数据分析能力",
                        "required_permissions": ["kb:read", "mcp_tool:analyze"],
                        "supported_knowledge_bases": ["*"],
                        "supported_mcp_tools": ["analyzer", "stats", "ml"]
                    }
                ]
            },
            AgentType.REPORTER: {
                "description": "报告员智能体，负责报告生成和总结",
                "capabilities": [
                    {
                        "name": "report_generation",
                        "description": "报告生成能力", 
                        "required_permissions": ["kb:read", "mcp_tool:generate"],
                        "supported_knowledge_bases": ["*"],
                        "supported_mcp_tools": ["generator", "formatter", "export"]
                    }
                ]
            }
        }
        
        return type_defaults.get(agent_type, {})
    
    def merge_configs(self, *configs: Dict[str, Any]) -> Dict[str, Any]:
        """合并多个配置"""
        merged = {}
        
        for config in configs:
            merged = self._deep_merge(merged, config)
        
        return merged
    
    def _deep_merge(self, dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = dict1.copy()
        
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def validate_config(self, config_data: Dict[str, Any]) -> None:
        """验证配置"""
        required_fields = ["name", "description", "agent_type", "user_id", "llm_config"]
        
        for field in required_fields:
            if field not in config_data:
                raise AgentConfigError(f"缺少必需字段: {field}")
        
        # 验证 agent_type
        try:
            AgentType(config_data["agent_type"])
        except ValueError:
            raise AgentConfigError(f"无效的智能体类型: {config_data['agent_type']}")
    
    def save_config(self, config: AgentConfig, file_path: Union[str, Path]) -> None:
        """保存配置到文件"""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            config_data = config.dict()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yml', '.yaml']:
                    yaml.safe_dump(config_data, f, default_flow_style=False, allow_unicode=True)
                elif file_path.suffix.lower() == '.json':
                    json.dump(config_data, f, indent=2, ensure_ascii=False, default=str)
                else:
                    raise AgentConfigError(f"不支持的配置文件格式: {file_path.suffix}")
                    
            logger.info(f"配置已保存到: {file_path}")
        except Exception as e:
            raise AgentConfigError(f"保存配置文件失败: {e}")


def load_agent_config(
    config_file: Optional[Union[str, Path]] = None,
    agent_type: Optional[AgentType] = None,
    env_prefix: str = "AGENT_",
    **kwargs
) -> AgentConfig:
    """
    加载智能体配置
    
    优先级：kwargs > 环境变量 > 配置文件 > 默认配置
    """
    loader = ConfigLoader()
    
    try:
        # 1. 加载默认配置
        if agent_type:
            config_data = loader.load_default_config(agent_type)
        else:
            config_data = {}
        
        # 2. 加载配置文件
        if config_file:
            file_config = loader.load_from_file(config_file)
            config_data = loader.merge_configs(config_data, file_config)
        
        # 3. 加载环境变量
        env_config = loader.load_from_env(env_prefix)
        if env_config:
            config_data = loader.merge_configs(config_data, env_config)
        
        # 4. 应用显式参数
        if kwargs:
            config_data = loader.merge_configs(config_data, kwargs)
        
        # 5. 验证配置
        loader.validate_config(config_data)
        
        # 6. 创建配置对象
        return AgentConfig(**config_data)
        
    except Exception as e:
        logger.error(f"加载智能体配置失败: {e}")
        raise AgentConfigError(f"配置加载失败: {e}")


# 预定义配置模板
AGENT_CONFIG_TEMPLATES = {
    "coordinator": {
        "name": "协调器",
        "description": "任务协调和流程控制智能体",
        "agent_type": "coordinator",
        "capabilities": [
            {
                "name": "task_coordination",
                "description": "任务协调能力",
                "required_permissions": ["agent:coordinate", "kb:read"],
                "supported_knowledge_bases": ["*"],
                "supported_mcp_tools": ["*"]
            }
        ]
    },
    "researcher": {
        "name": "研究员", 
        "description": "信息收集和分析智能体",
        "agent_type": "researcher",
        "capabilities": [
            {
                "name": "information_research",
                "description": "信息研究能力",
                "required_permissions": ["kb:read", "mcp_tool:search"],
                "supported_knowledge_bases": ["*"],
                "supported_mcp_tools": ["search", "crawler", "api"]
            }
        ]
    }
}