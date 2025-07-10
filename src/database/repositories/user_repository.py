"""
用户数据仓储
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import text

from .base import PostgreSQLRepository
from ..connection_manager import DatabaseConnectionManager

logger = logging.getLogger(__name__)


class UserInfo:
    """用户信息模型"""
    
    def __init__(self, user_id: str, username: str = None, email: str = None,
                 display_name: str = None, external_user_id: str = None,
                 organization: str = None, is_active: bool = True,
                 created_at: datetime = None, updated_at: datetime = None,
                 metadata: Dict[str, Any] = None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.display_name = display_name
        self.external_user_id = external_user_id
        self.organization = organization
        self.is_active = is_active
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'email': self.email,
            'display_name': self.display_name,
            'external_user_id': self.external_user_id,
            'organization': self.organization,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserInfo':
        """从字典创建"""
        created_at = None
        if data.get('created_at'):
            if isinstance(data['created_at'], str):
                created_at = datetime.fromisoformat(data['created_at'])
            elif isinstance(data['created_at'], datetime):
                created_at = data['created_at']
        
        updated_at = None
        if data.get('updated_at'):
            if isinstance(data['updated_at'], str):
                updated_at = datetime.fromisoformat(data['updated_at'])
            elif isinstance(data['updated_at'], datetime):
                updated_at = data['updated_at']
        
        return cls(
            user_id=data.get('id') or data.get('user_id'),  # 数据库字段是id，不是user_id
            username=data.get('username'),
            email=data.get('email'),
            display_name=data.get('display_name'),
            external_user_id=data.get('external_user_id'),
            organization=data.get('organization'),
            is_active=data.get('is_active', True),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get('metadata', {})
        )
    
    def __repr__(self):
        return f"UserInfo(user_id='{self.user_id}', username='{self.username}')"


class UserRepository(PostgreSQLRepository[UserInfo]):
    """用户数据仓储"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        super().__init__(connection_manager, 'server_db')
        self.enable_cache(ttl=1800)  # 30分钟缓存
    
    async def create(self, user: UserInfo) -> UserInfo:
        """创建用户"""
        try:
            async with await self.get_session() as session:
                # 检查用户是否已存在（只检查external_user_id，避免UUID格式错误）
                existing_user = session.execute(text("SELECT user_id FROM users WHERE external_user_id = :external_user_id"), {
                    'external_user_id': user.external_user_id
                }).first()
                
                if existing_user:
                    raise ValueError(f"User already exists: {user.user_id}")
                
                # 插入新用户
                query = """
                    INSERT INTO users (user_id, username, email, display_name, external_user_id, 
                                     organization, is_active, created_at, updated_at, metadata)
                    VALUES (:user_id, :username, :email, :display_name, :external_user_id,
                           :organization, :is_active, :created_at, :updated_at, :metadata)
                """
                
                import json
                await self.execute_query(query, {
                    'user_id': user.user_id,
                    'username': user.username,
                    'email': user.email,
                    'display_name': user.display_name,
                    'external_user_id': user.external_user_id,
                    'organization': user.organization,
                    'is_active': user.is_active,
                    'created_at': user.created_at,
                    'updated_at': user.updated_at,
                    'metadata': json.dumps(user.metadata) if user.metadata else '{}'
                })
            
            # 设置缓存
            await self._set_to_cache(f"user:{user.user_id}", user.to_dict())
            
            logger.info(f"User created: {user.user_id}")
            return user
            
        except Exception as e:
            logger.error(f"Failed to create user {user.user_id}: {e}")
            raise
    
    async def get_by_id(self, user_id: str) -> Optional[UserInfo]:
        """根据ID获取用户"""
        # 先尝试从缓存获取
        cached_data = await self._get_from_cache(f"user:{user_id}")
        if cached_data:
            return UserInfo.from_dict(cached_data)
        
        try:
            query = "SELECT * FROM users WHERE user_id = :user_id AND is_active = true"
            result = await self.execute_query(query, {'user_id': user_id})
            
            if result:
                # 处理SQLAlchemy行对象
                row = result[0]
                if hasattr(row, '_asdict'):
                    user_data = row._asdict()
                elif hasattr(row, '__dict__'):
                    user_data = row.__dict__
                else:
                    user_data = dict(row)
                
                # 解析metadata JSON字符串
                if user_data.get('metadata') and isinstance(user_data['metadata'], str):
                    try:
                        import json
                        user_data['metadata'] = json.loads(user_data['metadata'])
                    except json.JSONDecodeError:
                        user_data['metadata'] = {}
                user = UserInfo.from_dict(user_data)
                
                # 设置缓存
                await self._set_to_cache(f"user:{user_id}", user.to_dict())
                
                return user
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None
    
    async def get_by_external_id(self, external_user_id: str) -> Optional[UserInfo]:
        """根据外部用户ID获取用户"""
        # 先尝试从缓存获取
        cached_data = await self._get_from_cache(f"user:ext:{external_user_id}")
        if cached_data:
            return UserInfo.from_dict(cached_data)
        
        try:
            query = "SELECT * FROM users WHERE external_user_id = :external_user_id AND is_active = true"
            result = await self.execute_query(query, {'external_user_id': external_user_id})
            
            if result:
                # 处理SQLAlchemy行对象
                row = result[0]
                if hasattr(row, '_asdict'):
                    user_data = row._asdict()
                elif hasattr(row, '__dict__'):
                    user_data = row.__dict__
                else:
                    user_data = dict(row)
                
                # 解析metadata JSON字符串
                if user_data.get('metadata') and isinstance(user_data['metadata'], str):
                    try:
                        import json
                        user_data['metadata'] = json.loads(user_data['metadata'])
                    except json.JSONDecodeError:
                        user_data['metadata'] = {}
                user = UserInfo.from_dict(user_data)
                
                # 设置多个缓存键
                await self._set_to_cache(f"user:{user.user_id}", user.to_dict())
                await self._set_to_cache(f"user:ext:{external_user_id}", user.to_dict())
                
                return user
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by external ID {external_user_id}: {e}")
            return None
    
    async def get_by_username(self, username: str) -> Optional[UserInfo]:
        """根据用户名获取用户"""
        try:
            query = "SELECT * FROM users WHERE username = :username AND is_active = true"
            result = await self.execute_query(query, {'username': username})
            
            if result:
                # 处理SQLAlchemy行对象
                row = result[0]
                if hasattr(row, '_asdict'):
                    user_data = row._asdict()
                elif hasattr(row, '__dict__'):
                    user_data = row.__dict__
                else:
                    user_data = dict(row)
                # 解析metadata JSON字符串
                if user_data.get('metadata') and isinstance(user_data['metadata'], str):
                    try:
                        import json
                        user_data['metadata'] = json.loads(user_data['metadata'])
                    except json.JSONDecodeError:
                        user_data['metadata'] = {}
                user = UserInfo.from_dict(user_data)
                return user
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by username {username}: {e}")
            return None
    
    async def update(self, user: UserInfo) -> UserInfo:
        """更新用户"""
        try:
            user.updated_at = datetime.now()
            
            query = """
                UPDATE users 
                SET username = :username, email = :email, display_name = :display_name,
                    organization = :organization, is_active = :is_active,
                    updated_at = :updated_at, metadata = :metadata
                WHERE user_id = :user_id
            """
            
            import json
            await self.execute_query(query, {
                'user_id': user.user_id,
                'username': user.username,
                'email': user.email,
                'display_name': user.display_name,
                'organization': user.organization,
                'is_active': user.is_active,
                'updated_at': user.updated_at,
                'metadata': json.dumps(user.metadata) if user.metadata else '{}'
            })
            
            # 清除相关缓存
            await self._delete_from_cache(f"user:{user.user_id}")
            if user.external_user_id:
                await self._delete_from_cache(f"user:ext:{user.external_user_id}")
            
            logger.info(f"User updated: {user.user_id}")
            return user
            
        except Exception as e:
            logger.error(f"Failed to update user {user.user_id}: {e}")
            raise
    
    async def delete(self, user_id: str) -> bool:
        """删除用户（软删除）"""
        try:
            query = """
                UPDATE users 
                SET is_active = false, updated_at = :updated_at
                WHERE user_id = :user_id
            """
            
            await self.execute_query(query, {
                'user_id': user_id,
                'updated_at': datetime.now()
            })
            
            # 清除缓存
            await self._delete_from_cache(f"user:{user_id}")
            await self._invalidate_cache_pattern(f"user:ext:*")
            
            logger.info(f"User deleted: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[UserInfo]:
        """查找所有用户"""
        try:
            query = """
                SELECT * FROM users 
                WHERE is_active = true
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """
            
            result = await self.execute_query(query, {
                'limit': limit,
                'offset': offset
            })
            
            users = []
            for row in result:
                user_data = dict(row)
                user = UserInfo.from_dict(user_data)
                users.append(user)
            
            return users
            
        except Exception as e:
            logger.error(f"Failed to find all users: {e}")
            return []
    
    async def find_by_organization(self, organization: str, 
                                  limit: int = 100, offset: int = 0) -> List[UserInfo]:
        """根据组织查找用户"""
        try:
            query = """
                SELECT * FROM users 
                WHERE organization = :organization AND is_active = true
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """
            
            result = await self.execute_query(query, {
                'organization': organization,
                'limit': limit,
                'offset': offset
            })
            
            users = []
            for row in result:
                user_data = dict(row)
                user = UserInfo.from_dict(user_data)
                users.append(user)
            
            return users
            
        except Exception as e:
            logger.error(f"Failed to find users by organization {organization}: {e}")
            return []
    
    async def search_users(self, query: str, limit: int = 20) -> List[UserInfo]:
        """搜索用户"""
        try:
            sql_query = """
                SELECT * FROM users 
                WHERE (username ILIKE :query OR email ILIKE :query OR display_name ILIKE :query)
                  AND is_active = true
                ORDER BY 
                    CASE 
                        WHEN username = :exact_query THEN 1
                        WHEN username ILIKE :exact_query THEN 2
                        ELSE 3
                    END,
                    created_at DESC
                LIMIT :limit
            """
            
            search_pattern = f"%{query}%"
            result = await self.execute_query(sql_query, {
                'query': search_pattern,
                'exact_query': query,
                'limit': limit
            })
            
            users = []
            for row in result:
                user_data = dict(row)
                user = UserInfo.from_dict(user_data)
                users.append(user)
            
            return users
            
        except Exception as e:
            logger.error(f"Failed to search users with query '{query}': {e}")
            return []
    
    async def count(self, criteria: Dict[str, Any] = None) -> int:
        """统计用户数量"""
        try:
            base_query = "SELECT COUNT(*) FROM users WHERE is_active = true"
            params = {}
            
            if criteria:
                conditions = []
                if 'organization' in criteria:
                    conditions.append("organization = :organization")
                    params['organization'] = criteria['organization']
                
                if conditions:
                    base_query += " AND " + " AND ".join(conditions)
            
            result = await self.execute_query(base_query, params)
            return result[0][0] if result else 0
            
        except Exception as e:
            logger.error(f"Failed to count users: {e}")
            return 0
    
    async def get_user_statistics(self) -> Dict[str, Any]:
        """获取用户统计信息"""
        try:
            stats_query = """
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(*) FILTER (WHERE is_active = true) as active_users,
                    COUNT(*) FILTER (WHERE is_active = false) as inactive_users,
                    COUNT(DISTINCT organization) as organizations_count,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') as new_users_30d
                FROM users
            """
            
            result = await self.execute_query(stats_query)
            
            if result:
                # 处理SQLAlchemy行对象
                row = result[0]
                if hasattr(row, '_asdict'):
                    stats = row._asdict()
                elif hasattr(row, '__dict__'):
                    stats = row.__dict__
                else:
                    stats = dict(row)
                
                # 获取组织分布
                org_query = """
                    SELECT organization, COUNT(*) as user_count
                    FROM users 
                    WHERE is_active = true AND organization IS NOT NULL
                    GROUP BY organization
                    ORDER BY user_count DESC
                    LIMIT 10
                """
                
                org_result = await self.execute_query(org_query)
                organizations = []
                if org_result:
                    for row in org_result:
                        if hasattr(row, '_asdict'):
                            organizations.append(row._asdict())
                        elif hasattr(row, '__dict__'):
                            organizations.append(row.__dict__)
                        else:
                            organizations.append(dict(row))
                
                stats['organization_distribution'] = organizations
                
                return stats
            
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get user statistics: {e}")
            return {}
    
    async def create_or_update_user(self, user: UserInfo) -> UserInfo:
        """创建或更新用户（Upsert操作）"""
        try:
            existing_user = await self.get_by_id(user.user_id)
            if existing_user:
                # 更新现有用户的非空字段
                if user.username:
                    existing_user.username = user.username
                if user.email:
                    existing_user.email = user.email
                if user.display_name:
                    existing_user.display_name = user.display_name
                if user.organization:
                    existing_user.organization = user.organization
                if user.metadata:
                    existing_user.metadata.update(user.metadata)
                
                return await self.update(existing_user)
            else:
                return await self.create(user)
                
        except Exception as e:
            logger.error(f"Failed to create or update user {user.user_id}: {e}")
            raise
    
    async def is_first_run(self) -> bool:
        """检查是否是首次运行（没有用户）"""
        try:
            query = "SELECT COUNT(*) FROM users WHERE is_active = true"
            result = await self.execute_query(query)
            count = result[0][0] if result else 0
            return count == 0
        except Exception as e:
            logger.error(f"Error checking first run: {e}")
            return True
    
    async def check_first_run(self) -> bool:
        """兼容性方法：检查是否是首次运行"""
        return await self.is_first_run()