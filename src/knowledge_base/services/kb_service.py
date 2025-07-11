"""
知识库服务

基于现有的 UnifiedLightRAGKnowledgeBase 实现智能体系统所需的知识库服务接口
将核心功能适配为智能体可使用的标准接口
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from src.core.unified_lightrag_kb import UnifiedLightRAGKnowledgeBase, get_unified_lightrag_kb
from src.knowledge_base.models.kb_models import KnowledgeDatabase
from src.auth.services.permission_service import PermissionService

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """
    知识库服务
    
    基于现有的 UnifiedLightRAGKnowledgeBase 核心实现，
    提供智能体系统所需的标准化知识库接口
    """
    
    def __init__(self):
        # 使用现有的统一知识库实例
        self.unified_kb: UnifiedLightRAGKnowledgeBase = get_unified_lightrag_kb()
        # TODO: 正确初始化权限服务，暂时设为None
        self.permission_service = None  # PermissionService()
        self._cache = {}
        self._lock = asyncio.Lock()
        
        logger.info("KnowledgeBaseService 初始化完成，基于 UnifiedLightRAGKnowledgeBase")
    
    async def get_knowledge_base(self, kb_id: str) -> Optional['KnowledgeBaseAdapter']:
        """
        获取知识库实例
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            KnowledgeBaseAdapter: 知识库适配器实例
        """
        try:
            # 检查知识库是否存在
            if not await self.knowledge_base_exists(kb_id):
                logger.warning(f"知识库不存在: {kb_id}")
                return None
            
            # 获取知识库元数据
            kb_meta = self.unified_kb.databases_meta.get(kb_id)
            if not kb_meta:
                logger.warning(f"知识库元数据不存在: {kb_id}")
                return None
            
            # 创建知识库适配器
            adapter = KnowledgeBaseAdapter(
                kb_id=kb_id,
                unified_kb=self.unified_kb,
                metadata=kb_meta
            )
            
            await adapter.initialize()
            return adapter
            
        except Exception as e:
            logger.error(f"获取知识库失败 [{kb_id}]: {e}")
            return None
    
    async def knowledge_base_exists(self, kb_id: str) -> bool:
        """检查知识库是否存在"""
        try:
            return kb_id in self.unified_kb.databases_meta
        except Exception as e:
            logger.error(f"检查知识库存在性失败 [{kb_id}]: {e}")
            return False
    
    async def list_knowledge_bases(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出知识库
        
        Args:
            user_id: 用户ID，用于权限过滤
            
        Returns:
            List[Dict]: 知识库列表
        """
        try:
            # 获取所有知识库
            databases_info = self.unified_kb.get_databases()
            kb_list = databases_info.get("databases", [])
            
            # 如果指定了用户ID，进行权限过滤
            if user_id:
                filtered_list = []
                for kb in kb_list:
                    kb_id = kb.get("db_id")
                    if kb_id and await self._check_user_access(user_id, kb_id):
                        filtered_list.append(kb)
                return filtered_list
            
            return kb_list
            
        except Exception as e:
            logger.error(f"列出知识库失败: {e}")
            return []
    
    async def create_knowledge_base(
        self, 
        name: str, 
        description: str, 
        user_id: str,
        embed_info: Optional[Dict] = None,
        **kwargs
    ) -> Optional[str]:
        """
        创建知识库
        
        Args:
            name: 知识库名称
            description: 描述
            user_id: 创建者用户ID
            embed_info: 嵌入模型信息
            **kwargs: 其他参数
            
        Returns:
            str: 知识库ID
        """
        try:
            # 添加创建者信息
            kwargs['created_by'] = user_id
            kwargs['created_at'] = datetime.now().isoformat()
            
            # 使用统一知识库创建
            result = self.unified_kb.create_database(
                database_name=name,
                description=description,
                embed_info=embed_info,
                **kwargs
            )
            
            # 提取知识库ID（假设返回格式包含db_id）
            if isinstance(result, dict):
                kb_id = result.get('db_id')
            else:
                # 如果返回的是字符串形式的ID
                kb_id = result
            
            logger.info(f"知识库创建成功: {name} -> {kb_id}")
            return kb_id
            
        except Exception as e:
            logger.error(f"创建知识库失败 [{name}]: {e}")
            return None
    
    async def delete_knowledge_base(self, kb_id: str, user_id: str) -> bool:
        """
        删除知识库
        
        Args:
            kb_id: 知识库ID
            user_id: 操作用户ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            # 检查权限
            if not await self._check_user_access(user_id, kb_id, action="delete"):
                logger.warning(f"用户无权限删除知识库: {user_id} -> {kb_id}")
                return False
            
            # 删除知识库（需要在 UnifiedLightRAGKnowledgeBase 中实现）
            success = await self._delete_kb_from_unified(kb_id)
            
            if success:
                logger.info(f"知识库删除成功: {kb_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"删除知识库失败 [{kb_id}]: {e}")
            return False
    
    async def get_knowledge_base_stats(self, kb_id: str) -> Dict[str, Any]:
        """
        获取知识库统计信息
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            Dict: 统计信息
        """
        try:
            if kb_id not in self.unified_kb.databases_meta:
                return {}
            
            # 获取文件统计
            file_count = 0
            for file_info in self.unified_kb.files_meta.values():
                if file_info.get("database_id") == kb_id:
                    file_count += 1
            
            # 获取知识库元数据
            kb_meta = self.unified_kb.databases_meta[kb_id]
            
            return {
                "kb_id": kb_id,
                "name": kb_meta.get("name", ""),
                "description": kb_meta.get("description", ""),
                "file_count": file_count,
                "created_at": kb_meta.get("created_at"),
                "embed_info": kb_meta.get("embed_info", {}),
                "status": "active" if kb_id in self.unified_kb.instances else "inactive"
            }
            
        except Exception as e:
            logger.error(f"获取知识库统计失败 [{kb_id}]: {e}")
            return {}
    
    async def _check_user_access(self, user_id: str, kb_id: str, action: str = "read") -> bool:
        """检查用户访问权限"""
        try:
            # 这里应该集成实际的权限检查逻辑
            # 暂时返回 True，实际应该调用 permission_service
            return True
            
        except Exception as e:
            logger.error(f"权限检查失败: {e}")
            return False
    
    async def _delete_kb_from_unified(self, kb_id: str) -> bool:
        """从统一知识库中删除"""
        try:
            # 停止实例
            if kb_id in self.unified_kb.instances:
                del self.unified_kb.instances[kb_id]
            
            # 删除元数据
            if kb_id in self.unified_kb.databases_meta:
                del self.unified_kb.databases_meta[kb_id]
            
            # 删除相关文件元数据
            files_to_remove = []
            for file_id, file_info in self.unified_kb.files_meta.items():
                if file_info.get("database_id") == kb_id:
                    files_to_remove.append(file_id)
            
            for file_id in files_to_remove:
                del self.unified_kb.files_meta[file_id]
            
            # 保存元数据
            self.unified_kb._save_metadata()
            
            return True
            
        except Exception as e:
            logger.error(f"从统一知识库删除失败 [{kb_id}]: {e}")
            return False


class KnowledgeBaseAdapter:
    """
    知识库适配器
    
    将 UnifiedLightRAGKnowledgeBase 的功能包装为智能体可用的接口
    """
    
    def __init__(self, kb_id: str, unified_kb: UnifiedLightRAGKnowledgeBase, metadata: Dict[str, Any]):
        self.kb_id = kb_id
        self.unified_kb = unified_kb
        self.metadata = metadata
        self.lightrag_instance = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """初始化知识库适配器"""
        try:
            # 获取 LightRAG 实例
            self.lightrag_instance = await self.unified_kb._get_lightrag_instance(self.kb_id)
            
            if self.lightrag_instance:
                self._initialized = True
                logger.info(f"知识库适配器初始化成功: {self.kb_id}")
                return True
            else:
                logger.warning(f"无法获取 LightRAG 实例: {self.kb_id}")
                return False
                
        except Exception as e:
            logger.error(f"知识库适配器初始化失败 [{self.kb_id}]: {e}")
            return False
    
    async def query(self, query: str, mode: str = "hybrid", **kwargs) -> Dict[str, Any]:
        """
        查询知识库
        
        Args:
            query: 查询文本
            mode: 查询模式 (naive, local, global, hybrid)
            **kwargs: 其他查询参数
            
        Returns:
            Dict: 查询结果
        """
        try:
            if not self._initialized or not self.lightrag_instance:
                await self.initialize()
            
            if not self.lightrag_instance:
                return {"error": "知识库未初始化"}
            
            # 调用 LightRAG 查询
            result = await self.lightrag_instance.aquery(query, param={"mode": mode})
            
            return {
                "success": True,
                "result": result,
                "query": query,
                "mode": mode,
                "kb_id": self.kb_id
            }
            
        except Exception as e:
            logger.error(f"知识库查询失败 [{self.kb_id}]: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "kb_id": self.kb_id
            }
    
    async def add_document(self, content: str, metadata: Optional[Dict] = None) -> bool:
        """
        添加文档到知识库
        
        Args:
            content: 文档内容
            metadata: 文档元数据
            
        Returns:
            bool: 是否添加成功
        """
        try:
            if not self._initialized or not self.lightrag_instance:
                await self.initialize()
            
            if not self.lightrag_instance:
                return False
            
            # 调用 LightRAG 插入
            await self.lightrag_instance.ainsert(content)
            
            logger.info(f"文档添加成功 [{self.kb_id}]: {len(content)} 字符")
            return True
            
        except Exception as e:
            logger.error(f"文档添加失败 [{self.kb_id}]: {e}")
            return False
    
    def get_metadata(self) -> Dict[str, Any]:
        """获取知识库元数据"""
        return self.metadata.copy()
    
    def get_name(self) -> str:
        """获取知识库名称"""
        return self.metadata.get("name", self.kb_id)
    
    def get_description(self) -> str:
        """获取知识库描述"""
        return self.metadata.get("description", "")
    
    def is_ready(self) -> bool:
        """检查知识库是否就绪"""
        return self._initialized and self.lightrag_instance is not None