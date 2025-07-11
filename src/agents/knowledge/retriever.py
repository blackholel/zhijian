"""
知识检索器

基于现有的 UnifiedLightRAGKnowledgeBase 实现智能体知识检索功能
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from src.core.unified_lightrag_kb import UnifiedLightRAGKnowledgeBase, get_unified_lightrag_kb

logger = logging.getLogger(__name__)


class RetrievalStrategy(str, Enum):
    """检索策略"""
    NAIVE = "naive"           # 朴素检索
    LOCAL = "local"           # 本地检索
    GLOBAL = "global"         # 全局检索
    HYBRID = "hybrid"         # 混合检索
    MIX = "mix"              # 混合模式（LightRAG默认）


class RetrievalMode(str, Enum):
    """检索模式"""
    CONTEXT_ONLY = "context_only"      # 仅返回上下文
    ANSWER_ONLY = "answer_only"        # 仅返回答案
    FULL_RESPONSE = "full_response"    # 完整响应


class RetrievalResult(BaseModel):
    """检索结果"""
    query: str = Field(..., description="查询文本")
    response: str = Field(..., description="检索响应")
    context: List[str] = Field(default_factory=list, description="上下文片段")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="来源信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    retrieved_at: datetime = Field(default_factory=datetime.now, description="检索时间")
    retrieval_time: Optional[float] = Field(default=None, description="检索耗时(秒)")
    kb_id: Optional[str] = Field(default=None, description="知识库ID")
    strategy: Optional[RetrievalStrategy] = Field(default=None, description="检索策略")


class KnowledgeRetriever:
    """
    知识检索器
    
    基于现有的 UnifiedLightRAGKnowledgeBase 提供智能体知识检索功能
    """
    
    def __init__(self, kb_id: Optional[str] = None):
        """
        初始化知识检索器
        
        Args:
            kb_id: 默认知识库ID，如果不指定则需要在检索时指定
        """
        self.default_kb_id = kb_id
        self.unified_kb: UnifiedLightRAGKnowledgeBase = get_unified_lightrag_kb()
        self._retrieval_cache: Dict[str, RetrievalResult] = {}
        self._cache_size_limit = 100
        
        logger.info(f"KnowledgeRetriever 初始化完成，默认知识库: {kb_id}")
    
    async def retrieve(
        self,
        query: str,
        kb_id: Optional[str] = None,
        strategy: RetrievalStrategy = RetrievalStrategy.MIX,
        mode: RetrievalMode = RetrievalMode.FULL_RESPONSE,
        top_k: int = 10,
        **kwargs
    ) -> RetrievalResult:
        """
        执行知识检索
        
        Args:
            query: 查询文本
            kb_id: 知识库ID，如果不指定则使用默认知识库
            strategy: 检索策略
            mode: 检索模式
            top_k: 返回结果数量
            **kwargs: 其他查询参数
            
        Returns:
            RetrievalResult: 检索结果
        """
        start_time = datetime.now()
        
        # 确定使用的知识库ID
        target_kb_id = kb_id or self.default_kb_id
        if not target_kb_id:
            raise ValueError("必须指定知识库ID")
        
        try:
            # 检查知识库是否存在
            if target_kb_id not in self.unified_kb.databases_meta:
                raise ValueError(f"知识库不存在: {target_kb_id}")
            
            # 构建查询参数
            query_params = {
                "mode": strategy.value,
                "top_k": top_k,
                "only_need_context": mode == RetrievalMode.CONTEXT_ONLY,
                **kwargs
            }
            
            # 执行查询
            response = await self.unified_kb.aquery(
                query_text=query,
                db_id=target_kb_id,
                **query_params
            )
            
            # 计算检索时间
            retrieval_time = (datetime.now() - start_time).total_seconds()
            
            # 解析响应（根据LightRAG的返回格式调整）
            context_list = []
            sources_list = []
            
            # 如果响应是字符串，直接使用
            if isinstance(response, str):
                response_text = response
            else:
                # 如果响应是结构化数据，解析它
                response_text = str(response)
                # TODO: 根据实际LightRAG返回格式解析上下文和来源
            
            # 构建结果
            result = RetrievalResult(
                query=query,
                response=response_text,
                context=context_list,
                sources=sources_list,
                metadata={
                    "kb_name": self.unified_kb.databases_meta[target_kb_id].get("name", ""),
                    "kb_description": self.unified_kb.databases_meta[target_kb_id].get("description", ""),
                    "query_params": query_params
                },
                retrieved_at=start_time,
                retrieval_time=retrieval_time,
                kb_id=target_kb_id,
                strategy=strategy
            )
            
            # 缓存结果
            await self._cache_result(query, target_kb_id, result)
            
            logger.info(f"检索完成: {query[:50]}... -> {len(response_text)} 字符，耗时 {retrieval_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"检索失败 [{target_kb_id}]: {query[:50]}... -> {e}")
            # 返回错误结果
            return RetrievalResult(
                query=query,
                response=f"检索失败: {str(e)}",
                metadata={"error": str(e)},
                retrieved_at=start_time,
                retrieval_time=(datetime.now() - start_time).total_seconds(),
                kb_id=target_kb_id,
                strategy=strategy
            )
    
    async def batch_retrieve(
        self,
        queries: List[str],
        kb_id: Optional[str] = None,
        strategy: RetrievalStrategy = RetrievalStrategy.MIX,
        **kwargs
    ) -> List[RetrievalResult]:
        """
        批量检索
        
        Args:
            queries: 查询列表
            kb_id: 知识库ID
            strategy: 检索策略
            **kwargs: 其他参数
            
        Returns:
            List[RetrievalResult]: 检索结果列表
        """
        tasks = []
        for query in queries:
            task = self.retrieve(
                query=query,
                kb_id=kb_id,
                strategy=strategy,
                **kwargs
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(RetrievalResult(
                    query=queries[i],
                    response=f"批量检索失败: {str(result)}",
                    metadata={"error": str(result)},
                    retrieved_at=datetime.now()
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def get_available_knowledge_bases(self) -> List[Dict[str, Any]]:
        """
        获取可用的知识库列表
        
        Returns:
            List[Dict]: 知识库信息列表
        """
        try:
            databases_info = self.unified_kb.get_databases()
            return databases_info.get("databases", [])
        except Exception as e:
            logger.error(f"获取知识库列表失败: {e}")
            return []
    
    async def get_knowledge_base_info(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """
        获取知识库信息
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            Dict: 知识库信息
        """
        try:
            if kb_id not in self.unified_kb.databases_meta:
                return None
            
            kb_meta = self.unified_kb.databases_meta[kb_id].copy()
            
            # 统计文件数量
            file_count = 0
            for file_info in self.unified_kb.files_meta.values():
                if file_info.get("database_id") == kb_id:
                    file_count += 1
            
            kb_meta.update({
                "kb_id": kb_id,
                "file_count": file_count,
                "status": "active" if kb_id in self.unified_kb.instances else "inactive"
            })
            
            return kb_meta
            
        except Exception as e:
            logger.error(f"获取知识库信息失败 [{kb_id}]: {e}")
            return None
    
    async def switch_knowledge_base(self, kb_id: str) -> bool:
        """
        切换默认知识库
        
        Args:
            kb_id: 新的知识库ID
            
        Returns:
            bool: 是否切换成功
        """
        try:
            if kb_id not in self.unified_kb.databases_meta:
                logger.warning(f"知识库不存在: {kb_id}")
                return False
            
            self.default_kb_id = kb_id
            logger.info(f"切换默认知识库: {kb_id}")
            return True
            
        except Exception as e:
            logger.error(f"切换知识库失败: {e}")
            return False
    
    async def get_retrieval_statistics(self) -> Dict[str, Any]:
        """
        获取检索统计信息
        
        Returns:
            Dict: 统计信息
        """
        try:
            cache_stats = {
                "cache_size": len(self._retrieval_cache),
                "cache_limit": self._cache_size_limit
            }
            
            kb_stats = {
                "total_knowledge_bases": len(self.unified_kb.databases_meta),
                "active_instances": len(self.unified_kb.instances),
                "total_files": len(self.unified_kb.files_meta)
            }
            
            return {
                "cache_statistics": cache_stats,
                "knowledge_base_statistics": kb_stats,
                "default_kb_id": self.default_kb_id
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    async def _cache_result(self, query: str, kb_id: str, result: RetrievalResult):
        """缓存检索结果"""
        try:
            cache_key = f"{kb_id}:{query}"
            
            # 限制缓存大小
            if len(self._retrieval_cache) >= self._cache_size_limit:
                # 删除最旧的条目
                oldest_key = min(
                    self._retrieval_cache.keys(),
                    key=lambda k: self._retrieval_cache[k].retrieved_at
                )
                del self._retrieval_cache[oldest_key]
            
            self._retrieval_cache[cache_key] = result
            
        except Exception as e:
            logger.warning(f"缓存结果失败: {e}")
    
    async def get_cached_result(self, query: str, kb_id: Optional[str] = None) -> Optional[RetrievalResult]:
        """获取缓存的检索结果"""
        try:
            target_kb_id = kb_id or self.default_kb_id
            if not target_kb_id:
                return None
            
            cache_key = f"{target_kb_id}:{query}"
            return self._retrieval_cache.get(cache_key)
            
        except Exception as e:
            logger.warning(f"获取缓存失败: {e}")
            return None
    
    async def clear_cache(self):
        """清理缓存"""
        self._retrieval_cache.clear()
        logger.info("检索缓存已清理")


# 便捷函数
async def create_retriever(kb_id: Optional[str] = None) -> KnowledgeRetriever:
    """
    创建知识检索器
    
    Args:
        kb_id: 默认知识库ID
        
    Returns:
        KnowledgeRetriever: 检索器实例
    """
    return KnowledgeRetriever(kb_id=kb_id)


async def quick_retrieve(
    query: str,
    kb_id: str,
    strategy: RetrievalStrategy = RetrievalStrategy.MIX
) -> str:
    """
    快速检索（简化接口）
    
    Args:
        query: 查询文本
        kb_id: 知识库ID
        strategy: 检索策略
        
    Returns:
        str: 检索响应
    """
    retriever = KnowledgeRetriever(kb_id=kb_id)
    result = await retriever.retrieve(query=query, strategy=strategy)
    return result.response