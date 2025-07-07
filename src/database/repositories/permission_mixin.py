"""
权限控制混入类和装饰器
"""

import logging
from typing import Optional, Dict, Any, Union
from functools import wraps
from datetime import datetime

from server.auth.permission_framework import PermissionEngine, KnowledgeBaseResource, Permission

logger = logging.getLogger(__name__)


class PermissionMixin:
    """权限控制混入类"""
    
    def __init__(self):
        self.permission_engine = None
    
    def set_permission_engine(self, engine: PermissionEngine):
        """设置权限引擎"""
        self.permission_engine = engine
    
    async def check_kb_permission(self, user_id: str, kb_id: str, permission: Permission) -> bool:
        """检查知识库权限"""
        try:
            if not self.permission_engine:
                logger.warning("权限引擎未设置，跳过权限检查")
                return True
            
            resource = KnowledgeBaseResource(kb_id)
            return await self.permission_engine.check_permission_simple(
                user_id, resource, permission
            )
        except Exception as e:
            logger.error(f"权限检查失败: {e}")
            return False
    
    async def check_system_permission(self, user_id: str, permission: Permission) -> bool:
        """检查系统权限"""
        try:
            if not self.permission_engine:
                logger.warning("权限引擎未设置，跳过权限检查")
                return True
            
            # 系统权限检查逻辑
            # 这里可以扩展为系统资源
            return True  # 临时实现
        except Exception as e:
            logger.error(f"系统权限检查失败: {e}")
            return False


def require_kb_permission(permission: Permission, kb_id_param: str = 'kb_id'):
    """
    知识库权限检查装饰器
    
    Args:
        permission: 需要的权限
        kb_id_param: 知识库ID参数名
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # 获取用户ID和知识库ID
            user_id = kwargs.get('user_id')
            kb_id = kwargs.get(kb_id_param)
            
            # 如果参数在args中
            if not user_id or not kb_id:
                # 尝试从函数签名中获取参数位置
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                
                # 跳过self参数，因为args中不包含self
                if param_names and param_names[0] == 'self':
                    param_names = param_names[1:]
                
                for i, arg in enumerate(args):
                    if i < len(param_names):
                        param_name = param_names[i]
                        if param_name == 'user_id':
                            user_id = arg
                        elif param_name == kb_id_param:
                            kb_id = arg
            
            # 权限检查
            if user_id and kb_id and hasattr(self, 'check_kb_permission'):
                has_permission = await self.check_kb_permission(user_id, kb_id, permission)
                if not has_permission:
                    raise PermissionError(f"没有{permission.value}权限")
            
            return await func(self, *args, **kwargs)
        return wrapper
    return decorator


def require_system_permission(permission: Permission):
    """
    系统权限检查装饰器
    
    Args:
        permission: 需要的权限
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # 获取用户ID
            user_id = kwargs.get('user_id')
            
            # 如果参数在args中
            if not user_id:
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                
                # 跳过self参数，因为args中不包含self
                if param_names and param_names[0] == 'self':
                    param_names = param_names[1:]
                
                for i, arg in enumerate(args):
                    if i < len(param_names) and param_names[i] == 'user_id':
                        user_id = arg
                        break
            
            # 权限检查
            if user_id and hasattr(self, 'check_system_permission'):
                has_permission = await self.check_system_permission(user_id, permission)
                if not has_permission:
                    raise PermissionError(f"没有{permission.value}权限")
            
            return await func(self, *args, **kwargs)
        return wrapper
    return decorator


class PermissionValidator:
    """权限验证器"""
    
    def __init__(self, permission_engine: PermissionEngine = None):
        self.permission_engine = permission_engine or PermissionEngine.get_instance()
    
    async def validate_kb_access(self, user_id: str, kb_id: str, 
                               permission: Permission) -> bool:
        """验证知识库访问权限"""
        try:
            resource = KnowledgeBaseResource(kb_id)
            return await self.permission_engine.check_permission_simple(
                user_id, resource, permission
            )
        except Exception as e:
            logger.error(f"知识库权限验证失败: {e}")
            return False
    
    async def validate_file_access(self, user_id: str, file_id: str, 
                                 permission: Permission, kb_repo) -> bool:
        """验证文件访问权限"""
        try:
            # 通过文件获取知识库ID
            async with await kb_repo.get_session() as session:
                from server.models.kb_models import KnowledgeFile
                file_obj = session.query(KnowledgeFile).filter(
                    KnowledgeFile.file_id == file_id
                ).first()
                
                if not file_obj:
                    return False
                
                # 检查知识库权限
                return await self.validate_kb_access(
                    user_id, file_obj.database_id, permission
                )
        except Exception as e:
            logger.error(f"文件权限验证失败: {e}")
            return False
    
    async def validate_node_access(self, user_id: str, node_id: int, 
                                 permission: Permission, kb_repo) -> bool:
        """验证节点访问权限"""
        try:
            # 通过节点获取知识库ID
            async with await kb_repo.get_session() as session:
                from server.models.kb_models import KnowledgeNode, KnowledgeFile
                node = session.query(KnowledgeNode).join(KnowledgeFile).filter(
                    KnowledgeNode.id == node_id
                ).first()
                
                if not node or not node.file:
                    return False
                
                # 检查知识库权限
                return await self.validate_kb_access(
                    user_id, node.file.database_id, permission
                )
        except Exception as e:
            logger.error(f"节点权限验证失败: {e}")
            return False
    
    async def get_user_accessible_resources(self, user_id: str, 
                                          resource_type: str = 'knowledge_base') -> list:
        """获取用户可访问的资源列表"""
        try:
            # 这里可以扩展为通用的资源权限查询
            if resource_type == 'knowledge_base':
                # 返回用户可访问的知识库列表
                # 这需要与具体的仓储实现结合
                pass
            
            return []
        except Exception as e:
            logger.error(f"获取用户可访问资源失败: {e}")
            return []


class AuditLogger:
    """审计日志记录器"""
    
    @staticmethod
    async def log_access_attempt(user_id: str, resource_type: str, 
                               resource_id: str, action: str, 
                               success: bool, details: Dict[str, Any] = None):
        """记录访问尝试"""
        try:
            audit_data = {
                'user_id': user_id,
                'resource_type': resource_type,
                'resource_id': resource_id,
                'action': action,
                'success': success,
                'timestamp': datetime.now().isoformat(),
                'details': details or {}
            }
            
            # 这里可以将审计日志写入数据库或日志文件
            logger.info(f"访问审计: {audit_data}")
            
        except Exception as e:
            logger.error(f"记录审计日志失败: {e}")
    
    @staticmethod
    async def log_permission_change(user_id: str, target_user_id: str,
                                  resource_type: str, resource_id: str,
                                  old_permission: str, new_permission: str):
        """记录权限变更"""
        try:
            audit_data = {
                'action': 'permission_change',
                'operator_id': user_id,
                'target_user_id': target_user_id,
                'resource_type': resource_type,
                'resource_id': resource_id,
                'old_permission': old_permission,
                'new_permission': new_permission,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"权限变更审计: {audit_data}")
            
        except Exception as e:
            logger.error(f"记录权限变更审计失败: {e}")


def audit_access(resource_type: str, action: str):
    """访问审计装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            user_id = kwargs.get('user_id')
            resource_id = kwargs.get('kb_id') or kwargs.get('file_id') or kwargs.get('node_id')
            
            try:
                result = await func(self, *args, **kwargs)
                
                # 记录成功访问
                await AuditLogger.log_access_attempt(
                    user_id, resource_type, str(resource_id), action, True
                )
                
                return result
                
            except Exception as e:
                # 记录失败访问
                await AuditLogger.log_access_attempt(
                    user_id, resource_type, str(resource_id), action, False,
                    {'error': str(e)}
                )
                raise
                
        return wrapper
    return decorator