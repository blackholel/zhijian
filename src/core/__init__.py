from .history import HistoryManager
from .unified_lightrag_kb import UnifiedLightRAGKnowledgeBase, get_unified_lightrag_kb
from .graphbase import GraphDatabase

# 向后兼容性：保持原有接口可用
from .unified_lightrag_kb import UnifiedLightRAGKnowledgeBase as LightRagBasedKB

# 新增核心模块
from .llm.llm_service import llm_service, LLMService, LLMConfig, LLMProvider
from .streaming.event_manager import (
    event_manager, 
    streaming_manager, 
    progress_tracker,
    EventManager,
    StreamingManager,
    ProgressTracker,
    EventType,
    StreamEvent
)
from .context.context_manager import context_manager, ContextManager, ContextConfig
from .prompts.template_manager import template_manager, TemplateManager, PromptTemplate

__all__ = [
    # 原有模块
    'HistoryManager',
    'UnifiedLightRAGKnowledgeBase',
    'get_unified_lightrag_kb',
    'GraphDatabase',
    'LightRagBasedKB',
    
    # LLM服务
    'llm_service',
    'LLMService',
    'LLMConfig', 
    'LLMProvider',
    
    # 流式管理
    'event_manager',
    'streaming_manager',
    'progress_tracker',
    'EventManager',
    'StreamingManager',
    'ProgressTracker',
    'EventType',
    'StreamEvent',
    
    # 上下文管理
    'context_manager',
    'ContextManager',
    'ContextConfig',
    
    # 模板管理
    'template_manager',
    'TemplateManager',
    'PromptTemplate'
]
