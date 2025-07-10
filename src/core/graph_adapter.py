"""
GraphDatabase适配器 - 集成统一数据库管理器和权限控制
保持向后兼容的同时提供用户隔离和权限管理
"""

import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from src.database.manager import get_database_manager
from src.database.repositories.graph_repository import GraphRepository, GraphTriple, GraphNode
from src.database.repositories.permission_mixin import PermissionValidator
from src.auth.permission_framework import Permission

logger = logging.getLogger(__name__)


class UnifiedGraphAdapter:
    """
    统一图数据库适配器
    提供与GraphDatabase兼容的接口，但使用统一数据库管理器
    """
    
    def __init__(self):
        self.db_manager = get_database_manager()
        self.permission_validator = PermissionValidator()
        self._initialized = False
        
        # 用户上下文
        self.current_user_id = None
        self.current_kb_id = None
        self.current_tenant_id = None
    
    async def initialize(self):
        """初始化适配器"""
        if not self._initialized:
            await self.db_manager.initialize()
            self._initialized = True
            logger.info("UnifiedGraphAdapter initialized")
    
    def set_user_context(self, user_id: str, kb_id: str = None, tenant_id: str = None):
        """设置用户上下文"""
        self.current_user_id = user_id
        self.current_kb_id = kb_id
        self.current_tenant_id = tenant_id or f"tenant_{user_id}"
        logger.debug(f"Set user context: user_id={user_id}, kb_id={kb_id}")
    
    @asynccontextmanager
    async def get_graph_repository(self):
        """获取图数据仓储"""
        await self.initialize()
        graph_repo = self.db_manager.get_graph_repository()
        
        # 设置权限引擎
        from src.auth.permission_framework import PermissionEngine
        permission_engine = PermissionEngine.get_instance()
        graph_repo.set_permission_engine(permission_engine)
        
        try:
            yield graph_repo
        finally:
            pass
    
    async def check_kb_permission(self, user_id: str, kb_id: str, permission: Permission) -> bool:
        """检查知识库权限"""
        return await self.permission_validator.validate_kb_access(user_id, kb_id, permission)
    
    # 向后兼容的GraphDatabase接口
    
    async def txt_add_entity_with_user(self, user_id: str, kb_id: str, triples: List[Dict[str, str]]) -> bool:
        """添加实体三元组（用户隔离版本）"""
        try:
            # 权限检查
            if not await self.check_kb_permission(user_id, kb_id, Permission.WRITE):
                raise PermissionError(f"用户 {user_id} 没有写入知识库 {kb_id} 的权限")
            
            # 转换为GraphTriple对象
            graph_triples = []
            for triple in triples:
                graph_triples.append(GraphTriple(
                    head=triple['h'],
                    relation=triple['r'],
                    tail=triple['t'],
                    user_id=user_id,
                    kb_id=kb_id
                ))
            
            async with self.get_graph_repository() as graph_repo:
                return await graph_repo.create_user_triples(user_id, kb_id, graph_triples)
                
        except Exception as e:
            logger.error(f"Failed to add entities with user context: {e}")
            return False
    
    async def query_user_entities(self, user_id: str, kb_id: str, entity_name: str, 
                                hops: int = 2, limit: int = 100) -> List[Dict[str, Any]]:
        """查询用户实体（权限控制版本）"""
        try:
            # 权限检查
            if not await self.check_kb_permission(user_id, kb_id, Permission.READ):
                raise PermissionError(f"用户 {user_id} 没有读取知识库 {kb_id} 的权限")
            
            async with self.get_graph_repository() as graph_repo:
                return await graph_repo.query_user_entities(user_id, kb_id, entity_name, hops, limit)
                
        except Exception as e:
            logger.error(f"Failed to query user entities: {e}")
            return []
    
    async def get_user_accessible_entities(self, user_id: str, kb_ids: List[str] = None) -> List[GraphNode]:
        """获取用户可访问的实体"""
        try:
            # 如果提供了kb_ids，检查每个知识库的权限
            if kb_ids:
                accessible_kb_ids = []
                for kb_id in kb_ids:
                    if await self.check_kb_permission(user_id, kb_id, Permission.READ):
                        accessible_kb_ids.append(kb_id)
                kb_ids = accessible_kb_ids
                
                if not kb_ids:
                    logger.warning(f"用户 {user_id} 没有访问任何指定知识库的权限")
                    return []
            
            async with self.get_graph_repository() as graph_repo:
                return await graph_repo.get_user_accessible_entities(user_id, kb_ids)
                
        except Exception as e:
            logger.error(f"Failed to get user accessible entities: {e}")
            return []
    
    async def create_vector_index_for_kb(self, user_id: str, kb_id: str, dimension: int = 1024) -> bool:
        """为知识库创建向量索引"""
        try:
            # 权限检查
            if not await self.check_kb_permission(user_id, kb_id, Permission.WRITE):
                raise PermissionError(f"用户 {user_id} 没有管理知识库 {kb_id} 的权限")
            
            async with self.get_graph_repository() as graph_repo:
                return await graph_repo.create_vector_index_for_kb(user_id, kb_id, dimension)
                
        except Exception as e:
            logger.error(f"Failed to create vector index: {e}")
            return False
    
    async def delete_kb_data(self, user_id: str, kb_id: str) -> bool:
        """删除知识库数据"""
        try:
            # 权限检查
            if not await self.check_kb_permission(user_id, kb_id, Permission.DELETE):
                raise PermissionError(f"用户 {user_id} 没有删除知识库 {kb_id} 的权限")
            
            async with self.get_graph_repository() as graph_repo:
                return await graph_repo.delete_kb_data(user_id, kb_id)
                
        except Exception as e:
            logger.error(f"Failed to delete KB data: {e}")
            return False
    
    async def get_kb_statistics(self, user_id: str, kb_id: str) -> Dict[str, Any]:
        """获取知识库统计信息"""
        try:
            # 权限检查
            if not await self.check_kb_permission(user_id, kb_id, Permission.READ):
                return {'error': f"用户 {user_id} 没有读取知识库 {kb_id} 的权限"}
            
            async with self.get_graph_repository() as graph_repo:
                return await graph_repo.get_kb_statistics(user_id, kb_id)
                
        except Exception as e:
            logger.error(f"Failed to get KB statistics: {e}")
            return {'error': str(e)}
    
    # 兼容原GraphDatabase的方法（自动使用当前用户上下文）
    
    async def txt_add_entity_compat(self, triples: List[Dict[str, str]], kgdb_name: str = 'neo4j') -> bool:
        """兼容原GraphDatabase.txt_add_entity方法"""
        if not self.current_user_id or not self.current_kb_id:
            logger.error("未设置用户上下文，无法执行操作")
            return False
        
        return await self.txt_add_entity_with_user(self.current_user_id, self.current_kb_id, triples)
    
    async def query_node_compat(self, entity_name: str, kgdb_name: str = 'neo4j', 
                              hops: int = 2, limit: int = 100) -> List[Dict[str, Any]]:
        """兼容原GraphDatabase.query_node方法"""
        if not self.current_user_id or not self.current_kb_id:
            logger.error("未设置用户上下文，无法执行查询")
            return []
        
        return await self.query_user_entities(self.current_user_id, self.current_kb_id, 
                                            entity_name, hops, limit)
    
    # 健康检查和状态方法
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            await self.initialize()
            db_health = await self.db_manager.health_check()
            
            return {
                'status': 'healthy' if db_health.get('status') == 'healthy' else 'degraded',
                'unified_manager': db_health.get('status', 'unknown'),
                'user_context': {
                    'user_id': self.current_user_id,
                    'kb_id': self.current_kb_id,
                    'tenant_id': self.current_tenant_id
                },
                'initialized': self._initialized
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'initialized': self._initialized
            }


# 全局实例
_unified_graph_adapter: Optional[UnifiedGraphAdapter] = None


def get_unified_graph_adapter() -> UnifiedGraphAdapter:
    """获取统一图数据库适配器单例"""
    global _unified_graph_adapter
    if _unified_graph_adapter is None:
        _unified_graph_adapter = UnifiedGraphAdapter()
    return _unified_graph_adapter


async def initialize_unified_graph_adapter():
    """初始化统一图数据库适配器"""
    adapter = get_unified_graph_adapter()
    await adapter.initialize()
    return adapter


# 为现有代码提供兼容性接口
class GraphDatabaseProxy:
    """
    GraphDatabase代理类
    提供与原GraphDatabase相同的接口，但内部使用UnifiedGraphAdapter
    """
    
    def __init__(self):
        self.adapter = get_unified_graph_adapter()
        self.status = "closed"
    
    async def start(self):
        """启动连接"""
        await self.adapter.initialize()
        self.status = "open"
    
    def set_user_context(self, user_id: str, kb_id: str = None):
        """设置用户上下文"""
        self.adapter.set_user_context(user_id, kb_id)
    
    async def txt_add_entity(self, triples: List[Dict[str, str]], kgdb_name: str = 'neo4j'):
        """添加实体三元组（需要先设置用户上下文）"""
        return await self.adapter.txt_add_entity_compat(triples, kgdb_name)
    
    async def query_specific_entity(self, entity_name: str, kgdb_name: str = 'neo4j', 
                                  hops: int = 2, limit: int = 100):
        """查询特定实体（需要先设置用户上下文）"""
        return await self.adapter.query_node_compat(entity_name, kgdb_name, hops, limit)
    
    async def health_check(self):
        """健康检查"""
        return await self.adapter.health_check()