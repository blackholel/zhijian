"""
资源抽象基类
定义资源的通用接口和层次结构
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Set
from .core import ResourceType, ResourceIdentifier, Permission

class Resource(ABC):
    """资源抽象基类"""
    
    def __init__(self, identifier: ResourceIdentifier, metadata: Optional[Dict[str, Any]] = None):
        self.identifier = identifier
        self.metadata = metadata or {}
        self._parent: Optional['Resource'] = None
        self._children: Set['Resource'] = set()
    
    @property
    def resource_type(self) -> ResourceType:
        return self.identifier.resource_type
    
    @property
    def resource_id(self) -> str:
        return self.identifier.resource_id
    
    @property
    def namespace(self) -> Optional[str]:
        return self.identifier.namespace
    
    @property
    def uri(self) -> str:
        return str(self.identifier)
    
    # 层次结构支持
    def add_child(self, child: 'Resource'):
        """添加子资源"""
        child._parent = self
        self._children.add(child)
    
    def remove_child(self, child: 'Resource'):
        """移除子资源"""
        child._parent = None
        self._children.discard(child)
    
    @property
    def parent(self) -> Optional['Resource']:
        return self._parent
    
    @property
    def children(self) -> Set['Resource']:
        return self._children.copy()
    
    def get_ancestors(self) -> List['Resource']:
        """获取所有祖先资源"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors
    
    def get_descendants(self) -> Set['Resource']:
        """获取所有后代资源"""
        descendants = set()
        for child in self._children:
            descendants.add(child)
            descendants.update(child.get_descendants())
        return descendants
    
    # 抽象方法
    @abstractmethod
    async def get_owner(self) -> Optional[str]:
        """获取资源所有者ID"""
        pass
    
    @abstractmethod
    async def get_resource_attributes(self) -> Dict[str, Any]:
        """获取资源属性，用于权限决策"""
        pass
    
    @abstractmethod
    async def is_public(self) -> bool:
        """检查资源是否公开"""
        pass
    
    # 可选的生命周期方法
    async def on_permission_granted(self, user_id: str, permission: Permission, context: Dict[str, Any]):
        """权限授予回调"""
        pass
    
    async def on_permission_revoked(self, user_id: str, permission: Permission, context: Dict[str, Any]):
        """权限撤销回调"""
        pass
    
    def __hash__(self):
        return hash(self.uri)
    
    def __eq__(self, other):
        return isinstance(other, Resource) and self.uri == other.uri