from .history import HistoryManager
from .unified_lightrag_kb import UnifiedLightRAGKnowledgeBase, get_unified_lightrag_kb
from .graphbase import GraphDatabase

# 向后兼容性：保持原有接口可用
from .unified_lightrag_kb import UnifiedLightRAGKnowledgeBase as LightRagBasedKB
