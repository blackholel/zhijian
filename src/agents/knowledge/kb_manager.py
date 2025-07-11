"""
知识库动态加载管理器

结合 DeerFlow 和 Suna 的设计思想，实现智能的知识库管理
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from src.knowledge_base.models.kb_models import KnowledgeDatabase
from src.knowledge_base.services.kb_service import KnowledgeBaseService
from src.auth.services.permission_service import PermissionService
from src.core.unified_lightrag_kb import UnifiedLightRAGKnowledgeBase
from ..base.exceptions import KnowledgeBaseNotFoundError, AgentPermissionError
from .query_engine import QueryEngine, QueryMode, QueryResult

logger = logging.getLogger(__name__)


class KnowledgeBaseWrapper:
    """知识库包装器
    
    提供统一的知识库接口，封装底层实现细节
    """
    
    def __init__(self, kb: KnowledgeDatabase, user_id: str):
        self.kb = kb
        self.user_id = user_id
        self.id = kb.id
        self.name = kb.name
        self.description = kb.description
        self.created_at = kb.created_at
        self.updated_at = kb.updated_at
        
        # 查询引擎
        self.query_engine: Optional[QueryEngine] = None
        
        # 统计信息
        self.file_count = 0
        self.node_count = 0
        self.last_query_time: Optional[datetime] = None
        self.query_count = 0
        
        # 状态
        self.is_initialized = False
        self.is_loading = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> bool:
        """初始化知识库"""
        if self.is_initialized:
            return True
        
        async with self._lock:
            if self.is_initialized:
                return True
            
            try:
                self.is_loading = True
                logger.info(f"初始化知识库: {self.name} ({self.id})")
                
                # 初始化LightRAG查询引擎
                self.query_engine = QueryEngine(
                    kb_id=self.id,
                    kb_name=self.name
                )
                
                await self.query_engine.initialize()
                
                # 加载统计信息
                await self._load_statistics()
                
                self.is_initialized = True
                self.is_loading = False
                
                logger.info(f"知识库初始化完成: {self.name}")
                return True
                
            except Exception as e:
                self.is_loading = False
                logger.error(f"知识库初始化失败: {self.name} - {e}")
                return False
    
    async def _load_statistics(self):
        """加载统计信息"""
        try:
            # TODO: 实现具体的统计信息查询
            # 这里应该调用知识库服务获取文件和节点数量
            from src.knowledge_base.services.kb_service import KnowledgeBaseService
            
            kb_service = KnowledgeBaseService()
            
            # 获取文件数量
            self.file_count = await kb_service.get_file_count(self.id)
            
            # 获取节点数量  
            self.node_count = await kb_service.get_node_count(self.id)
            
        except Exception as e:
            logger.warning(f"加载知识库统计信息失败: {self.name} - {e}")
            self.file_count = 0
            self.node_count = 0
    
    async def query(
        self, 
        query: str, 
        mode: QueryMode = QueryMode.HYBRID,
        limit: int = 10,
        min_score: float = 0.0
    ) -> List[QueryResult]:
        """查询知识库"""
        if not self.is_initialized:
            await self.initialize()
        
        if not self.query_engine:
            raise RuntimeError(f"知识库 {self.name} 未正确初始化")
        
        try:
            # 更新查询统计
            self.last_query_time = datetime.now()
            self.query_count += 1
            
            # 执行查询
            results = await self.query_engine.query(
                query=query,
                mode=mode,
                limit=limit,
                min_score=min_score
            )
            
            logger.debug(f"知识库查询完成: {self.name}, 查询: {query[:50]}..., 结果数: {len(results)}")
            return results
            
        except Exception as e:
            logger.error(f"知识库查询失败: {self.name} - {e}")
            return []
    
    async def get_info(self) -> Dict[str, Any]:
        """获取知识库信息"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "file_count": self.file_count,
            "node_count": self.node_count,
            "query_count": self.query_count,
            "last_query_time": self.last_query_time.isoformat() if self.last_query_time else None,
            "is_initialized": self.is_initialized,
            "is_loading": self.is_loading,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.query_engine:
                await self.query_engine.cleanup()
            
            self.is_initialized = False
            logger.info(f"知识库资源清理完成: {self.name}")
            
        except Exception as e:
            logger.error(f"知识库资源清理失败: {self.name} - {e}")


class KnowledgeBaseManager:
    """知识库管理器
    
    参考 DeerFlow 的资源管理和 Suna 的服务模式
    """
    
    def __init__(self):
        self.kb_service = KnowledgeBaseService()
        # TODO: 正确初始化权限服务，暂时设为None
        self.permission_service = None  # PermissionService()
        
        # 知识库缓存
        self.loaded_kbs: Dict[str, KnowledgeBaseWrapper] = {}
        self.user_kb_cache: Dict[str, List[str]] = {}  # 用户知识库缓存
        
        # 缓存管理
        self.cache_ttl = timedelta(minutes=30)  # 缓存30分钟
        self.last_cache_update: Dict[str, datetime] = {}
        
        # 并发控制
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        
        logger.info("知识库管理器初始化完成")
    
    def _get_lock(self, key: str) -> asyncio.Lock:
        """获取锁"""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
    
    async def load_knowledge_base(self, kb_id: str, user_id: str) -> Optional[KnowledgeBaseWrapper]:
        """加载知识库"""
        cache_key = f"{kb_id}:{user_id}"
        
        # 检查缓存
        if cache_key in self.loaded_kbs:
            kb_wrapper = self.loaded_kbs[cache_key]
            if kb_wrapper.is_initialized:
                return kb_wrapper
        
        async with self._get_lock(cache_key):
            # 双重检查
            if cache_key in self.loaded_kbs:
                kb_wrapper = self.loaded_kbs[cache_key]
                if kb_wrapper.is_initialized:
                    return kb_wrapper
            
            try:
                # 权限检查
                if not await self.permission_service.has_kb_permission(user_id, kb_id, "read"):
                    raise AgentPermissionError(f"用户没有访问知识库 {kb_id} 的权限")
                
                # 获取知识库
                kb = await self.kb_service.get_knowledge_base(kb_id)
                if not kb:
                    raise KnowledgeBaseNotFoundError(kb_id)
                
                # 创建包装器
                kb_wrapper = KnowledgeBaseWrapper(kb, user_id)
                
                # 初始化
                if await kb_wrapper.initialize():
                    self.loaded_kbs[cache_key] = kb_wrapper
                    logger.info(f"知识库加载成功: {kb.name} ({kb_id})")
                    return kb_wrapper
                else:
                    raise RuntimeError(f"知识库初始化失败: {kb_id}")
                
            except Exception as e:
                logger.error(f"加载知识库失败: {kb_id} - {e}")
                return None
    
    async def get_user_knowledge_bases(self, user_id: str, force_reload: bool = False) -> List[KnowledgeBaseWrapper]:
        """获取用户的所有知识库"""
        # 检查缓存
        cache_time = self.last_cache_update.get(user_id)
        if not force_reload and cache_time and datetime.now() - cache_time < self.cache_ttl:
            if user_id in self.user_kb_cache:
                kb_ids = self.user_kb_cache[user_id]
                kbs = []
                for kb_id in kb_ids:
                    kb = await self.load_knowledge_base(kb_id, user_id)
                    if kb:
                        kbs.append(kb)
                return kbs
        
        try:
            # 获取用户可访问的知识库
            user_kbs = await self.kb_service.get_user_knowledge_bases(user_id)
            
            kb_wrappers = []
            kb_ids = []
            
            for kb in user_kbs:
                kb_wrapper = await self.load_knowledge_base(str(kb.id), user_id)
                if kb_wrapper:
                    kb_wrappers.append(kb_wrapper)
                    kb_ids.append(str(kb.id))
            
            # 更新缓存
            self.user_kb_cache[user_id] = kb_ids
            self.last_cache_update[user_id] = datetime.now()
            
            logger.info(f"用户 {user_id} 的知识库加载完成，共 {len(kb_wrappers)} 个")
            return kb_wrappers
            
        except Exception as e:
            logger.error(f"获取用户知识库失败: {user_id} - {e}")
            return []
    
    async def query_knowledge_bases(
        self,
        query: str,
        kb_ids: List[str],
        user_id: str,
        mode: QueryMode = QueryMode.HYBRID,
        limit: int = 10,
        min_score: float = 0.0
    ) -> List[QueryResult]:
        """查询多个知识库"""
        results = []
        
        # 并发查询所有知识库
        tasks = []
        for kb_id in kb_ids:
            kb = await self.load_knowledge_base(kb_id, user_id)
            if kb:
                task = self._query_single_kb(kb, query, mode, limit, min_score)
                tasks.append(task)
        
        if not tasks:
            return results
        
        # 执行并发查询
        kb_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并结果
        for kb_result in kb_results:
            if isinstance(kb_result, Exception):
                logger.error(f"知识库查询异常: {kb_result}")
                continue
            
            if isinstance(kb_result, list):
                results.extend(kb_result)
        
        # 按分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        # 限制结果数量
        return results[:limit]
    
    async def _query_single_kb(
        self,
        kb: KnowledgeBaseWrapper,
        query: str,
        mode: QueryMode,
        limit: int,
        min_score: float
    ) -> List[QueryResult]:
        """查询单个知识库"""
        try:
            results = await kb.query(query, mode, limit, min_score)
            
            # 为结果添加知识库信息
            for result in results:
                result.source_kb = kb.id
                result.source_name = kb.name
            
            return results
            
        except Exception as e:
            logger.error(f"查询知识库失败: {kb.name} - {e}")
            return []
    
    async def get_knowledge_base_info(self, kb_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """获取知识库信息"""
        kb = await self.load_knowledge_base(kb_id, user_id)
        if kb:
            return await kb.get_info()
        return None
    
    async def refresh_knowledge_base(self, kb_id: str, user_id: str) -> bool:
        """刷新知识库"""
        cache_key = f"{kb_id}:{user_id}"
        
        try:
            # 清理现有实例
            if cache_key in self.loaded_kbs:
                await self.loaded_kbs[cache_key].cleanup()
                del self.loaded_kbs[cache_key]
            
            # 重新加载
            kb = await self.load_knowledge_base(kb_id, user_id)
            
            return kb is not None
            
        except Exception as e:
            logger.error(f"刷新知识库失败: {kb_id} - {e}")
            return False
    
    async def cleanup_unused_knowledge_bases(self, max_idle_time: timedelta = timedelta(hours=1)):
        """清理未使用的知识库"""
        now = datetime.now()
        to_remove = []
        
        for cache_key, kb in self.loaded_kbs.items():
            if (kb.last_query_time and 
                now - kb.last_query_time > max_idle_time):
                to_remove.append(cache_key)
        
        for cache_key in to_remove:
            try:
                kb = self.loaded_kbs[cache_key]
                await kb.cleanup()
                del self.loaded_kbs[cache_key]
                logger.info(f"清理未使用的知识库: {kb.name}")
                
            except Exception as e:
                logger.error(f"清理知识库失败: {cache_key} - {e}")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_kbs = len(self.loaded_kbs)
        initialized_kbs = len([kb for kb in self.loaded_kbs.values() if kb.is_initialized])
        loading_kbs = len([kb for kb in self.loaded_kbs.values() if kb.is_loading])
        
        return {
            "total_knowledge_bases": total_kbs,
            "initialized_knowledge_bases": initialized_kbs,
            "loading_knowledge_bases": loading_kbs,
            "cache_hit_rate": self._calculate_cache_hit_rate(),
            "memory_usage": len(self.loaded_kbs) * 1024,  # 简化的内存估算
        }
    
    def _calculate_cache_hit_rate(self) -> float:
        """计算缓存命中率"""
        # 简化实现，实际应该记录命中和未命中次数
        return 0.85  # 示例值
    
    @asynccontextmanager
    async def knowledge_base_context(self, kb_ids: List[str], user_id: str):
        """知识库上下文管理器"""
        loaded_kbs = []
        
        try:
            # 加载知识库
            for kb_id in kb_ids:
                kb = await self.load_knowledge_base(kb_id, user_id)
                if kb:
                    loaded_kbs.append(kb)
            
            yield loaded_kbs
            
        finally:
            # 这里可以做一些清理工作，但通常知识库会保持加载状态
            pass
    
    async def shutdown(self):
        """关闭管理器"""
        logger.info("正在关闭知识库管理器...")
        
        # 清理所有知识库
        for cache_key, kb in list(self.loaded_kbs.items()):
            try:
                await kb.cleanup()
            except Exception as e:
                logger.error(f"清理知识库失败: {kb.name} - {e}")
        
        self.loaded_kbs.clear()
        self.user_kb_cache.clear()
        self.last_cache_update.clear()
        self._locks.clear()
        
        logger.info("知识库管理器已关闭")


# 全局知识库管理器实例
knowledge_base_manager = KnowledgeBaseManager()