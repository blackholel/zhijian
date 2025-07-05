import jwt
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from server.models.user_model import User
from server.utils.redis_manager import get_permission_cache

logger = logging.getLogger(__name__)

class ExternalJWTProcessor:
    """外部JWT处理器"""
    
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
    def sync_user_from_jwt(jwt_payload: Dict[str, Any], db: Session) -> User:
        """从JWT同步用户信息"""
        try:
            # 查找现有用户
            user = db.query(User).filter(
                User.external_user_id == jwt_payload['user_id']
            ).first()
            
            if not user:
                # 创建新用户
                user = User(
                    external_user_id=jwt_payload['user_id'],
                    username=jwt_payload['username'],
                    display_name=jwt_payload.get('display_name'),
                    organization=jwt_payload.get('organization'),
                    region=jwt_payload.get('region'),
                    login_name=jwt_payload['username'],
                    email=None,  # 外部JWT可能不包含email
                    password_hash=None,  # 外部用户无需密码
                    is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                
                logger.info(f"Created new user from JWT: {user.username}")
                
                # 为新用户分配角色
                ExternalJWTProcessor._assign_user_role(user, jwt_payload, db)
                
            else:
                # 更新现有用户信息
                updated = False
                
                if user.display_name != jwt_payload.get('display_name'):
                    user.display_name = jwt_payload.get('display_name')
                    updated = True
                
                if user.organization != jwt_payload.get('organization'):
                    user.organization = jwt_payload.get('organization')
                    updated = True
                
                if user.region != jwt_payload.get('region'):
                    user.region = jwt_payload.get('region')
                    updated = True
                
                # 更新最后登录时间
                user.last_login = datetime.utcnow()
                updated = True
                
                if updated:
                    db.commit()
                    db.refresh(user)
                    logger.debug(f"Updated user from JWT: {user.username}")
                
                # 检查并更新用户角色
                ExternalJWTProcessor._check_and_update_user_role(user, jwt_payload, db)
            
            return user
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error syncing user from JWT: {e}")
            raise ValueError(f"Failed to sync user: {str(e)}")
    
    @staticmethod
    def _assign_user_role(user: User, jwt_payload: Dict[str, Any], db: Session):
        """为用户分配适当的角色"""
        try:
            # 根据用户ID/用户名确定角色
            user_id = jwt_payload.get('user_id', '')
            username = jwt_payload.get('username', jwt_payload.get('login_name', ''))
            
            # 确定目标角色
            target_role_name = ExternalJWTProcessor._determine_user_role(user_id, username, jwt_payload)
            
            # 查找目标角色
            role_query = text("""
                SELECT id FROM roles WHERE name = :role_name AND is_system = true
            """)
            result = db.execute(role_query, {"role_name": target_role_name}).first()
            
            if result:
                role_id = result[0]
                
                # 分配角色（如果不存在）
                assign_role_query = text("""
                    INSERT INTO user_roles (id, user_id, role_id, granted_at)
                    VALUES (gen_random_uuid(), :user_id, :role_id, NOW())
                    ON CONFLICT (user_id, role_id) DO NOTHING
                """)
                db.execute(assign_role_query, {
                    "user_id": user.id,
                    "role_id": role_id
                })
                db.commit()
                
                logger.info(f"Assigned role '{target_role_name}' to user: {user.username}")
            else:
                logger.warning(f"Role '{target_role_name}' not found, skipping role assignment")
                
        except Exception as e:
            logger.error(f"Error assigning user role: {e}")
    
    @staticmethod
    def _check_and_update_user_role(user: User, jwt_payload: Dict[str, Any], db: Session):
        """检查并更新现有用户的角色"""
        try:
            user_id = jwt_payload.get('user_id', '')
            username = jwt_payload.get('username', jwt_payload.get('login_name', ''))
            
            # 确定目标角色
            target_role_name = ExternalJWTProcessor._determine_user_role(user_id, username, jwt_payload)
            
            # 检查用户是否已有该角色
            check_role_query = text("""
                SELECT 1 FROM user_roles ur
                JOIN roles r ON ur.role_id = r.id
                WHERE ur.user_id = :user_id AND r.name = :role_name
            """)
            
            has_role = db.execute(check_role_query, {
                "user_id": user.id,
                "role_name": target_role_name
            }).first()
            
            if not has_role:
                # 如果没有该角色，则分配
                ExternalJWTProcessor._assign_user_role(user, jwt_payload, db)
                
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
    def get_user_from_token(token: str, db: Session) -> Optional[User]:
        """从token获取用户（带缓存）"""
        try:
            logger.debug(f"Getting user from JWT token")
            
            # 先尝试从缓存获取
            permission_cache = get_permission_cache()
            session_id = permission_cache.cache_jwt_session(token, {})  # 生成session_id
            
            # 检查会话缓存
            cached_session = permission_cache.get_jwt_session(session_id)
            if cached_session and cached_session.get('user_id'):
                # 从数据库获取用户
                user = db.query(User).filter(
                    User.external_user_id == cached_session['user_id']
                ).first()
                if user:
                    logger.debug(f"User loaded from cache: {user.username}")
                    return user
            
            # 解析JWT获取用户信息
            logger.debug(f"Decoding external JWT")
            jwt_payload = ExternalJWTProcessor.decode_external_jwt(token)
            logger.debug(f"JWT payload: {jwt_payload}")
            
            # 同步用户信息
            logger.debug(f"Syncing user from JWT")
            user = ExternalJWTProcessor.sync_user_from_jwt(jwt_payload, db)
            logger.debug(f"User synced: {user.username if user else 'None'}")
            
            if user:
                # 缓存会话
                permission_cache.cache_jwt_session(token, {
                    'user_id': user.external_user_id,
                    'username': user.username,
                    'display_name': user.display_name,
                    'organization': user.organization,
                    'region': user.region
                })
            
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