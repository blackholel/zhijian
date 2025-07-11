"""
提示词模板管理模块
"""

from .template_manager import (
    template_manager,
    TemplateManager,
    PromptTemplate,
    TemplateType,
    TemplateFormat,
    get_template_manager,
    setup_predefined_templates,
    PREDEFINED_TEMPLATES
)

__all__ = [
    'template_manager',
    'TemplateManager',
    'PromptTemplate',
    'TemplateType',
    'TemplateFormat',
    'get_template_manager',
    'setup_predefined_templates',
    'PREDEFINED_TEMPLATES'
]