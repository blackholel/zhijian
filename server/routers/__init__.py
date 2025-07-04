from fastapi import APIRouter
from server.routers.chat_router import chat
from server.routers.data_router import data
from server.routers.base_router import base
from server.routers.auth_router import auth
from server.routers.graph_router import graph
from server.routers.rbac_router import router as rbac_router

router = APIRouter()
router.include_router(base)
router.include_router(chat)
router.include_router(data)
router.include_router(auth)
router.include_router(graph)
router.include_router(rbac_router)
