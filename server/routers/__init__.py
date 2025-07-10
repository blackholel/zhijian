from fastapi import APIRouter
# from server.routers.data_router import data  # 注释掉无权限控制的 data_router，统一使用 knowledge_router
from server.routers.base_router import base
from server.routers.auth_router import auth
from server.routers.graph_router import graph
from server.auth.routers.rbac_router import router as rbac_router
from server.auth.routers.permission_router import permission_mgmt
from server.routers.database_router import router as database_router
from server.routers.knowledge_router import knowledge_router
from server.routers.kb_collection_router import router as kb_collection_router

router = APIRouter()
router.include_router(base)
# router.include_router(data)  # 注释掉无权限控制的 data_router，统一使用 knowledge_router
router.include_router(auth)
router.include_router(graph)
router.include_router(rbac_router)
router.include_router(permission_mgmt)
router.include_router(database_router)
router.include_router(knowledge_router)
router.include_router(kb_collection_router)
