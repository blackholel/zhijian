# CLAUDE.md

本文件为Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。
使用中文输出
## 项目概述

语析知识库（Yuxi-Know）是一个基于AI的智能知识管理平台，结合了大语言模型与检索增强生成（RAG）和知识图谱技术。系统提供对话式AI、文档处理、智能代理和多模态处理能力。

## 开发环境配置

### 环境要求

确保以下数据库服务已启动：
- **Neo4j图数据库**: bolt://localhost:7687 (用户名: neo4j, 密码: A620250234Neo4j)
- **PostgreSQL**: localhost:5432 (用户名: postgres, 密码: fa6Z363@3bc6af5134)
  - 主数据库: xm
  - LightRAG数据库: lightrag
- **Milvus向量数据库**: localhost:19530
- **Redis缓存**: localhost:6379
- **MinIO对象存储**: localhost:9001

### 启动开发环境

#### 1. 安装Python依赖
```bash
# 进入项目根目录
cd /home/Projects/Yuxi-Know-main

# 安装依赖包
pip install -r requirements.txt
```

#### 2. 配置环境变量
创建 `src/.env` 文件，包含必要的API密钥：
```bash
# 硅流API密钥（必需）
SILICONFLOW_API_KEY=your_api_key

# 可选配置
TAVILY_API_KEY=your_tavily_key      # 网络搜索功能
OPENAI_API_KEY=your_openai_key      # OpenAI模型
DEEPSEEK_API_KEY=your_deepseek_key  # DeepSeek模型
```

#### 3. 启动API服务器
```bash
# 启动后端API服务
python -m server.main
```

#### 4. 启动前端服务
```bash
# 在新终端中启动前端
cd web
pnpm install
pnpm dev
```

### 访问地址
- **Web应用**: http://localhost:5173
- **API文档**: http://localhost:5050/docs
- **数据库管理API**: http://localhost:5050/api/database/
- **Neo4j浏览器**: http://localhost:7474
- **MinIO控制台**: http://localhost:9001 (admin/minioadmin)

## 架构概览

### 核心组件
- **server/**: FastAPI后端，提供认证、对话和图谱API
- **src/**: 核心应用逻辑，包括代理、模型和插件
  - **src/database/**: 统一数据库管理系统
  - **src/file/**: 文件管理系统
- **web/**: Vue.js前端，提供图谱可视化和对话界面

### 关键技术栈
- **后端**: FastAPI, LangChain/LangGraph, LlamaIndex, LightRAG
- **前端**: Vue.js 3, Ant Design Vue, Vite, Pinia, Sigma.js
- **数据库**: Neo4j（图谱）, PostgreSQL（元数据）, Milvus（向量）
- **AI/ML**: 多LLM提供商, BGE-M3嵌入, OCR处理

### 智能代理系统
平台使用基于插件的代理架构，集成LangGraph：
- **代理**: 位于 `src/agents/`，可配置工作流
- **工具**: 可扩展工具系统，包括网络搜索、知识库和计算器
- **配置**: 通过配置文件控制代理行为

### 知识管理
- **RAG管道**: 文档摄取 → OCR处理 → 向量嵌入 → 检索
- **知识图谱**: Neo4j存储结构化数据和实体关系
- **多模态**: 支持PDF、图像和文本，使用MinerU和PaddleOCR

## 数据库配置

### 当前数据库设置
系统使用以下数据库配置（开发环境）：

#### PostgreSQL主数据库
- **连接**: localhost:5432/xm
- **用户**: postgres
- **密码**: fa6Z363@3bc6af5134
- **用途**: 用户数据、对话历史、文档元数据

#### Neo4j图数据库
- **连接**: bolt://localhost:7687
- **用户**: neo4j 
- **密码**: A620250234Neo4j
- **用途**: 知识图谱存储和实体关系

#### Milvus向量数据库
- **连接**: localhost:19530
- **用户**: root
- **密码**: A6pgsql20200624
- **用途**: 向量嵌入存储和相似性搜索

#### Redis缓存
- **连接**: localhost:6379
- **密码**: A6pgsql202#00624
- **用途**: 缓存和会话存储

### 模型提供商配置
- **默认**: SiliconFlow（提供免费额度）
- **支持**: OpenAI, DeepSeek, 智谱AI, 通义千问, Together.ai
- **本地**: VLLM和Ollama集成
- **配置**: 编辑 `src/static/models.yaml` 自定义模型

## 开发指南

### 后端API开发
- 使用FastAPI异步模式
- **权限认证**: 统一使用 `server/auth/rbac_middleware.py` 进行JWT认证和权限验证
- **权限框架**: 位于 `server/auth/permission_framework/` 的完整权限管理系统
- **数据库访问**: 使用 `src/database/` 统一数据库管理系统
- **文件管理**: 使用 `src/file/` 文件管理系统
- 数据库模型位于 `server/models/`
- API路由位于 `server/routers/`

### 代理开发
- 扩展 `src/agents/` 中的基础代理类
- 在 `src/agents/tools_factory.py` 中定义工具
- 通过配置文件配置代理行为
- 使用LangGraph进行工作流编排

### 插件开发
- 文档处理插件位于 `src/plugins/`
- MinerU和PaddleOCR的OCR功能
- 通过插件系统扩展工具功能

## 常见开发任务

### 添加新的LLM提供商
1. 在 `src/static/models.yaml` 中更新模型配置
2. 将提供商凭据添加到环境变量
3. 在 `web/src/components/ModelSelectorComponent.vue` 中更新前端模型选择器

### 添加新的代理工具
1. 在 `src/agents/tools_factory.py` 中实现工具
2. 在代理配置中注册工具
3. 在 `web/src/components/ToolCallingResult/` 中添加工具结果渲染器

### 数据库模式变更
1. 更新 `server/models/` 中的模型
2. 根据需要创建迁移脚本
3. 更新 `server/routers/` 中的API端点
4. 使用新的数据库管理系统 `src/database/` 访问数据

### 使用新的数据库管理系统
1. 获取数据库管理器：
   ```python
   from src.database.manager import get_database_manager
   db_manager = get_database_manager()
   await db_manager.initialize()
   ```
2. 获取适配器：
   ```python
   postgres_adapter = await db_manager.get_postgresql_adapter('server_db')
   redis_adapter = await db_manager.get_redis_adapter()
   ```
3. 使用仓储模式：
   ```python
   user_repo = db_manager.get_user_repository()
   knowledge_repo = db_manager.get_knowledge_repository()
   ```

### 使用文件管理系统
1. 文件管理器已弃用，改用新的数据库架构
2. 使用 `src/database/repositories/file_repository.py` 管理文件元数据
3. 使用 `src/database/adapters/minio.py` 管理文件存储



## 后端开发命令

### 服务器操作
```bash
# 直接运行API服务器
python -m server.main

# 运行测试
python -m pytest test/

# 检查特定功能
python test/test_neo4j.py
```

## 调试和监控

### 日志位置
- API日志: 控制台输出
- Web日志: 浏览器控制台
- 数据库日志: 各数据库服务日志

### 常见问题
- **端口冲突**: 确保端口5173, 5050, 7474, 9000, 19530, 5432可用
- **内存问题**: 向量操作需要足够的RAM
- **GPU支持**: GPU功能需要NVIDIA Container Toolkit

### 性能监控
- Neo4j浏览器：图查询性能
- Milvus指标：向量搜索性能
- FastAPI自动文档：API调试

## 环境变量配置

### 必需配置
在 `src/.env` 文件中至少需要：
```
SILICONFLOW_API_KEY=your_api_key
```

### 可选配置
```
TAVILY_API_KEY=your_tavily_key      # 网络搜索
OPENAI_API_KEY=your_openai_key      # OpenAI模型
DEEPSEEK_API_KEY=your_deepseek_key  # DeepSeek模型
```

## RBAC权限管理系统

### 权限系统概述
系统已实现完整的基于角色的访问控制（RBAC）系统，支持外部JWT认证和细粒度权限管理。

### 系统架构
- **权限模型**: 用户 → 角色 → 权限的分层授权模式
- **认证方式**: 外部JWT Token认证，支持多种认证源
- **权限缓存**: Redis缓存用户权限，提升验证性能
- **动态分配**: 基于用户身份自动分配适当角色

### 核心组件

#### 数据库模型
```
- users: 用户信息表
- roles: 角色定义表  
- permissions: 权限定义表
- user_roles: 用户角色关联表
- role_permissions: 角色权限关联表
```

#### 权限中间件
- **位置**: `server/auth/rbac_middleware.py`
- **功能**: JWT解析、用户认证、权限验证
- **依赖注入**: 与FastAPI完美集成
- **外部JWT支持**: 自动处理外部JWT认证和用户同步

#### 外部JWT处理
- **位置**: `server/auth/external_jwt_processor.py`
- **功能**: 
  - 解析外部JWT Token（支持RS256等多种签名算法）
  - 用户信息同步到本地数据库
  - 智能角色分配（rf_sjz等预定义用户）
  - 权限缓存管理

#### 新权限框架
- **位置**: `server/auth/permission_framework/`
- **功能**:
  - 策略模式的权限检查系统
  - 支持资源级细粒度权限控制
  - 多层缓存（L1内存 + L2 Redis）
  - 权限审计和性能监控
  - 可扩展的权限策略

#### 系统初始化
- **位置**: `server/auth/rbac_init.py`
- **功能**: 
  - 创建系统角色和权限
  - 数据库表结构初始化
  - 默认数据填充

### 系统角色

| 角色 | 英文名 | 权限描述 |
|------|--------|---------|
| 超级管理员 | `superadmin` | 拥有所有权限(`*:*`) |
| 管理员 | `admin` | 用户管理、知识库管理等核心权限 |
| 高级用户 | `power_user` | 知识库和对话管理权限 |
| 普通用户 | `user` | 基本使用权限 |

### 权限类别

#### 用户管理
- `user:read` - 查看用户
- `user:create` - 创建用户
- `user:update` - 更新用户
- `user:delete` - 删除用户
- `user:grant_role` - 分配角色
- `user:revoke_role` - 撤销角色

#### 角色管理
- `role:read` - 查看角色
- `role:create` - 创建角色
- `role:update` - 更新角色
- `role:delete` - 删除角色
- `role:grant_permission` - 分配权限
- `role:revoke_permission` - 撤销权限

#### 知识库管理
- `kb:read` - 查看知识库
- `kb:create` - 创建知识库
- `kb:update` - 更新知识库
- `kb:delete` - 删除知识库
- `kb:upload` - 上传文档
- `kb:download` - 下载文档
- `kb:query` - 查询知识库
- `kb:share` - 共享知识库
- `kb:manage_users` - 管理知识库用户
- `kb:view_logs` - 查看知识库日志

#### 系统管理
- `system:read` - 查看系统信息
- `system:config` - 系统配置
- `system:restart` - 重启系统
- `system:logs` - 查看日志

### 智能角色分配

系统支持基于用户身份的智能角色分配：

#### 超级管理员用户
自动分配`superadmin`角色的用户：
- `admin`, `root`, `administrator`
- `rf_sjz` (瑞飞数据组)
- JWT Scope包含`superadmin`或`admin`的用户

#### 管理员用户  
自动分配`admin`角色的用户：
- `manager`, `admin_user`
- JWT Scope包含`manager`的用户

#### 默认角色
其他用户默认分配`user`角色

### JWT Token管理

#### 生成Token工具
```bash
# 生成超级管理员token
python generate_token.py admin

# 生成指定用户token
python generate_token.py user <user_id> <username> [display_name]

# 解析token信息
python generate_token.py decode <token>
```

#### 当前管理员用户Token

**admin用户**:
```
用户ID: admin
权限: 超级管理员(*:*)
```

**rf_sjz用户**:
```
用户ID: bpaooawkyt2h5g5h9dza7rl3
用户名: rf_sjz
组织: ORGASZ100011287 (瑞飞数据组)
权限: 超级管理员(*:*)
```

### API接口

#### 数据库管理接口
- `GET /api/database/health` - 获取数据库健康状态
- `GET /api/database/connections` - 获取数据库连接状态（管理员权限）
- `GET /api/database/adapters` - 获取数据库适配器信息（管理员权限）
- `POST /api/database/reconnect` - 重连所有数据库（超级管理员权限）
- `GET /api/database/config` - 获取数据库配置信息（管理员权限）
- `GET /api/database/repositories` - 获取仓储状态（管理员权限）
- `GET /api/database/users/count` - 获取用户数量
- `GET /api/database/users/statistics` - 获取用户统计（管理员权限）

#### RBAC管理接口
- `GET /api/rbac/roles` - 获取角色列表
- `POST /api/rbac/roles` - 创建角色
- `PUT /api/rbac/roles/{id}` - 更新角色
- `DELETE /api/rbac/roles/{id}` - 删除角色

- `GET /api/rbac/permissions` - 获取权限列表
- `POST /api/rbac/permissions` - 创建权限

- `POST /api/rbac/user-roles` - 分配用户角色
- `DELETE /api/rbac/user-roles/{user_id}/{role_id}` - 撤销用户角色

- `GET /api/rbac/users/{user_id}/permissions` - 查看用户权限
- `GET /api/rbac/roles/{role_id}/permissions` - 查看角色权限

#### 权限框架管理接口
- `GET /api/permission-framework/status` - 查看权限框架状态
- `POST /api/permission-framework/cache/invalidate` - 清除权限缓存
- `GET /api/permission-framework/performance` - 查看性能监控
- `GET /api/permission-framework/audit` - 查看权限审计日志

### 开发集成

#### 权限验证装饰器
```python
# RBAC权限验证
from server.auth.rbac_middleware import require_permission

@router.get("/protected-endpoint")
async def protected_function(
    current_user: User = Depends(require_permission("resource:action")),
    db: Session = Depends(get_db)
):
    # 业务逻辑
    pass

# 新权限框架装饰器
from server.auth.permission_framework import require_kb_permission, require_system_permission, Permission

@router.get("/databases")
@require_system_permission(Permission.READ)
async def get_databases(current_user: User = Depends(get_required_user)):
    # 业务逻辑
    pass

@router.delete("/databases/{db_id}")
@require_kb_permission(Permission.DELETE, "db_id")
async def delete_database(db_id: str, current_user: User = Depends(get_required_user)):
    # 业务逻辑
    pass
```

#### 权限检查
```python
# RBAC权限检查
has_permission = await rbac_middleware.verify_permission(user, "resource:action", db)
if not has_permission:
    raise HTTPException(status_code=403, detail="权限不足")

# 新权限框架检查
from server.auth.permission_framework import PermissionEngine, KnowledgeBaseResource, Permission

engine = PermissionEngine.get_instance()
resource = KnowledgeBaseResource(db_id)
has_permission = await engine.check_permission_simple(user_id, resource, Permission.READ)
```

### 系统初始化

#### 首次部署
```bash
# 初始化RBAC系统（创建角色、权限）
python -c "
import sys
sys.path.append('/home/Projects/Yuxi-Know-main')
from server.auth.rbac_init import init_rbac_system
init_rbac_system()
"

# 创建默认管理员用户
python generate_token.py admin
```

#### 权限缓存管理
```bash
# 清除用户权限缓存
python -c "
from server.utils.redis_manager import get_permission_cache
cache = get_permission_cache()
cache.invalidate_user_permissions('user_id')
cache.invalidate_all_user_permissions()
"
```

### 故障排除

#### 常见问题

1. **401 Unauthorized**
   - 检查JWT Token是否有效（外部JWT使用RS256签名）
   - 确认用户在数据库中存在（支持external_user_id查找）
   - 验证Token格式正确
   - 确保使用rbac_middleware而非auth_middleware

2. **403 Forbidden** 
   - 检查用户角色分配（rf_sjz等用户自动分配superadmin）
   - 确认角色拥有所需权限
   - 清除权限缓存重试
   - 检查权限框架策略是否正确注册

3. **422 Unprocessable Entity**
   - 检查API参数格式
   - 确认依赖注入配置正确
   - 验证装饰器使用方式

4. **权限框架初始化失败**
   - 检查策略注册是否成功
   - 确认RBAC中间件正确传递
   - 查看权限引擎状态日志

#### 调试命令

```bash
# 检查数据库健康状态
curl http://localhost:5050/api/database/health

# 检查数据库连接状态（需要管理员权限）
curl -H "Authorization: Bearer <token>" \
     http://localhost:5050/api/database/connections

# 检查用户权限
curl -H "Authorization: Bearer <token>" \
     http://localhost:5050/api/rbac/users/<user_id>/permissions

# 测试权限接口
curl -H "Authorization: Bearer <token>" \
     http://localhost:5050/api/rbac/roles

# 检查权限框架状态
curl -H "Authorization: Bearer <token>" \
     http://localhost:5050/api/permission-framework/status

# 测试外部JWT认证
curl -H "Authorization: Bearer <jwt_token>" \
     http://localhost:5050/api/data/

# 查看系统日志
tail -f server.log

# 杀死端口占用进程
lsof -ti:5050 | xargs kill -9
```

## 重要开发原则

### 代码规范
- 遵循现有的代码风格和模式
- 使用现有的库和工具
- 遵循安全最佳实践
- 永远不要将密钥和凭据提交到仓库

### 开发提醒
按照要求执行任务，不多不少。
除非绝对必要，否则永远不要创建文件。
总是优先编辑现有文件而不是创建新文件。
除非用户明确要求，否则永远不要主动创建文档文件（*.md）或README文件。