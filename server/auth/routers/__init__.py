"""Auth routers module"""
from .rbac_router import router as rbac_router
from .permission_router import permission_mgmt as permission_router

__all__ = ["rbac_router", "permission_router"]