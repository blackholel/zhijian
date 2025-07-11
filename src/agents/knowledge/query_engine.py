"""
知识库查询引擎

基于 LightRAG 的统一查询接口，参考 DeerFlow 的查询策略
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from src.core.unified_lightrag_kb import UnifiedLightRAGKnowledgeBase

logger = logging.getLogger(__name__)


class QueryMode(str, Enum):
    """查询模式"""
    NAIVE = "naive"                    # 简单查询
    LOCAL = "local"                   # 本地查询  
    GLOBAL = "global"                 # 全局查询
    HYBRID = "hybrid"                 # 混合查询（推荐）


class QueryResult(BaseModel):
    """查询结果"""
    content: str = Field(..., description="内容")
    score: float = Field(..., description="相关性分数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    source_file: Optional[str] = Field(default=None, description="源文件")
    source_kb: Optional[str] = Field(default=None, description="源知识库")
    source_name: Optional[str] = Field(default=None, description="源知识库名称")
    chunk_id: Optional[str] = Field(default=None, description="文本块ID")
    position: Optional[Dict[str, int]] = Field(default=None, description="位置信息")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class QueryEngine:
    """查询引擎
    
    封装 LightRAG 提供统一的查询接口
    """
    
    def __init__(self, kb_id: str, kb_name: str):
        self.kb_id = kb_id
        self.kb_name = kb_name
        self.lightrag: Optional[LightRAGManager] = None
        
        # 查询统计
        self.query_count = 0
        self.total_query_time = 0.0
        self.last_query_time: Optional[datetime] = None
        
        # 性能配置
        self.default_timeout = 30.0
        self.max_retries = 3
        
        logger.info(f"查询引擎初始化: {kb_name} ({kb_id})")
    
    async def initialize(self) -> bool:
        """初始化查询引擎"""
        try:
            # 初始化 LightRAG
            self.lightrag = LightRAGManager()
            
            # 为特定知识库初始化
            await self.lightrag.initialize(self.kb_id)
            
            logger.info(f"查询引擎初始化完成: {self.kb_name}")
            return True
            
        except Exception as e:
            logger.error(f"查询引擎初始化失败: {self.kb_name} - {e}")
            return False
    
    async def query(
        self,
        query: str,
        mode: QueryMode = QueryMode.HYBRID,
        limit: int = 10,
        min_score: float = 0.0,
        timeout: Optional[float] = None
    ) -> List[QueryResult]:
        """执行查询"""
        if not self.lightrag:
            raise RuntimeError("查询引擎未初始化")
        
        start_time = datetime.now()
        query_timeout = timeout or self.default_timeout
        
        try:
            # 更新统计
            self.query_count += 1
            self.last_query_time = start_time
            
            # 执行查询（带超时）
            raw_results = await asyncio.wait_for(
                self._execute_lightrag_query(query, mode, limit),
                timeout=query_timeout
            )
            
            # 转换结果格式
            results = self._convert_results(raw_results, min_score)
            
            # 更新性能统计
            query_time = (datetime.now() - start_time).total_seconds()
            self.total_query_time += query_time
            
            logger.debug(f"查询完成: {query[:50]}..., 模式: {mode}, 结果: {len(results)}, 耗时: {query_time:.2f}s")
            
            return results
            
        except asyncio.TimeoutError:
            logger.warning(f"查询超时: {query[:50]}..., 超时时间: {query_timeout}s")
            return []
            
        except Exception as e:
            logger.error(f"查询执行失败: {query[:50]}... - {e}")
            return []
    
    async def _execute_lightrag_query(
        self,
        query: str,
        mode: QueryMode,
        limit: int
    ) -> List[Dict[str, Any]]:
        """执行 LightRAG 查询"""
        try:
            # 根据查询模式调用不同的 LightRAG 方法
            if mode == QueryMode.NAIVE:
                results = await self.lightrag.query_naive(query, limit=limit)
            elif mode == QueryMode.LOCAL:
                results = await self.lightrag.query_local(query, limit=limit)
            elif mode == QueryMode.GLOBAL:
                results = await self.lightrag.query_global(query, limit=limit)
            elif mode == QueryMode.HYBRID:
                results = await self.lightrag.query_hybrid(query, limit=limit)
            else:
                # 默认使用混合模式
                results = await self.lightrag.query_hybrid(query, limit=limit)
            
            return results if results else []
            
        except Exception as e:
            logger.error(f"LightRAG 查询失败: {e}")
            return []
    
    def _convert_results(
        self,
        raw_results: List[Dict[str, Any]],
        min_score: float = 0.0
    ) -> List[QueryResult]:
        """转换查询结果格式"""
        results = []
        
        for item in raw_results:
            try:
                # 提取分数
                score = float(item.get('score', 0.0))
                
                # 过滤低分结果
                if score < min_score:
                    continue
                
                # 构建查询结果
                result = QueryResult(
                    content=item.get('content', ''),
                    score=score,
                    metadata=item.get('metadata', {}),
                    source_file=item.get('source_file'),
                    chunk_id=item.get('chunk_id'),
                    position=item.get('position')
                )
                
                results.append(result)
                
            except Exception as e:
                logger.warning(f"转换查询结果失败: {e}")
                continue
        
        # 按分数降序排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results
    
    async def batch_query(
        self,
        queries: List[str],
        mode: QueryMode = QueryMode.HYBRID,
        limit: int = 10,
        min_score: float = 0.0
    ) -> Dict[str, List[QueryResult]]:
        """批量查询"""
        results = {}
        
        # 并发执行查询
        tasks = []
        for query in queries:
            task = self.query(query, mode, limit, min_score)
            tasks.append((query, task))
        
        # 等待所有查询完成
        for query, task in tasks:
            try:
                query_results = await task
                results[query] = query_results
            except Exception as e:
                logger.error(f"批量查询失败: {query} - {e}")
                results[query] = []
        
        return results
    
    async def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0
    ) -> List[QueryResult]:
        """语义搜索"""
        return await self.query(
            query=query,
            mode=QueryMode.LOCAL,  # 本地语义搜索
            limit=top_k,
            min_score=min_score
        )
    
    async def keyword_search(
        self,
        keywords: List[str],
        limit: int = 10,
        min_score: float = 0.0
    ) -> List[QueryResult]:
        """关键词搜索"""
        # 构建关键词查询
        query = " ".join(keywords)
        
        return await self.query(
            query=query,
            mode=QueryMode.NAIVE,  # 简单关键词匹配
            limit=limit,
            min_score=min_score
        )
    
    async def get_related_content(
        self,
        content_id: str,
        limit: int = 5
    ) -> List[QueryResult]:
        """获取相关内容"""
        try:
            # 首先获取内容
            if not self.lightrag:
                return []
            
            # 获取相关内容
            related = await self.lightrag.get_related_content(content_id, limit=limit)
            
            return self._convert_results(related)
            
        except Exception as e:
            logger.error(f"获取相关内容失败: {content_id} - {e}")
            return []
    
    async def explain_query(self, query: str) -> Dict[str, Any]:
        """解释查询"""
        try:
            if not self.lightrag:
                return {}
            
            # 分析查询
            explanation = await self.lightrag.explain_query(query)
            
            return {
                "query": query,
                "analysis": explanation,
                "suggested_mode": self._suggest_query_mode(query),
                "estimated_results": self._estimate_result_count(query)
            }
            
        except Exception as e:
            logger.error(f"查询解释失败: {query} - {e}")
            return {}
    
    def _suggest_query_mode(self, query: str) -> QueryMode:
        """建议查询模式"""
        # 简化的启发式规则
        if len(query.split()) <= 3:
            return QueryMode.LOCAL  # 短查询用本地模式
        elif "总结" in query or "概述" in query or "整体" in query:
            return QueryMode.GLOBAL  # 总结性查询用全局模式
        else:
            return QueryMode.HYBRID  # 默认混合模式
    
    def _estimate_result_count(self, query: str) -> int:
        """估算结果数量"""
        # 简化实现
        return min(len(query.split()) * 2, 20)
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        avg_query_time = (
            self.total_query_time / self.query_count 
            if self.query_count > 0 else 0.0
        )
        
        return {
            "query_count": self.query_count,
            "total_query_time": self.total_query_time,
            "average_query_time": avg_query_time,
            "last_query_time": self.last_query_time.isoformat() if self.last_query_time else None,
            "kb_id": self.kb_id,
            "kb_name": self.kb_name
        }
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.lightrag:
                await self.lightrag.cleanup()
                self.lightrag = None
            
            logger.info(f"查询引擎清理完成: {self.kb_name}")
            
        except Exception as e:
            logger.error(f"查询引擎清理失败: {self.kb_name} - {e}")


class QueryOptimizer:
    """查询优化器"""
    
    @staticmethod
    def optimize_query(query: str) -> str:
        """优化查询语句"""
        # 去除多余空格
        query = " ".join(query.split())
        
        # 去除特殊字符（可选）
        # query = re.sub(r'[^\w\s\u4e00-\u9fff]', '', query)
        
        # 限制长度
        if len(query) > 200:
            query = query[:200] + "..."
        
        return query
    
    @staticmethod
    def suggest_alternatives(query: str) -> List[str]:
        """建议替代查询"""
        alternatives = []
        
        # 简化版本
        words = query.split()
        if len(words) > 3:
            # 取前半部分
            alternatives.append(" ".join(words[:len(words)//2]))
            # 取后半部分
            alternatives.append(" ".join(words[len(words)//2:]))
        
        # 添加同义词扩展等...
        
        return alternatives
    
    @staticmethod
    def expand_query(query: str, synonyms: Dict[str, List[str]]) -> str:
        """扩展查询（添加同义词）"""
        words = query.split()
        expanded_words = []
        
        for word in words:
            expanded_words.append(word)
            if word in synonyms:
                expanded_words.extend(synonyms[word][:2])  # 添加最多2个同义词
        
        return " ".join(expanded_words)