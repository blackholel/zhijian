"""
智能体数据仓储
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import text, and_

from .base import PostgreSQLRepository
from ..connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)


class AgentInfo:
    """智能体信息模型"""
    
    def __init__(self, agent_id: str, name: str, agent_type: str, 
                 user_id: str, description: str = None, version: str = "1.0",
                 organization_id: str = None, config_data: Dict[str, Any] = None,
                 is_active: bool = True, is_deleted: bool = False,
                 created_at: datetime = None, updated_at: datetime = None):
        self.agent_id = agent_id
        self.name = name
        self.agent_type = agent_type
        self.user_id = user_id
        self.description = description
        self.version = version
        self.organization_id = organization_id
        self.config_data = config_data or {}
        self.is_active = is_active
        self.is_deleted = is_deleted
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'agent_id': self.agent_id,
            'name': self.name,
            'agent_type': self.agent_type,
            'user_id': self.user_id,
            'description': self.description,
            'version': self.version,
            'organization_id': self.organization_id,
            'config_data': self.config_data,
            'is_active': self.is_active,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AgentRepository(PostgreSQLRepository[AgentInfo]):
    """智能体仓储"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        super().__init__(connection_manager, 'server_db')
        self.table_name = 'agent_definitions'
    
    async def create(self, agent_info: AgentInfo) -> AgentInfo:
        """创建智能体"""
        try:
            async with self.connection_manager.get_session(self.db_name) as session:
                query = text(f"""
                    INSERT INTO {self.table_name} (
                        agent_id, name, agent_type, user_id, description, version,
                        organization_id, config_data, is_active, is_deleted,
                        created_at, updated_at
                    ) VALUES (
                        :agent_id, :name, :agent_type, :user_id, :description, :version,
                        :organization_id, :config_data, :is_active, :is_deleted,
                        :created_at, :updated_at
                    )
                    RETURNING *
                """)
                
                result = await session.execute(query, {
                    'agent_id': agent_info.agent_id,
                    'name': agent_info.name,
                    'agent_type': agent_info.agent_type,
                    'user_id': agent_info.user_id,
                    'description': agent_info.description,
                    'version': agent_info.version,
                    'organization_id': agent_info.organization_id,
                    'config_data': agent_info.config_data,
                    'is_active': agent_info.is_active,
                    'is_deleted': agent_info.is_deleted,
                    'created_at': agent_info.created_at,
                    'updated_at': agent_info.updated_at
                })
                
                row = result.fetchone()
                if row:
                    return self._row_to_agent_info(row)
                else:
                    raise Exception("创建智能体失败")
                    
        except Exception as e:
            logger.error(f"创建智能体失败: {e}")
            raise
    
    async def get_by_id(self, agent_id: str) -> Optional[AgentInfo]:
        """根据ID获取智能体"""
        try:
            async with self.connection_manager.get_session(self.db_name) as session:
                query = text(f"""
                    SELECT * FROM {self.table_name} 
                    WHERE agent_id = :agent_id AND is_deleted = false
                """)
                
                result = await session.execute(query, {'agent_id': agent_id})
                row = result.fetchone()
                
                if row:
                    return self._row_to_agent_info(row)
                return None
                
        except Exception as e:
            logger.error(f"获取智能体失败: {e}")
            return None
    
    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[AgentInfo]:
        """根据字段获取智能体"""
        try:
            async with self.connection_manager.get_session(self.db_name) as session:
                query = text(f"""
                    SELECT * FROM {self.table_name} 
                    WHERE {field_name} = :field_value AND is_deleted = false
                """)
                
                result = await session.execute(query, {'field_value': field_value})
                row = result.fetchone()
                
                if row:
                    return self._row_to_agent_info(row)
                return None
                
        except Exception as e:
            logger.error(f"根据字段获取智能体失败: {e}")
            return None
    
    async def update(self, agent_info: AgentInfo) -> AgentInfo:
        """更新智能体"""
        try:
            agent_info.updated_at = datetime.now()
            
            async with self.connection_manager.get_session(self.db_name) as session:
                query = text(f"""
                    UPDATE {self.table_name} SET
                        name = :name,
                        description = :description,
                        config_data = :config_data,
                        is_active = :is_active,
                        updated_at = :updated_at
                    WHERE agent_id = :agent_id AND is_deleted = false
                    RETURNING *
                """)
                
                result = await session.execute(query, {
                    'name': agent_info.name,
                    'description': agent_info.description,
                    'config_data': agent_info.config_data,
                    'is_active': agent_info.is_active,
                    'updated_at': agent_info.updated_at,
                    'agent_id': agent_info.agent_id
                })
                
                row = result.fetchone()
                if row:
                    return self._row_to_agent_info(row)
                else:
                    raise Exception("更新智能体失败")
                    
        except Exception as e:
            logger.error(f"更新智能体失败: {e}")
            raise
    
    async def delete(self, agent_id: str) -> bool:
        """软删除智能体"""
        try:
            async with self.connection_manager.get_session(self.db_name) as session:
                query = text(f"""
                    UPDATE {self.table_name} SET
                        is_deleted = true,
                        is_active = false,
                        updated_at = :updated_at
                    WHERE agent_id = :agent_id
                """)
                
                result = await session.execute(query, {
                    'agent_id': agent_id,
                    'updated_at': datetime.now()
                })
                
                return result.rowcount > 0
                
        except Exception as e:
            logger.error(f"删除智能体失败: {e}")
            return False
    
    async def list_by_user(self, user_id: str, include_inactive: bool = False) -> List[AgentInfo]:
        """获取用户的智能体列表"""
        try:
            async with self.connection_manager.get_session(self.db_name) as session:
                where_clause = "WHERE user_id = :user_id AND is_deleted = false"
                if not include_inactive:
                    where_clause += " AND is_active = true"
                
                query = text(f"""
                    SELECT * FROM {self.table_name} 
                    {where_clause}
                    ORDER BY created_at DESC
                """)
                
                result = await session.execute(query, {'user_id': user_id})
                rows = result.fetchall()
                
                return [self._row_to_agent_info(row) for row in rows]
                
        except Exception as e:
            logger.error(f"获取用户智能体列表失败: {e}")
            return []
    
    async def list_by_type(self, agent_type: str, user_id: str = None) -> List[AgentInfo]:
        """根据类型获取智能体列表"""
        try:
            async with self.connection_manager.get_session(self.db_name) as session:
                where_clause = "WHERE agent_type = :agent_type AND is_deleted = false AND is_active = true"
                params = {'agent_type': agent_type}
                
                if user_id:
                    where_clause += " AND user_id = :user_id"
                    params['user_id'] = user_id
                
                query = text(f"""
                    SELECT * FROM {self.table_name} 
                    {where_clause}
                    ORDER BY created_at DESC
                """)
                
                result = await session.execute(query, params)
                rows = result.fetchall()
                
                return [self._row_to_agent_info(row) for row in rows]
                
        except Exception as e:
            logger.error(f"根据类型获取智能体列表失败: {e}")
            return []
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[AgentInfo]:
        """查找所有智能体"""
        try:
            async with self.connection_manager.get_session(self.db_name) as session:
                query = text(f"""
                    SELECT * FROM {self.table_name} 
                    WHERE is_deleted = false
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """)
                
                result = await session.execute(query, {
                    'limit': limit,
                    'offset': offset
                })
                rows = result.fetchall()
                
                return [self._row_to_agent_info(row) for row in rows]
                
        except Exception as e:
            logger.error(f"查找所有智能体失败: {e}")
            return []
    
    def _row_to_agent_info(self, row) -> AgentInfo:
        """数据库行转换为智能体信息"""
        return AgentInfo(
            agent_id=row.agent_id,
            name=row.name,
            agent_type=row.agent_type,
            user_id=row.user_id,
            description=row.description,
            version=row.version,
            organization_id=row.organization_id,
            config_data=row.config_data,
            is_active=row.is_active,
            is_deleted=row.is_deleted,
            created_at=row.created_at,
            updated_at=row.updated_at
        )