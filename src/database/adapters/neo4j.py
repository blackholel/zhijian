"""
Neo4j图数据库适配器
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

try:
    from neo4j import GraphDatabase as GD
    from neo4j import Query, exceptions as neo4j_exceptions
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

from ..base import NoSQLDatabaseAdapter, ConnectionStatus, ConnectionError

logger = logging.getLogger(__name__)


class Neo4jAdapter(NoSQLDatabaseAdapter):
    """Neo4j图数据库适配器"""
    
    def __init__(self, config: Dict[str, Any], db_name: str = None):
        """
        初始化Neo4j适配器
        
        Args:
            config: 数据库配置
            db_name: 数据库名称
        """
        if not NEO4J_AVAILABLE:
            raise ConnectionError("Neo4j driver not available. Please install: pip install neo4j")
        
        super().__init__(config, db_name)
        
        self.driver = None
        self.database_name = config.get('database', 'neo4j')
        
        # 连接配置
        self.uri = config.get('uri', 'bolt://localhost:7687')
        self.username = config.get('username', 'neo4j')
        self.password = config.get('password', 'password')
        self.encrypted = config.get('encrypted', False)
        self.trust = config.get('trust', 'TRUST_ALL_CERTIFICATES')
        self.connection_timeout = config.get('connection_timeout', 30)
        self.max_connection_lifetime = config.get('max_connection_lifetime', 3600)
        self.max_connection_pool_size = config.get('max_connection_pool_size', 100)
        self.connection_acquisition_timeout = config.get('connection_acquisition_timeout', 60)
        
        logger.debug(f"Neo4j adapter initialized for {self.db_name}")
    
    def _create_driver_config(self) -> Dict[str, Any]:
        """创建驱动器配置"""
        driver_config = {}
        
        # 加密配置
        if 'encrypted' in self.config:
            driver_config['encrypted'] = self.encrypted
        
        # 信任配置
        if self.trust:
            try:
                from neo4j import TrustStrategy
                if self.trust == 'TRUST_ALL_CERTIFICATES':
                    driver_config['trust'] = TrustStrategy.trust_all_certificates()
                elif self.trust == 'TRUST_SYSTEM_CA_SIGNED_CERTIFICATES':
                    driver_config['trust'] = TrustStrategy.trust_system_ca_signed_certificates()
            except ImportError:
                logger.warning("TrustStrategy not available, skipping trust configuration")
        
        # 超时配置
        driver_config.update({
            'connection_timeout': self.connection_timeout,
            'max_connection_lifetime': self.max_connection_lifetime,
            'max_connection_pool_size': self.max_connection_pool_size,
            'connection_acquisition_timeout': self.connection_acquisition_timeout
        })
        
        return driver_config
    
    async def connect(self) -> bool:
        """建立数据库连接"""
        if self.status == ConnectionStatus.CONNECTED:
            return True
        
        self.status = ConnectionStatus.CONNECTING
        
        try:
            # 创建驱动器配置
            driver_config = self._create_driver_config()
            
            # 创建驱动器
            def _create_driver():
                return GD.driver(
                    self.uri,
                    auth=(self.username, self.password),
                    **driver_config
                )
            
            self.driver = await asyncio.get_event_loop().run_in_executor(None, _create_driver)
            
            # 测试连接
            await self._test_connection()
            
            self._client = self.driver
            self.status = ConnectionStatus.CONNECTED
            
            logger.info(f"Neo4j connection established for {self.db_name} at {self.uri}")
            return True
            
        except Exception as e:
            self.status = ConnectionStatus.ERROR
            logger.error(f"Failed to connect to Neo4j {self.db_name}: {e}")
            return False
    
    async def _test_connection(self):
        """测试数据库连接"""
        def _sync_test():
            with self.driver.session(database=self.database_name) as session:
                session.run("RETURN 1")
        
        await asyncio.get_event_loop().run_in_executor(None, _sync_test)
    
    async def disconnect(self) -> bool:
        """断开数据库连接"""
        try:
            if self.driver:
                def _close_driver():
                    self.driver.close()
                
                await asyncio.get_event_loop().run_in_executor(None, _close_driver)
                self.driver = None
                self._client = None
            
            self.status = ConnectionStatus.DISCONNECTED
            logger.info(f"Neo4j connection closed for {self.db_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Neo4j {self.db_name}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.is_connected:
                return {
                    'status': 'disconnected',
                    'database_name': self.db_name,
                    'timestamp': datetime.now().isoformat()
                }
            
            def _sync_health_check():
                with self.driver.session(database=self.database_name) as session:
                    # 基本连接测试
                    session.run("RETURN 1")
                    
                    # 获取数据库组件信息
                    try:
                        result = session.run("CALL dbms.components() YIELD name, versions")
                        components = list(result)
                    except Exception:
                        components = []
                    
                    # 获取节点和关系统计
                    try:
                        stats_result = session.run("""
                            MATCH (n) 
                            OPTIONAL MATCH ()-[r]->() 
                            RETURN count(DISTINCT n) as node_count, count(r) as relationship_count
                        """)
                        stats = stats_result.single()
                        node_count = stats['node_count'] if stats else 0
                        relationship_count = stats['relationship_count'] if stats else 0
                    except Exception:
                        node_count = 0
                        relationship_count = 0
                    
                    return {
                        'status': 'healthy',
                        'database_name': self.db_name,
                        'uri': self.uri,
                        'database': self.database_name,
                        'components': components,
                        'node_count': node_count,
                        'relationship_count': relationship_count,
                        'timestamp': datetime.now().isoformat()
                    }
            
            result = await asyncio.get_event_loop().run_in_executor(None, _sync_health_check)
            return result
            
        except Exception as e:
            return {
                'status': 'error',
                'database_name': self.db_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            'database_name': self.db_name,
            'type': 'neo4j',
            'uri': self.uri,
            'username': self.username,
            'database': self.database_name,
            'encrypted': self.encrypted,
            'status': self.status.value,
            'pool_size': self.max_connection_pool_size
        }
    
    @asynccontextmanager
    async def get_session(self):
        """获取数据库会话的异步上下文管理器"""
        await self.ensure_connected()
        
        def _get_session():
            return self.driver.session(database=self.database_name)
        
        session = await asyncio.get_event_loop().run_in_executor(None, _get_session)
        try:
            yield session
        except Exception as e:
            logger.error(f"Neo4j session error for {self.db_name}: {e}")
            raise
        finally:
            def _close_session():
                session.close()
            await asyncio.get_event_loop().run_in_executor(None, _close_session)
    
    async def execute_cypher(self, query: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        执行Cypher查询
        
        Args:
            query: Cypher查询语句
            parameters: 查询参数
            
        Returns:
            查询结果列表
        """
        await self.ensure_connected()
        
        def _sync_execute():
            with self.driver.session(database=self.database_name) as session:
                result = session.run(query, parameters or {})
                return [record.data() for record in result]
        
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_execute)
        except Exception as e:
            logger.error(f"Cypher query execution failed for {self.db_name}: {e}")
            raise
    
    async def execute_transaction(self, operations: List[Dict[str, Any]]) -> bool:
        """
        执行事务
        
        Args:
            operations: 操作列表，每个操作包含 'query' 和 'parameters'
            
        Returns:
            bool: 事务执行成功返回True
        """
        await self.ensure_connected()
        
        def _sync_transaction():
            with self.driver.session(database=self.database_name) as session:
                def tx_function(tx):
                    for operation in operations:
                        query = operation.get('query')
                        parameters = operation.get('parameters', {})
                        tx.run(query, parameters)
                
                session.execute_write(tx_function)
            return True
        
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _sync_transaction)
        except Exception as e:
            logger.error(f"Neo4j transaction failed for {self.db_name}: {e}")
            return False
    
    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文档（节点）
        
        Args:
            collection: 节点标签
            doc_id: 文档ID
            
        Returns:
            文档数据或None
        """
        try:
            query = f"MATCH (n:{collection} {{id: $doc_id}}) RETURN n"
            results = await self.execute_cypher(query, {'doc_id': doc_id})
            
            if results:
                return dict(results[0]['n'])
            return None
            
        except Exception as e:
            logger.error(f"Failed to get document {doc_id} from {collection}: {e}")
            return None
    
    async def save_document(self, collection: str, doc_id: str, document: Dict[str, Any]) -> bool:
        """
        保存文档（节点）
        
        Args:
            collection: 节点标签
            doc_id: 文档ID
            document: 文档数据
            
        Returns:
            保存成功返回True
        """
        try:
            # 构建属性字符串
            properties = {**document, 'id': doc_id}
            
            query = f"""
                MERGE (n:{collection} {{id: $doc_id}})
                SET n = $properties
                RETURN n
            """
            
            await self.execute_cypher(query, {'doc_id': doc_id, 'properties': properties})
            return True
            
        except Exception as e:
            logger.error(f"Failed to save document {doc_id} to {collection}: {e}")
            return False
    
    async def create_relationship(self, from_node: Dict[str, Any], to_node: Dict[str, Any], 
                                relationship_type: str, properties: Dict[str, Any] = None) -> bool:
        """
        创建关系
        
        Args:
            from_node: 源节点信息 {'label': 'Label', 'id': 'id'}
            to_node: 目标节点信息 {'label': 'Label', 'id': 'id'}
            relationship_type: 关系类型
            properties: 关系属性
            
        Returns:
            创建成功返回True
        """
        try:
            query = f"""
                MATCH (a:{from_node['label']} {{id: $from_id}})
                MATCH (b:{to_node['label']} {{id: $to_id}})
                MERGE (a)-[r:{relationship_type}]->(b)
                SET r = $properties
                RETURN r
            """
            
            parameters = {
                'from_id': from_node['id'],
                'to_id': to_node['id'],
                'properties': properties or {}
            }
            
            await self.execute_cypher(query, parameters)
            return True
            
        except Exception as e:
            logger.error(f"Failed to create relationship {relationship_type}: {e}")
            return False
    
    async def get_neighbors(self, node_label: str, node_id: str, 
                           relationship_types: List[str] = None, direction: str = 'both',
                           max_depth: int = 1) -> List[Dict[str, Any]]:
        """
        获取节点邻居
        
        Args:
            node_label: 节点标签
            node_id: 节点ID
            relationship_types: 关系类型列表，None表示所有类型
            direction: 关系方向 ('incoming', 'outgoing', 'both')
            max_depth: 最大深度
            
        Returns:
            邻居节点列表
        """
        try:
            # 构建关系模式
            if relationship_types:
                rel_pattern = '|'.join(relationship_types)
                rel_part = f"[r:{rel_pattern}*1..{max_depth}]"
            else:
                rel_part = f"[r*1..{max_depth}]"
            
            # 构建方向模式
            if direction == 'incoming':
                pattern = f"(m)<-{rel_part}-(n:{node_label})"
            elif direction == 'outgoing':
                pattern = f"(n:{node_label})-{rel_part}->(m)"
            else:  # both
                pattern = f"(n:{node_label})-{rel_part}-(m)"
            
            query = f"""
                MATCH {pattern}
                WHERE n.id = $node_id
                RETURN DISTINCT m, r
            """
            
            results = await self.execute_cypher(query, {'node_id': node_id})
            
            neighbors = []
            for result in results:
                neighbor_data = dict(result['m'])
                relationship_data = [dict(rel) for rel in result['r']] if result['r'] else []
                neighbors.append({
                    'node': neighbor_data,
                    'relationships': relationship_data
                })
            
            return neighbors
            
        except Exception as e:
            logger.error(f"Failed to get neighbors for {node_id}: {e}")
            return []
    
    async def delete_node(self, node_label: str, node_id: str) -> bool:
        """删除节点及其关系"""
        try:
            query = f"MATCH (n:{node_label} {{id: $node_id}}) DETACH DELETE n"
            await self.execute_cypher(query, {'node_id': node_id})
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {e}")
            return False
    
    async def clear_database(self) -> bool:
        """清空数据库"""
        try:
            query = "MATCH (n) DETACH DELETE n"
            await self.execute_cypher(query)
            logger.info(f"Database {self.db_name} cleared")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear database {self.db_name}: {e}")
            return False
    
    async def create_index(self, label: str, property_name: str) -> bool:
        """创建索引"""
        try:
            query = f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{property_name})"
            await self.execute_cypher(query)
            logger.info(f"Index created for {label}.{property_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index for {label}.{property_name}: {e}")
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            def _get_stats():
                with self.driver.session(database=self.database_name) as session:
                    # 节点统计
                    node_result = session.run("MATCH (n) RETURN count(n) as node_count")
                    node_count = node_result.single()['node_count']
                    
                    # 关系统计
                    rel_result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
                    rel_count = rel_result.single()['rel_count']
                    
                    # 标签统计
                    try:
                        labels_result = session.run("CALL db.labels() YIELD label RETURN collect(label) as labels")
                        labels = labels_result.single()['labels']
                    except Exception:
                        labels = []
                    
                    # 关系类型统计
                    try:
                        types_result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) as types")
                        rel_types = types_result.single()['types']
                    except Exception:
                        rel_types = []
                    
                    return {
                        'node_count': node_count,
                        'relationship_count': rel_count,
                        'labels': labels,
                        'relationship_types': rel_types
                    }
            
            return await asyncio.get_event_loop().run_in_executor(None, _get_stats)
            
        except Exception as e:
            logger.error(f"Failed to get statistics for {self.db_name}: {e}")
            return {
                'node_count': 0,
                'relationship_count': 0,
                'labels': [],
                'relationship_types': []
            }