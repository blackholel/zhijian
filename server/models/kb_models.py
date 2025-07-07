from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import time
import uuid

from server.models import Base

class KnowledgeDatabase(Base):
    """知识库模型"""
    __tablename__ = 'knowledge_databases'
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    db_id = Column(String, nullable=False, unique=True, index=True)  # 数据库ID
    name = Column(String, nullable=False)  # 数据库名称
    description = Column(Text, nullable=True)  # 描述
    embed_model = Column(String, nullable=True)  # 嵌入模型名称
    dimension = Column(Integer, nullable=True)  # 向量维度
    meta_info = Column(JSON, nullable=True)  # 元数据
    created_at = Column(DateTime, default=func.now())  # 创建时间
    
    # 权限相关字段
    owner_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)  # 知识库所有者
    is_public = Column(Boolean, default=False)  # 是否公开
    access_level = Column(String(20), default='private')  # private, shared, public

    # 关系
    files = relationship("KnowledgeFile", back_populates="database", cascade="all, delete-orphan")
    permissions = relationship("KnowledgeDatabasePermission", back_populates="database", cascade="all, delete-orphan")

    def to_dict(self, with_nodes=True):
        """转换为字典格式，确保meta_info映射为metadata"""
        try:
            result = {
                "id": getattr(self, 'id', None),
                "db_id": getattr(self, 'db_id', None),
                "name": getattr(self, 'name', None),
                "description": getattr(self, 'description', None),
                "embed_model": getattr(self, 'embed_model', None),
                "dimension": getattr(self, 'dimension', None),
                "metadata": getattr(self, 'meta_info', None) or {},
                "created_at": getattr(self, 'created_at', None).isoformat() if getattr(self, 'created_at', None) else None,
                "owner_id": str(getattr(self, 'owner_id', None)) if getattr(self, 'owner_id', None) else None,
                "is_public": getattr(self, 'is_public', False),
                "access_level": getattr(self, 'access_level', 'private')
            }
            # 添加文件信息
            files_attr = getattr(self, 'files', None)
            if files_attr:
                result["files"] = {file.file_id: file.to_dict(with_nodes=with_nodes) for file in files_attr}
            else:
                result["files"] = {}
            return result
        except Exception as e:
            # 如果出现属性访问错误，返回基本信息
            return {
                "id": getattr(self, 'id', None),
                "db_id": getattr(self, 'db_id', None),
                "name": getattr(self, 'name', 'Unknown'),
                "description": getattr(self, 'description', None),
                "metadata": {},
                "files": {}
            }

class KnowledgeFile(Base):
    """知识库文件模型"""
    __tablename__ = 'knowledge_files'
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, nullable=False, unique=True, index=True)  # 文件ID
    database_id = Column(String, ForeignKey('knowledge_databases.db_id'), nullable=False)  # 所属数据库ID
    filename = Column(String, nullable=False)  # 文件名
    path = Column(String, nullable=False)  # 文件路径（本地路径或MinIO存储键）
    file_type = Column(String, nullable=False)  # 文件类型
    status = Column(String, nullable=False)  # 处理状态
    storage_type = Column(String, default='local')  # 存储类型：local, minio
    file_size = Column(Integer, nullable=True)  # 文件大小
    file_metadata = Column(JSON, nullable=True)  # 文件元数据 (避免与SQLAlchemy的metadata冲突)
    created_at = Column(DateTime, default=func.now())  # 创建时间
    
    # 权限相关字段
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)  # 上传者

    # 关系
    database = relationship("KnowledgeDatabase", back_populates="files")
    nodes = relationship("KnowledgeNode", back_populates="file", cascade="all, delete-orphan")

    @property
    def computed_node_count(self):
        """动态计算节点数量"""
        return len(self.nodes) if self.nodes is not None else 0

    def to_dict(self, with_nodes=True):
        """转换为字典格式"""
        try:
            result = {
                "file_id": getattr(self, 'file_id', None),
                "filename": getattr(self, 'filename', None),
                "path": getattr(self, 'path', None),
                "type": getattr(self, 'file_type', None),
                "status": getattr(self, 'status', 'unknown'),
                "storage_type": getattr(self, 'storage_type', 'local'),
                "file_size": getattr(self, 'file_size', None),
                "metadata": getattr(self, 'file_metadata', None) or {},
                "node_count": self.computed_node_count,
                "created_at": getattr(self, 'created_at', None).timestamp() if getattr(self, 'created_at', None) else time.time(),
                "uploaded_by": str(getattr(self, 'uploaded_by', None)) if getattr(self, 'uploaded_by', None) else None,
                "database_id": getattr(self, 'database_id', None)
            }
            if with_nodes:
                nodes_attr = getattr(self, 'nodes', None)
                if nodes_attr:
                    result["nodes"] = [node.to_dict() for node in nodes_attr]
                else:
                    result["nodes"] = []
            return result
        except Exception as e:
            # 如果出现属性访问错误，返回基本信息
            return {
                "file_id": getattr(self, 'file_id', None),
                "filename": getattr(self, 'filename', 'Unknown'),
                "path": getattr(self, 'path', None),
                "type": getattr(self, 'file_type', 'unknown'),
                "status": getattr(self, 'status', 'unknown'),
                "node_count": 0,
                "created_at": time.time(),
                "nodes": []
            }

class KnowledgeNode(Base):
    """知识块模型"""
    __tablename__ = 'knowledge_nodes'
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, ForeignKey('knowledge_files.file_id'), nullable=False)  # 所属文件ID
    text = Column(Text, nullable=False)  # 文本内容
    hash = Column(String, nullable=True)  # 文本哈希值
    start_char_idx = Column(Integer, nullable=True)  # 开始字符索引
    end_char_idx = Column(Integer, nullable=True)  # 结束字符索引
    meta_info = Column(JSON, nullable=True)  # 元数据

    # 关系
    file = relationship("KnowledgeFile", back_populates="nodes")

    def to_dict(self):
        """转换为字典格式，确保meta_info映射为metadata"""
        return {
            "id": self.id,
            "file_id": self.file_id,
            "text": self.text,
            "hash": self.hash,
            "start_char_idx": self.start_char_idx,
            "end_char_idx": self.end_char_idx,
            "metadata": self.meta_info or {}  # 确保映射正确
        }


class KnowledgeDatabasePermission(Base):
    """知识库权限模型 - 支持细粒度权限控制"""
    __tablename__ = 'knowledge_database_permissions'
    __table_args__ = {'extend_existing': True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    database_id = Column(String, ForeignKey('knowledge_databases.db_id', ondelete='CASCADE'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    permission_type = Column(String(20), nullable=False)  # read, write, admin
    granted_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    granted_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)
    
    # 关系
    database = relationship("KnowledgeDatabase", back_populates="permissions")

    def to_dict(self):
        return {
            "id": str(self.id),
            "database_id": self.database_id,
            "user_id": str(self.user_id),
            "permission_type": self.permission_type,
            "granted_by": str(self.granted_by) if self.granted_by else None,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
