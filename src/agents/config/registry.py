"""
智能体配置注册表
管理和缓存智能体配置，提供配置发现和验证功能
"""

import asyncio
import os
import json
import yaml
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from .agent_config import AgentConfig, AgentType
from src.utils.logging_config import logger


class AgentConfigRegistry:
    """智能体配置注册表"""
    
    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = config_dir or os.path.join(os.path.dirname(__file__), "../../static/agents")
        self.configs: Dict[str, AgentConfig] = {}
        self.config_templates: Dict[AgentType, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._last_scan_time: Optional[datetime] = None
    
    async def initialize(self):
        """初始化注册表"""
        await self.scan_configs()
        await self.load_default_templates()
        logger.info(f"智能体配置注册表初始化完成，加载了 {len(self.configs)} 个配置")
    
    async def scan_configs(self):
        """扫描配置目录"""
        async with self._lock:
            config_path = Path(self.config_dir)
            
            if not config_path.exists():
                logger.warning(f"智能体配置目录不存在: {self.config_dir}")
                # 创建目录
                config_path.mkdir(parents=True, exist_ok=True)
                await self.create_default_configs()
                return
            
            # 扫描YAML配置文件
            for config_file in config_path.glob("*.yaml"):
                await self._load_config_file(config_file)
            
            # 扫描JSON配置文件
            for config_file in config_path.glob("*.json"):
                await self._load_config_file(config_file)
            
            self._last_scan_time = datetime.now()
    
    async def _load_config_file(self, config_file: Path):
        """加载配置文件"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                if config_file.suffix == '.yaml':
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
            
            # 支持单个配置或配置数组
            configs = data if isinstance(data, list) else [data]
            
            for config_data in configs:
                if self._validate_config_data(config_data):
                    config = AgentConfig(**config_data)
                    self.configs[config.agent_id] = config
                    logger.debug(f"加载智能体配置: {config.agent_id}")
                
        except Exception as e:
            logger.error(f"加载配置文件失败 {config_file}: {e}")
    
    def _validate_config_data(self, config_data: Dict[str, Any]) -> bool:
        """验证配置数据"""
        required_fields = ['agent_id', 'name', 'agent_type']
        
        for field in required_fields:
            if field not in config_data:
                logger.warning(f"配置缺少必需字段 {field}: {config_data}")
                return False
        
        return True
    
    async def register_config(self, config: AgentConfig):
        """注册配置"""
        async with self._lock:
            self.configs[config.agent_id] = config
            logger.info(f"注册智能体配置: {config.agent_id}")
    
    async def get_config(self, agent_id: str) -> Optional[AgentConfig]:
        """获取配置"""
        return self.configs.get(agent_id)
    
    async def list_configs(self, agent_type: Optional[AgentType] = None) -> List[AgentConfig]:
        """列出配置"""
        configs = list(self.configs.values())
        
        if agent_type:
            configs = [c for c in configs if c.agent_type == agent_type]
        
        return configs
    
    async def create_config_from_template(
        self,
        agent_id: str,
        name: str,
        agent_type: AgentType,
        **kwargs
    ) -> AgentConfig:
        """从模板创建配置"""
        template = self.config_templates.get(agent_type, {})
        
        config_data = {
            'agent_id': agent_id,
            'name': name,
            'agent_type': agent_type,
            'description': template.get('description', f'{agent_type.value} agent'),
            **template,
            **kwargs
        }
        
        config = AgentConfig(**config_data)
        await self.register_config(config)
        
        return config
    
    async def save_config(self, config: AgentConfig, file_path: Optional[str] = None):
        """保存配置到文件"""
        if not file_path:
            file_path = os.path.join(self.config_dir, f"{config.agent_id}.yaml")
        
        config_data = config.model_dump()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"智能体配置已保存到: {file_path}")
    
    async def load_default_templates(self):
        """加载默认模板"""
        self.config_templates = {
            AgentType.COORDINATOR: {
                'description': '协调器智能体，负责任务分解和资源协调',
                'capabilities': [
                    {
                        'name': 'task_decomposition',
                        'description': '任务分解能力',
                        'required_permissions': ['agent:coordinate'],
                        'supported_knowledge_bases': [],
                        'supported_mcp_tools': []
                    }
                ],
                'selected_knowledge_bases': [],
                'selected_mcp_tools': [],
                'llm_config': {
                    'provider': 'openai',
                    'model_name': 'gpt-3.5-turbo',
                    'temperature': 0.7,
                    'max_tokens': 4096
                },
                'prompt_templates': {
                    'system': 'coordinator_system',
                    'planning': 'coordinator_planning'
                }
            },
            
            AgentType.RESEARCHER: {
                'description': '研究员智能体，负责信息收集和初步分析',
                'capabilities': [
                    {
                        'name': 'information_gathering',
                        'description': '信息收集能力',
                        'required_permissions': ['knowledge_base:read'],
                        'supported_knowledge_bases': ['*'],
                        'supported_mcp_tools': []
                    }
                ],
                'selected_knowledge_bases': [],
                'selected_mcp_tools': [],
                'llm_config': {
                    'provider': 'openai',
                    'model_name': 'gpt-3.5-turbo',
                    'temperature': 0.3,
                    'max_tokens': 4096
                },
                'prompt_templates': {
                    'system': 'researcher_system',
                    'analysis': 'researcher_analysis'
                }
            },
            
            AgentType.ANALYZER: {
                'description': '分析员智能体，负责深度分析和洞察发现',
                'capabilities': [
                    {
                        'name': 'data_analysis',
                        'description': '数据分析能力',
                        'required_permissions': ['knowledge_base:read'],
                        'supported_knowledge_bases': ['*'],
                        'supported_mcp_tools': []
                    }
                ],
                'selected_knowledge_bases': [],
                'selected_mcp_tools': [],
                'llm_config': {
                    'provider': 'openai',
                    'model_name': 'gpt-4',
                    'temperature': 0.2,
                    'max_tokens': 4096
                },
                'prompt_templates': {
                    'system': 'analyzer_system',
                    'insight': 'analyzer_insight'
                }
            },
            
            AgentType.REPORTER: {
                'description': '报告员智能体，负责结果整理和报告生成',
                'capabilities': [
                    {
                        'name': 'report_generation',
                        'description': '报告生成能力',
                        'required_permissions': ['report:create'],
                        'supported_knowledge_bases': [],
                        'supported_mcp_tools': []
                    }
                ],
                'selected_knowledge_bases': [],
                'selected_mcp_tools': [],
                'llm_config': {
                    'provider': 'openai',
                    'model_name': 'gpt-3.5-turbo',
                    'temperature': 0.5,
                    'max_tokens': 8192
                },
                'prompt_templates': {
                    'system': 'reporter_system',
                    'formatting': 'reporter_formatting'
                }
            }
        }
    
    async def create_default_configs(self):
        """创建默认配置文件"""
        try:
            # 创建示例配置文件
            example_config = {
                'agent_id': 'coordinator_001',
                'name': '默认协调器',
                'description': '示例协调器智能体配置',
                'agent_type': 'coordinator',
                'capabilities': [
                    {
                        'name': 'task_decomposition',
                        'description': '任务分解和协调',
                        'required_permissions': ['agent:coordinate'],
                        'supported_knowledge_bases': [],
                        'supported_mcp_tools': []
                    }
                ],
                'selected_knowledge_bases': [],
                'selected_mcp_tools': [],
                'llm_config': {
                    'provider': 'openai',
                    'model_name': 'gpt-3.5-turbo',
                    'temperature': 0.7,
                    'max_tokens': 4096
                },
                'prompt_templates': {
                    'system': 'coordinator_system'
                },
                'user_id': 'system',
                'organization_id': 'default'
            }
            
            config_file = os.path.join(self.config_dir, "agent_config.example.yaml")
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(example_config, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"创建示例配置文件: {config_file}")
            
        except Exception as e:
            logger.error(f"创建默认配置失败: {e}")


# 全局配置注册表
agent_config_registry = AgentConfigRegistry()


async def get_agent_config_registry() -> AgentConfigRegistry:
    """获取智能体配置注册表"""
    return agent_config_registry