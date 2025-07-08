"""
图数据仓储 - 支持用户隔离和权限控制
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from .base import Neo4jRepository
from ..connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)


class GraphNode:
    """图节点模型"""
    
    def __init__(self, node_id: str, label: str, properties: Dict[str, Any] = None, 
                 user_id: str = None, kb_id: str = None, tenant_id: str = None):
        self.node_id = node_id
        self.label = label
        self.properties = properties or {}
        self.user_id = user_id
        self.kb_id = kb_id
        self.tenant_id = tenant_id
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'node_id': self.node_id,
            'label': self.label,
            'properties': self.properties,
            'user_id': self.user_id,
            'kb_id': self.kb_id,
            'tenant_id': self.tenant_id
        }


class GraphTriple:
    """图三元组模型"""
    
    def __init__(self, head: str, relation: str, tail: str, 
                 user_id: str = None, kb_id: str = None, tenant_id: str = None):
        self.head = head
        self.relation = relation
        self.tail = tail
        self.user_id = user_id
        self.kb_id = kb_id
        self.tenant_id = tenant_id
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'h': self.head,
            'r': self.relation,
            't': self.tail,
            'user_id': self.user_id,
            'kb_id': self.kb_id,
            'tenant_id': self.tenant_id
        }


class GraphRepository(Neo4jRepository[GraphNode]):
    """图数据仓储 - 纯数据访问层"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        super().__init__(connection_manager, 'neo4j')
    
    def _get_entity_label(self, kb_id: str = None) -> str:
        """获取实体标签，支持知识库隔离"""
        return f"Entity_KB_{kb_id}" if kb_id else "Entity"
    
    def _add_user_properties(self, properties: Dict[str, Any], user_id: str, 
                           kb_id: str = None, tenant_id: str = None) -> Dict[str, Any]:
        """为节点属性添加用户信息"""
        properties.update({
            'user_id': user_id,
            'kb_id': kb_id,
            'tenant_id': tenant_id or f"tenant_{user_id}",
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        })
        return properties
    
    def _build_user_filter(self, user_id: str, kb_id: str = None) -> Tuple[str, Dict[str, Any]]:
        """构建用户过滤条件"""
        params = {'current_user_id': user_id}
        conditions = ['n.user_id = $current_user_id']
        
        if kb_id:
            params['current_kb_id'] = kb_id
            conditions.append('n.kb_id = $current_kb_id')
        
        return ' AND '.join(conditions), params
    
    # 基础CRUD操作
    
    async def create(self, node: GraphNode) -> GraphNode:
        """创建节点"""
        # 实现创建逻辑
        return node
    
    async def get_by_id(self, node_id: str) -> Optional[GraphNode]:
        """根据ID获取节点"""
        # 实现获取逻辑
        return None
    
    async def update(self, node: GraphNode) -> GraphNode:
        """更新节点"""
        # 实现更新逻辑
        return node
    
    async def delete(self, node_id: str) -> bool:
        """删除节点"""
        # 实现删除逻辑
        return True
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[GraphNode]:
        """查找所有节点"""
        # 实现查找逻辑
        return []
    
    # 用户隔离的图操作方法
    
    async def create_user_entity(self, user_id: str, kb_id: str, entity_name: str, 
                               properties: Dict[str, Any] = None) -> GraphNode:
        """创建用户隔离的实体节点"""
        try:
            async with await self.get_session() as session:
                entity_label = self._get_entity_label(kb_id)
                node_props = self._add_user_properties(
                    properties or {'name': entity_name}, 
                    user_id, kb_id
                )
                
                query = f"""
                CREATE (n:{entity_label} $properties)
                RETURN n
                """
                
                result = await session.execute_cypher(query, {'properties': node_props})
                
                if result:
                    node_data = result[0]['n']
                    return GraphNode(
                        node_id=node_data.element_id,
                        label=entity_label,
                        properties=dict(node_data),
                        user_id=user_id,
                        kb_id=kb_id
                    )
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to create user entity: {e}")
            raise
    
    async def create_user_triples(self, user_id: str, kb_id: str, 
                                triples: List[GraphTriple]) -> bool:
        """创建用户隔离的三元组"""
        try:
            async with await self.get_session() as session:
                entity_label = self._get_entity_label(kb_id)
                
                # 批量创建三元组
                for triple in triples:
                    # 准备节点属性
                    h_props = self._add_user_properties({'name': triple.head}, user_id, kb_id)
                    t_props = self._add_user_properties({'name': triple.tail}, user_id, kb_id)
                    rel_props = self._add_user_properties({'type': triple.relation}, user_id, kb_id)
                    
                    query = f"""
                    MERGE (h:{entity_label} {{name: $head, user_id: $user_id, kb_id: $kb_id}})
                    SET h += $h_props
                    MERGE (t:{entity_label} {{name: $tail, user_id: $user_id, kb_id: $kb_id}})
                    SET t += $t_props
                    MERGE (h)-[r:{triple.relation.replace(" ", "_")} $rel_props]->(t)
                    """
                    
                    await session.execute_cypher(query, {
                        'head': triple.head,
                        'tail': triple.tail,
                        'user_id': user_id,
                        'kb_id': kb_id,
                        'h_props': h_props,
                        't_props': t_props,
                        'rel_props': rel_props
                    })
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to create user triples: {e}")
            raise
    
    async def query_user_entities(self, user_id: str, kb_id: str, entity_name: str,
                                hops: int = 2, limit: int = 100) -> List[Dict[str, Any]]:
        """查询用户隔离的实体关系"""
        try:
            async with await self.get_session() as session:
                entity_label = self._get_entity_label(kb_id)
                filter_clause, params = self._build_user_filter(user_id, kb_id)
                
                params.update({
                    'entity_name': entity_name,
                    'limit': limit
                })
                
                query = f"""
                MATCH (n:{entity_label} {{name: $entity_name}})-[r*1..{hops}]-(m:{entity_label})
                WHERE {filter_clause} AND m.user_id = $current_user_id
                AND ($current_kb_id IS NULL OR m.kb_id = $current_kb_id)
                RETURN n, r, m
                LIMIT $limit
                """
                
                results = await session.execute_cypher(query, params)
                return [dict(record) for record in results]
                
        except Exception as e:
            logger.error(f"Failed to query user entities: {e}")
            return []
    
    async def get_user_accessible_entities(self, user_id: str, kb_ids: List[str] = None) -> List[GraphNode]:
        """获取用户可访问的实体列表"""
        try:
            async with await self.get_session() as session:
                conditions = ['n.user_id = $user_id']
                params = {'user_id': user_id}
                
                if kb_ids:
                    conditions.append('n.kb_id IN $kb_ids')
                    params['kb_ids'] = kb_ids
                
                # 构建动态标签匹配
                if kb_ids:
                    label_patterns = [f"Entity_KB_{kb_id}" for kb_id in kb_ids]
                    label_query = " OR ".join([f"n:{label}" for label in label_patterns])
                    match_clause = f"MATCH (n) WHERE ({label_query})"
                else:
                    match_clause = "MATCH (n:Entity)"
                
                query = f"""
                {match_clause}
                WHERE {' AND '.join(conditions)}
                RETURN n
                LIMIT 1000
                """
                
                results = await session.execute_cypher(query, params)
                
                entities = []
                for record in results:
                    node = record['n']
                    entities.append(GraphNode(
                        node_id=node.element_id,
                        label=list(node.labels)[0] if node.labels else 'Entity',
                        properties=dict(node),
                        user_id=node.get('user_id'),
                        kb_id=node.get('kb_id'),
                        tenant_id=node.get('tenant_id')
                    ))
                
                return entities
                
        except Exception as e:
            logger.error(f"Failed to get user accessible entities: {e}")
            return []
    
    async def create_vector_index_for_kb(self, user_id: str, kb_id: str, dimension: int = 1024) -> bool:
        """为知识库创建向量索引"""
        try:
            async with await self.get_session() as session:
                entity_label = self._get_entity_label(kb_id)
                index_name = f"entityEmbeddings_{kb_id}"
                
                # 检查索引是否存在
                check_query = "SHOW INDEXES YIELD name WHERE name = $index_name"
                existing = await session.execute_cypher(check_query, {'index_name': index_name})
                
                if not existing:
                    create_query = f"""
                    CREATE VECTOR INDEX {index_name}
                    FOR (n:{entity_label}) ON (n.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {dimension},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                    """
                    
                    await session.execute_cypher(create_query)
                    logger.info(f"Created vector index for KB {kb_id}")
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to create vector index for KB {kb_id}: {e}")
            return False
    
    async def delete_kb_data(self, user_id: str, kb_id: str) -> bool:
        """删除知识库的所有图数据"""
        try:
            async with await self.get_session() as session:
                entity_label = self._get_entity_label(kb_id)
                filter_clause, params = self._build_user_filter(user_id, kb_id)
                
                query = f"""
                MATCH (n:{entity_label})
                WHERE {filter_clause}
                DETACH DELETE n
                """
                
                await session.execute_cypher(query, params)
                logger.info(f"Deleted all graph data for KB {kb_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete KB data: {e}")
            return False
    
    async def get_kb_statistics(self, user_id: str, kb_id: str) -> Dict[str, Any]:
        """获取知识库图数据统计"""
        try:
            async with await self.get_session() as session:
                entity_label = self._get_entity_label(kb_id)
                filter_clause, params = self._build_user_filter(user_id, kb_id)
                
                stats_query = f"""
                MATCH (n:{entity_label})
                WHERE {filter_clause}
                OPTIONAL MATCH (n)-[r]->()
                RETURN count(DISTINCT n) as node_count, count(r) as relationship_count
                """
                
                result = await session.execute_cypher(stats_query, params)
                
                if result:
                    stats = result[0]
                    return {
                        'kb_id': kb_id,
                        'entity_label': entity_label,
                        'node_count': stats['node_count'],
                        'relationship_count': stats['relationship_count'],
                        'user_id': user_id,
                        'last_updated': datetime.now().isoformat()
                    }
                
                return {
                    'kb_id': kb_id,
                    'node_count': 0,
                    'relationship_count': 0,
                    'user_id': user_id
                }
                
        except Exception as e:
            logger.error(f"Failed to get KB statistics: {e}")
            return {'error': str(e)}