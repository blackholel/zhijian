"""
具体资源类型实现
包含知识库、对话会话、MCP工具等资源的具体实现
"""

from typing import Dict, Any, Optional
from sqlalchemy import text
import logging

from .core import ResourceType, ResourceIdentifier
from .resources import Resource
from server.db_manager import db_manager

logger = logging.getLogger(__name__)

class KnowledgeBaseResource(Resource):
    """知识库资源"""
    
    def __init__(self, db_id: str, namespace: str = None):
        identifier = ResourceIdentifier(ResourceType.KNOWLEDGE_BASE, db_id, namespace)
        super().__init__(identifier)
    
    async def get_owner(self) -> Optional[str]:
        """获取知识库所有者"""
        db = db_manager.get_session()
        try:
            result = db.execute(text("""
                SELECT owner_id FROM knowledge_databases 
                WHERE db_id = :db_id
            """), {"db_id": self.resource_id}).first()
            return str(result[0]) if result else None
        except Exception as e:
            logger.error(f"Error getting KB owner: {e}")
            return None
        finally:
            db.close()
    
    async def get_resource_attributes(self) -> Dict[str, Any]:
        """获取知识库属性"""
        db = db_manager.get_session()
        try:
            result = db.execute(text("""
                SELECT is_public, access_level, meta_info, created_at
                FROM knowledge_databases 
                WHERE db_id = :db_id
            """), {"db_id": self.resource_id}).first()
            
            if result:
                return {
                    "is_public": result[0],
                    "access_level": result[1],
                    "metadata": result[2] or {},
                    "created_at": result[3].isoformat() if result[3] else None
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting KB attributes: {e}")
            return {}
        finally:
            db.close()
    
    async def is_public(self) -> bool:
        """检查知识库是否公开"""
        attributes = await self.get_resource_attributes()
        return attributes.get("is_public", False)

class ChatSessionResource(Resource):
    """对话会话资源"""
    
    def __init__(self, session_id: str, namespace: str = None):
        identifier = ResourceIdentifier(ResourceType.CHAT_SESSION, session_id, namespace)
        super().__init__(identifier)
    
    async def get_owner(self) -> Optional[str]:
        """获取对话会话所有者"""
        db = db_manager.get_session()
        try:
            # 假设有chat_sessions表
            result = db.execute(text("""
                SELECT user_id FROM chat_sessions 
                WHERE session_id = :session_id
            """), {"session_id": self.resource_id}).first()
            return str(result[0]) if result else None
        except Exception as e:
            logger.error(f"Error getting chat session owner: {e}")
            # 如果表不存在，可以从session_id中提取用户信息
            # 这里假设session_id格式为 user_id:timestamp
            try:
                if ":" in self.resource_id:
                    return self.resource_id.split(":")[0]
            except:
                pass
            return None
        finally:
            db.close()
    
    async def get_resource_attributes(self) -> Dict[str, Any]:
        """获取对话会话属性"""
        db = db_manager.get_session()
        try:
            # 假设有chat_sessions表
            result = db.execute(text("""
                SELECT user_id, is_shared, created_at, updated_at
                FROM chat_sessions 
                WHERE session_id = :session_id
            """), {"session_id": self.resource_id}).first()
            
            if result:
                return {
                    "owner_id": str(result[0]),
                    "is_shared": result[1] if result[1] is not None else False,
                    "created_at": result[2].isoformat() if result[2] else None,
                    "updated_at": result[3].isoformat() if result[3] else None
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting chat session attributes: {e}")
            return {}
        finally:
            db.close()
    
    async def is_public(self) -> bool:
        """对话会话一般不公开"""
        attributes = await self.get_resource_attributes()
        return attributes.get("is_shared", False)

class MCPToolResource(Resource):
    """MCP工具资源"""
    
    def __init__(self, tool_name: str, namespace: str = None):
        identifier = ResourceIdentifier(ResourceType.MCP_TOOL, tool_name, namespace)
        super().__init__(identifier)
    
    async def get_owner(self) -> Optional[str]:
        """MCP工具可能没有特定所有者，由系统管理"""
        return None
    
    async def get_resource_attributes(self) -> Dict[str, Any]:
        """获取MCP工具属性"""
        # 这里可以从工具配置文件或数据库获取工具属性
        # 暂时返回基于metadata的属性
        return {
            "tool_type": self.metadata.get("tool_type"),
            "security_level": self.metadata.get("security_level", "normal"),
            "requires_approval": self.metadata.get("requires_approval", False),
            "description": self.metadata.get("description", ""),
            "version": self.metadata.get("version", "1.0")
        }
    
    async def is_public(self) -> bool:
        """工具的公开性取决于配置"""
        return self.metadata.get("is_public", False)

class GraphDataResource(Resource):
    """图谱数据资源"""
    
    def __init__(self, graph_id: str, namespace: str = None):
        identifier = ResourceIdentifier(ResourceType.GRAPH_DATA, graph_id, namespace)
        super().__init__(identifier)
    
    async def get_owner(self) -> Optional[str]:
        """获取图谱数据所有者"""
        try:
            # 从Neo4j查询图谱所有者
            # 这里需要根据实际的图数据库结构调整
            from src import graph_base
            if hasattr(graph_base, 'query'):
                result = await graph_base.query(
                    "MATCH (g:Graph {id: $graph_id}) RETURN g.owner_id",
                    graph_id=self.resource_id
                )
                return result[0]["g.owner_id"] if result else None
        except Exception as e:
            logger.error(f"Error getting graph data owner: {e}")
        return None
    
    async def get_resource_attributes(self) -> Dict[str, Any]:
        """获取图谱数据属性"""
        try:
            from src import graph_base
            if hasattr(graph_base, 'query'):
                result = await graph_base.query(
                    "MATCH (g:Graph {id: $graph_id}) RETURN g.sensitivity_level, g.node_count, g.created_at",
                    graph_id=self.resource_id
                )
                if result:
                    return {
                        "sensitivity_level": result[0]["g.sensitivity_level"],
                        "node_count": result[0]["g.node_count"],
                        "created_at": result[0]["g.created_at"]
                    }
        except Exception as e:
            logger.error(f"Error getting graph data attributes: {e}")
        return {}
    
    async def is_public(self) -> bool:
        """检查图谱数据是否公开"""
        attrs = await self.get_resource_attributes()
        return attrs.get("sensitivity_level") == "public"

class FileSystemResource(Resource):
    """文件系统资源"""
    
    def __init__(self, file_path: str, namespace: str = None):
        identifier = ResourceIdentifier(ResourceType.FILE_SYSTEM, file_path, namespace)
        super().__init__(identifier)
    
    async def get_owner(self) -> Optional[str]:
        """获取文件所有者"""
        import os
        import pwd
        try:
            stat = os.stat(self.resource_id)
            return str(stat.st_uid)
        except Exception as e:
            logger.error(f"Error getting file owner: {e}")
            return None
    
    async def get_resource_attributes(self) -> Dict[str, Any]:
        """获取文件属性"""
        import os
        try:
            stat = os.stat(self.resource_id)
            return {
                "size": stat.st_size,
                "permissions": oct(stat.st_mode)[-3:],
                "is_directory": os.path.isdir(self.resource_id),
                "modified_time": stat.st_mtime,
                "created_time": stat.st_ctime
            }
        except Exception as e:
            logger.error(f"Error getting file attributes: {e}")
            return {}
    
    async def is_public(self) -> bool:
        """检查文件是否公开（其他用户可读）"""
        attrs = await self.get_resource_attributes()
        perms = attrs.get("permissions", "000")
        return perms[-1] in ["4", "5", "6", "7"]  # 其他用户可读

class UserProfileResource(Resource):
    """用户资料资源"""
    
    def __init__(self, user_id: str, namespace: str = None):
        identifier = ResourceIdentifier(ResourceType.USER_PROFILE, user_id, namespace)
        super().__init__(identifier)
    
    async def get_owner(self) -> Optional[str]:
        """用户资料的所有者就是用户自己"""
        return self.resource_id
    
    async def get_resource_attributes(self) -> Dict[str, Any]:
        """获取用户资料属性"""
        db = db_manager.get_session()
        try:
            result = db.execute(text("""
                SELECT username, email, is_active, created_at, login_name
                FROM users 
                WHERE id = :user_id
            """), {"user_id": self.resource_id}).first()
            
            if result:
                return {
                    "username": result[0],
                    "email": result[1],
                    "is_active": result[2],
                    "created_at": result[3].isoformat() if result[3] else None,
                    "login_name": result[4]
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting user profile attributes: {e}")
            return {}
        finally:
            db.close()
    
    async def is_public(self) -> bool:
        """用户资料一般不公开"""
        return False

class ResourceFactory:
    """资源工厂"""
    
    _resource_classes = {
        ResourceType.KNOWLEDGE_BASE: KnowledgeBaseResource,
        ResourceType.CHAT_SESSION: ChatSessionResource,
        ResourceType.MCP_TOOL: MCPToolResource,
        ResourceType.GRAPH_DATA: GraphDataResource,
        ResourceType.FILE_SYSTEM: FileSystemResource,
        ResourceType.USER_PROFILE: UserProfileResource,
    }
    
    @classmethod
    def register_resource_class(cls, resource_type: ResourceType, resource_class: type):
        """注册资源类"""
        cls._resource_classes[resource_type] = resource_class
        logger.info(f"Registered resource class for {resource_type.value}: {resource_class.__name__}")
    
    @classmethod
    def create_resource(cls, identifier: ResourceIdentifier, metadata: dict = None) -> Resource:
        """创建资源实例"""
        resource_class = cls._resource_classes.get(identifier.resource_type)
        if not resource_class:
            raise ValueError(f"Unsupported resource type: {identifier.resource_type}")
        
        resource = resource_class(identifier.resource_id, identifier.namespace)
        if metadata:
            resource.metadata.update(metadata)
        return resource
    
    @classmethod
    def get_supported_types(cls) -> list:
        """获取支持的资源类型"""
        return list(cls._resource_classes.keys())