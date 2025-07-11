import uvicorn
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.routers import router
from src.routers.agent_router import router as agent_router
from src.auth.middleware.auth_middleware import is_public_path
from src.auth.middleware.rbac_middleware import rbac_middleware
from src.auth.permission_framework import initialize_permission_framework, shutdown_permission_framework
from src.utils.logging_config import logger
from src.database.manager import initialize_global_database_manager, shutdown_global_database_manager
from src.database.init_tables import initialize_database_tables
from src.agents.manager import agent_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    try:
        # 初始化数据库管理器
        logger.info("Initializing unified database manager...")
        await initialize_global_database_manager()
        logger.info("Unified database manager initialized successfully")
        
        # 初始化数据库表
        logger.info("Initializing database tables...")
        await initialize_database_tables()
        logger.info("Database tables initialized successfully")
        
        # 初始化权限框架
        logger.info("Initializing permission framework...")
        await initialize_permission_framework(
            rbac_middleware,
            enable_cache=True,
            enable_audit=True,
            enable_performance_monitoring=True
        )
        logger.info("Permission framework initialized successfully")
        
        # 初始化智能体管理器
        logger.info("Initializing agent manager...")
        await agent_manager.start_monitoring()
        logger.info("Agent manager initialized successfully")
        
        # 初始化核心服务
        logger.info("Initializing core services...")
        
        # 初始化LLM服务
        from src.core.llm import setup_default_models
        await setup_default_models()
        logger.info("LLM service initialized")
        
        # 初始化模板系统
        from src.core.prompts import setup_predefined_templates, template_manager
        await template_manager.load_templates()
        await setup_predefined_templates()
        logger.info("Template system initialized")
        
        logger.info("Core services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    
    yield  # 应用运行期间
    
    # 关闭时执行
    try:
        # 关闭智能体管理器
        logger.info("Shutting down agent manager...")
        await agent_manager.shutdown()
        logger.info("Agent manager shutdown successfully")
        
        logger.info("Shutting down permission framework...")
        await shutdown_permission_framework()
        logger.info("Permission framework shutdown successfully")
        
        # 关闭数据库管理器
        logger.info("Shutting down unified database manager...")
        await shutdown_global_database_manager()
        logger.info("Unified database manager shutdown successfully")
    except Exception as e:
        logger.error(f"Error shutting down application: {e}")

app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/api")
app.include_router(agent_router)  # 智能体路由已经包含了 /api/agents 前缀

# CORS 设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 鉴权中间件
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 获取请求路径
        path = request.url.path

        # 检查是否为公开路径，公开路径无需身份验证
        if is_public_path(path):
            return await call_next(request)

        if not path.startswith("/api"):
            # 非API路径，可能是前端路由或静态资源
            return await call_next(request)

        # # 提取Authorization头
        # auth_header = request.headers.get("Authorization")
        # if not auth_header or not auth_header.startswith("Bearer "):
        #     return JSONResponse(
        #         status_code=status.HTTP_401_UNAUTHORIZED,
        #         content={"detail": f"请先登录。Path: {path}"},
        #         headers={"WWW-Authenticate": "Bearer"}
        #     )

        # # 获取token
        # token = auth_header.split("Bearer ")[1]

        # # 添加token到请求状态，后续路由可以直接使用
        # request.state.token = token

        # 继续处理请求
        return await call_next(request)

# 添加鉴权中间件
app.add_middleware(AuthMiddleware)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050)

