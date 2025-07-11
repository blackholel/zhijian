"""
提示词模板管理系统
支持动态模板加载、变量替换和多语言支持
"""

import asyncio
import os
import json
import yaml
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
import jinja2

from src.utils.logging_config import logger


class TemplateType(str, Enum):
    """模板类型"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    AGENT = "agent"


class TemplateFormat(str, Enum):
    """模板格式"""
    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"


@dataclass
class PromptTemplate:
    """提示词模板"""
    template_id: str
    name: str
    description: str
    template_type: TemplateType
    format: TemplateFormat
    content: str
    variables: List[str]
    required_variables: List[str]
    optional_variables: List[str]
    default_values: Dict[str, Any]
    version: str = "1.0"
    author: str = "system"
    tags: List[str] = None
    created_at: str = None
    updated_at: str = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = self.created_at


class TemplateManager:
    """模板管理器"""
    
    def __init__(self, template_dir: Optional[str] = None):
        self.template_dir = template_dir or os.path.join(os.path.dirname(__file__), "templates")
        self.templates: Dict[str, PromptTemplate] = {}
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_dir),
            autoescape=jinja2.select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
        self._lock = asyncio.Lock()
        
        # 注册自定义过滤器
        self.jinja_env.filters['timestamp'] = self._timestamp_filter
        self.jinja_env.filters['format_list'] = self._format_list_filter
        self.jinja_env.filters['truncate_text'] = self._truncate_text_filter
    
    async def load_templates(self):
        """加载模板"""
        async with self._lock:
            template_path = Path(self.template_dir)
            
            if not template_path.exists():
                logger.warning(f"模板目录不存在: {self.template_dir}")
                return
            
            # 加载YAML模板配置
            for config_file in template_path.glob("*.yaml"):
                await self._load_template_config(config_file)
            
            # 加载JSON模板配置
            for config_file in template_path.glob("*.json"):
                await self._load_template_config(config_file)
            
            # 加载文本模板
            for template_file in template_path.glob("*.txt"):
                await self._load_text_template(template_file)
            
            # 加载Markdown模板
            for template_file in template_path.glob("*.md"):
                await self._load_markdown_template(template_file)
            
            logger.info(f"加载了 {len(self.templates)} 个模板")
    
    async def _load_template_config(self, config_file: Path):
        """加载模板配置文件"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                if config_file.suffix == '.yaml':
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
            
            # 处理多个模板
            templates = config.get('templates', [config])
            
            for template_data in templates:
                template = PromptTemplate(
                    template_id=template_data['template_id'],
                    name=template_data['name'],
                    description=template_data.get('description', ''),
                    template_type=TemplateType(template_data.get('type', 'system')),
                    format=TemplateFormat(template_data.get('format', 'text')),
                    content=template_data['content'],
                    variables=template_data.get('variables', []),
                    required_variables=template_data.get('required_variables', []),
                    optional_variables=template_data.get('optional_variables', []),
                    default_values=template_data.get('default_values', {}),
                    version=template_data.get('version', '1.0'),
                    author=template_data.get('author', 'system'),
                    tags=template_data.get('tags', [])
                )
                
                self.templates[template.template_id] = template
                
        except Exception as e:
            logger.error(f"加载模板配置失败 {config_file}: {e}")
    
    async def _load_text_template(self, template_file: Path):
        """加载文本模板"""
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 从文件名生成模板ID
            template_id = template_file.stem
            
            # 提取变量
            variables = self._extract_variables(content)
            
            template = PromptTemplate(
                template_id=template_id,
                name=template_id.replace('_', ' ').title(),
                description=f"从文件 {template_file.name} 加载的模板",
                template_type=TemplateType.USER,
                format=TemplateFormat.TEXT,
                content=content,
                variables=variables,
                required_variables=variables,
                optional_variables=[],
                default_values={}
            )
            
            self.templates[template_id] = template
            
        except Exception as e:
            logger.error(f"加载文本模板失败 {template_file}: {e}")
    
    async def _load_markdown_template(self, template_file: Path):
        """加载Markdown模板"""
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            template_id = template_file.stem
            variables = self._extract_variables(content)
            
            template = PromptTemplate(
                template_id=template_id,
                name=template_id.replace('_', ' ').title(),
                description=f"从文件 {template_file.name} 加载的Markdown模板",
                template_type=TemplateType.SYSTEM,
                format=TemplateFormat.MARKDOWN,
                content=content,
                variables=variables,
                required_variables=variables,
                optional_variables=[],
                default_values={}
            )
            
            self.templates[template_id] = template
            
        except Exception as e:
            logger.error(f"加载Markdown模板失败 {template_file}: {e}")
    
    def _extract_variables(self, content: str) -> List[str]:
        """提取模板变量"""
        import re
        
        # 提取Jinja2变量
        variables = []
        
        # 匹配 {{ variable }} 格式
        var_pattern = r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
        matches = re.findall(var_pattern, content)
        variables.extend(matches)
        
        # 匹配 {% for var in vars %} 格式
        for_pattern = r'\{\%\s*for\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\%\}'
        matches = re.findall(for_pattern, content)
        for match in matches:
            variables.extend(match)
        
        return list(set(variables))
    
    async def register_template(self, template: PromptTemplate):
        """注册模板"""
        async with self._lock:
            self.templates[template.template_id] = template
            logger.info(f"注册模板: {template.template_id}")
    
    async def get_template(self, template_id: str) -> Optional[PromptTemplate]:
        """获取模板"""
        return self.templates.get(template_id)
    
    async def list_templates(
        self,
        template_type: Optional[TemplateType] = None,
        tags: Optional[List[str]] = None
    ) -> List[PromptTemplate]:
        """列出模板"""
        templates = list(self.templates.values())
        
        if template_type:
            templates = [t for t in templates if t.template_type == template_type]
        
        if tags:
            templates = [t for t in templates if any(tag in t.tags for tag in tags)]
        
        return templates
    
    async def render_template(
        self,
        template_id: str,
        variables: Dict[str, Any],
        validate: bool = True
    ) -> str:
        """渲染模板"""
        template = await self.get_template(template_id)
        
        if not template:
            raise ValueError(f"模板不存在: {template_id}")
        
        if validate:
            await self._validate_variables(template, variables)
        
        # 合并默认值
        render_variables = {**template.default_values, **variables}
        
        try:
            # 使用Jinja2渲染
            jinja_template = self.jinja_env.from_string(template.content)
            rendered = jinja_template.render(**render_variables)
            
            return rendered
            
        except Exception as e:
            logger.error(f"渲染模板失败 {template_id}: {e}")
            raise
    
    async def _validate_variables(self, template: PromptTemplate, variables: Dict[str, Any]):
        """验证变量"""
        # 检查必需变量
        missing_vars = []
        for required_var in template.required_variables:
            if required_var not in variables:
                missing_vars.append(required_var)
        
        if missing_vars:
            raise ValueError(f"缺少必需变量: {missing_vars}")
    
    async def create_template_from_text(
        self,
        template_id: str,
        name: str,
        content: str,
        template_type: TemplateType = TemplateType.USER,
        description: str = "",
        tags: List[str] = None
    ) -> PromptTemplate:
        """从文本创建模板"""
        variables = self._extract_variables(content)
        
        template = PromptTemplate(
            template_id=template_id,
            name=name,
            description=description,
            template_type=template_type,
            format=TemplateFormat.TEXT,
            content=content,
            variables=variables,
            required_variables=variables,
            optional_variables=[],
            default_values={},
            tags=tags or []
        )
        
        await self.register_template(template)
        return template
    
    async def save_template(self, template: PromptTemplate, file_path: Optional[str] = None):
        """保存模板到文件"""
        if not file_path:
            file_path = os.path.join(self.template_dir, f"{template.template_id}.yaml")
        
        template_data = {
            'template_id': template.template_id,
            'name': template.name,
            'description': template.description,
            'type': template.template_type.value,
            'format': template.format.value,
            'content': template.content,
            'variables': template.variables,
            'required_variables': template.required_variables,
            'optional_variables': template.optional_variables,
            'default_values': template.default_values,
            'version': template.version,
            'author': template.author,
            'tags': template.tags
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(template_data, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"模板已保存到: {file_path}")
    
    # 自定义过滤器
    def _timestamp_filter(self, value: str) -> str:
        """时间戳过滤器"""
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return value
    
    def _format_list_filter(self, value: List[Any], separator: str = ", ") -> str:
        """列表格式化过滤器"""
        if not isinstance(value, list):
            return str(value)
        return separator.join(str(item) for item in value)
    
    def _truncate_text_filter(self, value: str, length: int = 100) -> str:
        """文本截断过滤器"""
        if len(value) <= length:
            return value
        return value[:length] + "..."


# 全局模板管理器
template_manager = TemplateManager()


async def get_template_manager() -> TemplateManager:
    """获取模板管理器"""
    return template_manager


# 预定义模板
PREDEFINED_TEMPLATES = {
    "coordinator_system": {
        "template_id": "coordinator_system",
        "name": "协调器系统提示",
        "description": "协调器Agent的系统提示词",
        "type": "system",
        "content": """你是一个智能研究协调器，负责分解复杂的研究任务并协调多个专业Agent。

你的职责包括：
1. 分析研究目标和需求
2. 制定详细的研究计划
3. 分配任务给合适的Agent
4. 监控执行进度
5. 协调Agent之间的协作

可用的Agent类型：
- 研究员Agent: 负责信息收集和初步分析
- 分析员Agent: 负责深度分析和洞察发现
- 报告员Agent: 负责结果整理和报告生成

可用资源：
- 知识库: {{ knowledge_bases | format_list }}
- MCP工具: {{ mcp_tools | format_list }}

当前任务：{{ task_description }}
研究目标：{{ research_objective }}

请制定详细的执行计划，包括：
1. 任务分解
2. Agent分配
3. 执行顺序
4. 依赖关系
5. 预期产出""",
        "variables": ["knowledge_bases", "mcp_tools", "task_description", "research_objective"],
        "required_variables": ["task_description", "research_objective"],
        "optional_variables": ["knowledge_bases", "mcp_tools"],
        "default_values": {
            "knowledge_bases": [],
            "mcp_tools": []
        }
    },
    
    "researcher_system": {
        "template_id": "researcher_system",
        "name": "研究员系统提示",
        "description": "研究员Agent的系统提示词",
        "type": "system",
        "content": """你是一个专业的研究员Agent，擅长信息收集、数据分析和初步研究。

你的职责包括：
1. 根据研究主题收集相关信息
2. 从知识库中查找相关资料
3. 使用MCP工具获取外部数据
4. 对收集的信息进行初步整理和分析
5. 提供可靠的信息摘要

可用的知识库：
{% for kb in knowledge_bases %}
- {{ kb.name }}: {{ kb.description }}
{% endfor %}

可用的MCP工具：
{% for tool in mcp_tools %}
- {{ tool.name }}: {{ tool.description }}
{% endfor %}

当前研究任务：{{ task_description }}
具体要求：{{ requirements }}

请按照以下格式提供研究结果：
1. 信息来源
2. 关键发现
3. 数据摘要
4. 初步分析
5. 后续建议""",
        "variables": ["knowledge_bases", "mcp_tools", "task_description", "requirements"],
        "required_variables": ["task_description"],
        "optional_variables": ["knowledge_bases", "mcp_tools", "requirements"],
        "default_values": {
            "knowledge_bases": [],
            "mcp_tools": [],
            "requirements": "请提供全面的研究结果"
        }
    }
}


async def setup_predefined_templates():
    """设置预定义模板"""
    for template_data in PREDEFINED_TEMPLATES.values():
        template = PromptTemplate(
            template_id=template_data['template_id'],
            name=template_data['name'],
            description=template_data['description'],
            template_type=TemplateType(template_data['type']),
            format=TemplateFormat.TEXT,
            content=template_data['content'],
            variables=template_data['variables'],
            required_variables=template_data['required_variables'],
            optional_variables=template_data['optional_variables'],
            default_values=template_data['default_values']
        )
        
        await template_manager.register_template(template)
    
    logger.info("预定义模板设置完成")