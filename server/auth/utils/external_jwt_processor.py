import jwt
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from server.auth.models.user_models import User
from src.database.repositories.user_repository import UserRepository, UserInfo

logger = logging.getLogger(__name__)

class ExternalJWTProcessor:
    """外部JWT处理器"""
    
    @staticmethod
    def generate_uuid_from_external_id(external_id: str) -> str:
        """从外部ID生成确定性UUID"""
        # 使用SHA-256创建确定性UUID
        hash_object = hashlib.sha256(external_id.encode('utf-8'))
        hash_hex = hash_object.hexdigest()
        
        # 将哈希值转换为UUID格式
        uuid_str = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
        return uuid_str
    
    @staticmethod
    def decode_external_jwt(token: str) -> Dict[str, Any]:
        """解析外部JWT（无需验证签名）"""
        try:
            # 不验证签名，直接解析payload
            payload = jwt.decode(token, options={"verify_signature": False})
            
            # 提取用户信息
            user_data = {
                'user_id': payload.get('user_id'),
                'username': payload.get('login_name'),
                'display_name': payload.get('display_name'),
                'organization': payload.get('organization'),
                'region': payload.get('region'),
                'expires_at': payload.get('exp'),
                'issued_at': payload.get('iat'),
                'client_id': payload.get('client_id'),
                'scope': payload.get('scope', [])
            }
            
            # 验证必要字段
            if not user_data['user_id'] or not user_data['username']:
                raise ValueError("JWT missing required fields: user_id or login_name")
            
            # 检查token是否过期
            if user_data['expires_at']:
                exp_time = datetime.fromtimestamp(user_data['expires_at'])
                if exp_time < datetime.now():
                    raise ValueError("JWT token has expired")
            
            logger.debug(f"Successfully decoded JWT for user: {user_data['username']}")
            return user_data
            
        except jwt.DecodeError as e:
            logger.error(f"JWT decode error: {e}")
            raise ValueError(f"Invalid JWT token: {str(e)}")
        except Exception as e:
            logger.error(f"JWT processing error: {e}")
            raise ValueError(f"JWT processing failed: {str(e)}")
    
    @staticmethod
    async def sync_user_from_jwt(jwt_payload: Dict[str, Any], user_repo: UserRepository) -> User:
        """从JWT同步用户信息"""
        try:
            # 查找现有用户
            user_info = await user_repo.get_by_external_id(jwt_payload['user_id'])
            
            # 转换为 User 模型对象（兼容性）
            user = None
            if user_info:
                user = User(
                    id=user_info.user_id,
                    external_user_id=user_info.external_user_id,
                    username=user_info.username,
                    display_name=user_info.display_name,
                    organization=user_info.organization,
                    is_active=user_info.is_active,
                    created_at=user_info.created_at,
                    updated_at=user_info.updated_at
                )
            
            if not user:
                # 创建新用户，为外部用户ID生成确定性UUID
                external_id = jwt_payload['user_id']
                uuid_from_external = ExternalJWTProcessor.generate_uuid_from_external_id(external_id)
                
                new_user_info = UserInfo(
                    user_id=uuid_from_external,
                    external_user_id=external_id,
                    username=jwt_payload['username'],
                    display_name=jwt_payload.get('display_name'),
                    organization=jwt_payload.get('organization'),
                    is_active=True,
                    metadata={
                        'region': jwt_payload.get('region'),
                        'client_id': jwt_payload.get('client_id'),
                        'scope': jwt_payload.get('scope', [])
                    }
                )
                
                try:
                    created_user_info = await user_repo.create(new_user_info)
                    # 转换为User对象
                    user = User(
                        id=created_user_info.user_id,
                        external_user_id=created_user_info.external_user_id,
                        username=created_user_info.username,
                        display_name=created_user_info.display_name,
                        organization=created_user_info.organization,
                        is_active=created_user_info.is_active,
                        created_at=created_user_info.created_at,
                        updated_at=created_user_info.updated_at
                    )
                except ValueError as e:
                    if "User already exists" in str(e):
                        # 用户已存在，重新获取
                        logger.info(f"User already exists, fetching existing user: {jwt_payload['user_id']}")
                        # 尝试多种方式获取用户
                        existing_user_info = await user_repo.get_by_external_id(jwt_payload['user_id'])
                        if not existing_user_info:
                            # 如果通过external_id获取失败，尝试通过user_id获取
                            existing_user_info = await user_repo.get_by_id(jwt_payload['user_id'])
                        if not existing_user_info:
                            # 如果还是失败，尝试通过用户名获取
                            existing_user_info = await user_repo.get_by_username(jwt_payload['username'])
                        
                        if existing_user_info:
                            created_user_info = existing_user_info
                            logger.info(f"Successfully retrieved existing user: {existing_user_info.username}")
                        else:
                            # 如果都失败了，可能是数据库连接问题或者数据不一致，记录错误但不抛出异常
                            logger.error(f"User exists but cannot be retrieved: {jwt_payload['user_id']}")
                            # 创建一个临时用户对象用于返回，避免阻断认证流程
                            created_user_info = new_user_info
                    else:
                        raise
                
                # 转换为 User 模型对象（兼容性）
                user = User(
                    id=created_user_info.user_id,
                    external_user_id=created_user_info.external_user_id,
                    username=created_user_info.username,
                    display_name=created_user_info.display_name,
                    organization=created_user_info.organization,
                    is_active=created_user_info.is_active,
                    created_at=created_user_info.created_at,
                    updated_at=created_user_info.updated_at
                )
                
                logger.info(f"Created new user from JWT: {user.username}")
                
                # 为新用户分配角色
                await ExternalJWTProcessor._assign_user_role(user, jwt_payload, user_repo)
                
            else:
                # 更新现有用户信息
                updated = False
                
                if user.display_name != jwt_payload.get('display_name'):
                    user_info.display_name = jwt_payload.get('display_name')
                    user.display_name = jwt_payload.get('display_name')
                    updated = True
                
                if user.organization != jwt_payload.get('organization'):
                    user_info.organization = jwt_payload.get('organization')
                    user.organization = jwt_payload.get('organization')
                    updated = True
                
                # 更新元数据
                if user_info.metadata.get('region') != jwt_payload.get('region'):
                    user_info.metadata['region'] = jwt_payload.get('region')
                    updated = True
                
                if updated:
                    await user_repo.update(user_info)
                    logger.debug(f"Updated user from JWT: {user.username}")
                
                # 检查并更新用户角色
                await ExternalJWTProcessor._check_and_update_user_role(user, jwt_payload, user_repo)
            
            return user
            
        except Exception as e:
            logger.error(f"Error syncing user from JWT: {e}")
            raise ValueError(f"Failed to sync user: {str(e)}")
    
    @staticmethod
    async def _assign_user_role(user: User, jwt_payload: Dict[str, Any], user_repo: UserRepository):
        """为用户分配适当的角色"""
        try:
            # 根据用户ID/用户名确定角色
            user_id = jwt_payload.get('user_id', '')
            username = jwt_payload.get('username', jwt_payload.get('login_name', ''))
            
            # 确定目标角色
            target_role_name = ExternalJWTProcessor._determine_user_role(user_id, username, jwt_payload)
            
            # 使用数据库管理器执行角色分配
            from src.database.manager import get_database_manager
            db_manager = get_database_manager()
            await db_manager.initialize()
            postgres_adapter = await db_manager.get_postgresql_adapter('server_db')
            
            # 查找目标角色
            role_query = """
                SELECT id FROM roles WHERE name = :role_name AND is_system = true
            """
            result = await postgres_adapter.execute_query(role_query, {"role_name": target_role_name})
            
            if result and len(result) > 0:
                role_id = result[0][0]
                
                # 分配角色（如果不存在）
                assign_role_query = """
                    INSERT INTO user_roles (id, user_id, role_id, granted_at)
                    VALUES (gen_random_uuid(), :user_id, :role_id, NOW())
                    ON CONFLICT (user_id, role_id) DO NOTHING
                """
                await postgres_adapter.execute_query(assign_role_query, {
                    "user_id": user.id,
                    "role_id": role_id
                })
                
                logger.info(f"Assigned role '{target_role_name}' to user: {user.username}")
            else:
                logger.warning(f"Role '{target_role_name}' not found, skipping role assignment")
                
        except Exception as e:
            logger.error(f"Error assigning user role: {e}")
    
    @staticmethod
    async def _check_and_update_user_role(user: User, jwt_payload: Dict[str, Any], user_repo: UserRepository):
        """检查并更新现有用户的角色"""
        try:
            user_id = jwt_payload.get('user_id', '')
            username = jwt_payload.get('username', jwt_payload.get('login_name', ''))
            
            # 确定目标角色
            target_role_name = ExternalJWTProcessor._determine_user_role(user_id, username, jwt_payload)
            
            # 使用数据库管理器检查角色
            from src.database.manager import get_database_manager
            db_manager = get_database_manager()
            await db_manager.initialize()
            postgres_adapter = await db_manager.get_postgresql_adapter('server_db')
            
            # 检查用户是否已有该角色
            check_role_query = """
                SELECT 1 FROM user_roles ur
                JOIN roles r ON ur.role_id = r.id
                WHERE ur.user_id = :user_id AND r.name = :role_name
            """
            
            result = await postgres_adapter.execute_query(check_role_query, {
                "user_id": user.id,
                "role_name": target_role_name
            })
            
            has_role = result and len(result) > 0
            
            if not has_role:
                # 如果没有该角色，则分配
                await ExternalJWTProcessor._assign_user_role(user, jwt_payload, user_repo)
                
        except Exception as e:
            logger.error(f"Error checking user role: {e}")
    
    @staticmethod
    def _determine_user_role(user_id: str, username: str, jwt_payload: Dict[str, Any]) -> str:
        """根据用户信息确定应分配的角色"""
        
        # 超级管理员用户列表
        superadmin_users = ['admin', 'root', 'administrator', 'rf_sjz']
        
        # 管理员用户列表  
        admin_users = ['manager', 'admin_user']
        
        # 检查用户ID或用户名
        if user_id in superadmin_users or username in superadmin_users:
            return 'superadmin'
        elif user_id in admin_users or username in admin_users:
            return 'admin'
        
        # 检查JWT中的scope或role信息
        scopes = jwt_payload.get('scope', [])
        if isinstance(scopes, str):
            scopes = scopes.split()
        
        if 'superadmin' in scopes or 'admin' in scopes:
            return 'superadmin'
        elif 'manager' in scopes:
            return 'admin'
        elif 'power_user' in scopes:
            return 'power_user'
        
        # 默认角色
        return 'user'
    
    @staticmethod
    async def get_user_from_token(token: str, user_repo: UserRepository) -> Optional[User]:
        """从token获取用户（带缓存）"""
        try:
            logger.debug(f"Getting user from JWT token")
            
            # 获取数据库管理器和Redis适配器
            from src.database.manager import get_database_manager
            import hashlib
            import json
            
            db_manager = get_database_manager()
            await db_manager.initialize()
            redis_adapter = await db_manager.get_redis_adapter()
            
            # 先尝试从缓存获取
            session_id = hashlib.md5(token.encode()).hexdigest()
            session_key = f"jwt_session:{session_id}"
            
            cached_session = None
            if redis_adapter and redis_adapter.is_available:
                try:
                    cached_data = await redis_adapter.get(session_key)
                    if cached_data:
                        try:
                            # 检查cached_data是否已经是dict对象
                            if isinstance(cached_data, dict):
                                cached_session = cached_data
                            elif isinstance(cached_data, (str, bytes)):
                                cached_session = json.loads(cached_data)
                            else:
                                logger.warning(f"Unexpected cached_data type: {type(cached_data)}")
                                cached_session = None
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in JWT session cache: {session_id}")
                        except Exception as e:
                            logger.warning(f"Error processing cached session data: {e}")
                except Exception as e:
                    logger.warning(f"Redis get operation failed, skipping cache: {e}")
                    cached_session = None
            
            # 检查会话缓存
            if cached_session and cached_session.get('user_id'):
                # 从用户仓库获取用户
                user_info = await user_repo.get_by_external_id(cached_session['user_id'])
                if user_info:
                    # 转换为 User 模型对象
                    user = User(
                        id=user_info.user_id,
                        external_user_id=user_info.external_user_id,
                        username=user_info.username,
                        display_name=user_info.display_name,
                        organization=user_info.organization,
                        is_active=user_info.is_active,
                        created_at=user_info.created_at,
                        updated_at=user_info.updated_at
                    )
                    logger.debug(f"User loaded from cache: {user.username}")
                    return user
            
            # 解析JWT获取用户信息
            logger.debug(f"Decoding external JWT")
            jwt_payload = ExternalJWTProcessor.decode_external_jwt(token)
            logger.debug(f"JWT payload: {jwt_payload}")
            
            # 同步用户信息
            logger.debug(f"Syncing user from JWT")
            user = await ExternalJWTProcessor.sync_user_from_jwt(jwt_payload, user_repo)
            logger.debug(f"User synced: {user.username if user else 'None'}")
            
            if user and redis_adapter and redis_adapter.is_available:
                try:
                    # 缓存会话
                    session_data = {
                        'user_id': user.external_user_id,
                        'username': user.username,
                        'display_name': user.display_name,
                        'organization': user.organization
                    }
                    await redis_adapter.set(session_key, json.dumps(session_data), 1800)  # 30分钟缓存
                except Exception as e:
                    logger.warning(f"Redis set operation failed, session not cached: {e}")
            
            return user
            
        except Exception as e:
            logger.error(f"Error processing external JWT: {e}")
            import traceback
            logger.error(f"JWT processing error traceback: {traceback.format_exc()}")
            return None
    
    @staticmethod
    def validate_token_scope(jwt_payload: Dict[str, Any], required_scope: str = None) -> bool:
        """验证token的作用域"""
        if not required_scope:
            return True
        
        token_scopes = jwt_payload.get('scope', [])
        if isinstance(token_scopes, str):
            token_scopes = token_scopes.split()
        
        return required_scope in token_scopes
    
    @staticmethod
    def get_token_info(token: str) -> Dict[str, Any]:
        """获取token信息（用于调试）"""
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            
            # 计算token剩余时间
            exp_time = None
            time_left = None
            if payload.get('exp'):
                exp_time = datetime.fromtimestamp(payload['exp'])
                time_left = exp_time - datetime.now()
            
            return {
                'user_id': payload.get('user_id'),
                'username': payload.get('login_name'),
                'display_name': payload.get('display_name'),
                'organization': payload.get('organization'),
                'region': payload.get('region'),
                'client_id': payload.get('client_id'),
                'scope': payload.get('scope', []),
                'issued_at': datetime.fromtimestamp(payload['iat']) if payload.get('iat') else None,
                'expires_at': exp_time,
                'time_left': str(time_left) if time_left else None,
                'is_expired': exp_time < datetime.now() if exp_time else False
            }
            
        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return {'error': str(e)}


class JWTAuthenticationError(Exception):
    """JWT认证异常"""
    pass


class JWTTokenExpiredError(JWTAuthenticationError):
    """JWT token过期异常"""
    pass


class JWTInvalidTokenError(JWTAuthenticationError):
    """JWT token无效异常"""
    pass