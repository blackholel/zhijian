# Yuxi-Know 知识管理系统

## 项目概述

Yuxi-Know 是一个基于 FastAPI 和 LightRAG 构建的企业级知识管理系统，集成了先进的 AI 技术和统一的数据库管理架构。系统提供全面的权限管理、知识库管理和多数据库支持，旨在为企业提供智能化的知识管理解决方案。

## 核心架构

### 技术栈
- **后端框架**: FastAPI + Uvicorn
- **数据库**: PostgreSQL (主数据库) + Neo4j (图数据库) + Milvus (向量数据库) + Redis (缓存) + MinIO (对象存储)
- **AI 集成**: LightRAG + 多种 LLM 模型 (OpenAI、DeepSeek、Zhipu AI 等)
- **认证授权**: JWT + RBAC (基于角色的访问控制)
- **ORM**: SQLAlchemy (异步)

### 项目结构
```
src/
├── main.py                    # 应用程序入口
├── auth/                      # 认证授权模块
│   ├── models/               # 用户、角色、权限模型
│   ├── services/             # 认证服务
│   └── middlewares/          # 认证中间件
├── core/                     # 核心业务逻辑
│   ├── lightrag/            # LightRAG 知识图谱
│   └── graph/               # 图数据库适配器
├── database/                 # 统一数据库管理
│   ├── manager.py           # 数据库管理器
│   ├── adapters/            # 数据库适配器
│   └── repositories/        # 数据访问层
├── knowledge_base/           # 知识库管理
│   ├── models/              # 知识库模型
│   └── services/            # 知识库服务
├── models/                   # AI 模型配置
├── routers/                  # API 路由
├── services/                 # 业务服务
└── utils/                    # 工具函数
```

## 权限管理系统

### 1. 认证架构

#### 多重认证支持
- **JWT 令牌认证**: 内部用户认证，支持 24 小时有效期
- **外部 JWT 处理**: 支持第三方系统集成
- **会话管理**: Redis 缓存会话，30 分钟 TTL
- **密码安全**: SHA-256 加盐哈希存储

#### 中间件层
- **认证中间件** (`auth_middleware.py`): 基础 JWT 令牌验证
- **RBAC 中间件** (`rbac_middleware.py`): 基于角色的访问控制
- **外部 JWT 处理器** (`external_jwt_processor.py`): 第三方系统集成

### 2. RBAC 权限模型

#### 核心实体
```python
# 用户模型
class User:
    id: UUID
    external_user_id: str  # 外部系统用户ID
    username: str
    password_hash: str
    roles: List[Role]

# 角色模型
class Role:
    id: UUID
    name: str
    is_system: bool  # 系统角色标识
    permissions: List[Permission]

# 权限模型
class Permission:
    id: UUID
    resource_type: str  # 资源类型
    action: str        # 操作类型
    resource_id: str   # 特定资源ID
```

#### 系统角色层次
1. **超级管理员** (`superadmin`): 拥有所有权限
2. **管理员** (`admin`): 系统管理权限
3. **高级用户** (`power_user`): 扩展功能权限
4. **普通用户** (`user`): 基础功能权限

### 3. 权限框架

#### 资源类型
- `knowledge_base`: 知识库资源
- `chat_session`: 对话会话
- `graph_data`: 图数据
- `file_system`: 文件系统
- `user_profile`: 用户配置
- `system_config`: 系统配置

#### 权限策略 (优先级顺序)
1. **SuperAdminStrategy**: 超级管理员全权限
2. **OwnershipStrategy**: 资源所有者权限
3. **PublicResourceStrategy**: 公开资源访问
4. **SystemPermissionStrategy**: 系统级权限检查
5. **ResourcePermissionStrategy**: 资源特定权限
6. **InheritanceStrategy**: 权限继承策略
7. **DenyAllStrategy**: 默认拒绝策略

#### 权限装饰器
```python
@require_permission("knowledge_base:read")
@require_kb_permission("read", kb_id)
@require_system_permission("system:config")
@require_any_permission(["kb:read", "kb:write"])
@require_all_permissions(["kb:read", "kb:admin"])
```

### 4. 预定义权限 (88 个)

#### 用户管理权限
- `user:read`, `user:create`, `user:update`, `user:delete`
- `user:grant_role`, `user:revoke_role`

#### 知识库权限
- `kb:read`, `kb:create`, `kb:update`, `kb:delete`
- `kb:upload`, `kb:download`, `kb:query`, `kb:share`
- `kb:manage_users`, `kb:view_logs`
- `kb:read_specific`, `kb:write_specific`, `kb:admin_specific`

#### 系统权限
- `system:read`, `system:config`, `system:restart`
- `system:logs`, `system:backup`

#### 文件权限
- `file:read`, `file:upload`, `file:download`, `file:delete`

### 5. 审计和监控

#### 操作日志
- **权限检查日志**: 记录所有权限验证
- **用户操作日志**: 追踪用户行为
- **IP 地址追踪**: 请求来源记录
- **性能监控**: 权限检查性能指标

#### 缓存管理
- **权限缓存**: 1 小时 TTL，Redis 存储
- **会话缓存**: 30 分钟 TTL
- **自动失效**: 权限变更时自动清理缓存

## 知识库管理系统

### 1. 知识库架构

#### 数据模型层次
```
知识库 (KnowledgeDatabase)
├── 权限 (KnowledgeDatabasePermission)
├── 文件 (KnowledgeFile)
│   ├── 处理状态
│   ├── 存储元数据
│   └── 节点 (KnowledgeNode)
│       ├── 向量嵌入
│       ├── 字符位置
│       └── 关系映射
└── 模型配置 (每个知识库独立配置)
```

#### 核心模型
- **KnowledgeDatabase**: 知识库主实体，包含元数据、权限和所有权
- **KnowledgeFile**: 文档文件管理，支持处理状态跟踪
- **KnowledgeNode**: 文本块分段，包含嵌入向量和元数据
- **KnowledgeDatabasePermission**: 细粒度权限系统

### 2. 存储后端

#### 多存储架构
- **PostgreSQL**: 主要结构化数据存储
- **Milvus**: 向量数据库，语义搜索
- **Neo4j**: 图数据库，关系映射
- **Redis**: 缓存和实时状态管理
- **MinIO**: 对象存储，文件上传

#### LightRAG 集成
- 核心检索引擎，支持多模态查询
- 自动知识图谱构建
- 实体和关系抽取
- 混合检索策略

### 3. 文档处理流程

#### 上传和存储
1. **文件上传**: 支持本地和 MinIO 对象存储
2. **格式检测**: 自动识别文件类型
3. **进度跟踪**: 实时状态更新
4. **批量处理**: 支持批量上传

#### 处理管道
1. **文本提取**: OCR 支持图像，PDF 解析
2. **内容分块**: 智能文本分段，重叠控制
3. **向量化**: 多种嵌入模型支持
4. **知识图谱**: 自动实体关系抽取
5. **存储**: 多后端持久化

#### 支持格式
- **文档**: PDF, DOC/DOCX, TXT, MD, HTML, JSON, CSV
- **图像**: JPG, PNG, BMP, TIFF (OCR 支持)
- **高级 OCR**: MineRU OCR, PaddleX OCR, ONNX Rapid OCR

### 4. 搜索和检索

#### 多模态搜索
- **语义搜索**: 使用 Milvus 向量相似性
- **图遍历**: 通过 Neo4j 基于关系的查询
- **全文搜索**: PostgreSQL 文本搜索
- **混合 RAG**: LightRAG 多策略组合查询

#### 搜索优化
- **自动索引**: 文档变更时实时更新
- **智能分块**: 保持元数据的分块策略
- **多维相似性**: 支持多维度相似性搜索
- **重排序**: 搜索结果优化

### 5. 知识库 API

#### 核心 REST API
```python
# 知识库管理
GET    /api/knowledge/databases              # 获取知识库列表
POST   /api/knowledge/databases              # 创建知识库
GET    /api/knowledge/databases/{kb_id}      # 获取知识库详情
PUT    /api/knowledge/databases/{kb_id}      # 更新知识库
DELETE /api/knowledge/databases/{kb_id}      # 删除知识库

# 文档管理
POST   /api/knowledge/databases/{kb_id}/upload    # 上传文档
GET    /api/knowledge/databases/{kb_id}/files     # 获取文件列表
GET    /api/knowledge/files/{file_id}             # 获取文件详情
GET    /api/knowledge/files/{file_id}/download    # 下载文件
DELETE /api/knowledge/files/{file_id}             # 删除文件

# 查询和搜索
POST   /api/knowledge/databases/{kb_id}/query     # 查询知识库

# 权限管理
POST   /api/knowledge/databases/{kb_id}/permissions        # 授权
DELETE /api/knowledge/databases/{kb_id}/permissions/{user_id}  # 撤销权限

# 状态监控
GET    /api/knowledge/databases/{kb_id}/files/status        # 文件处理状态
GET    /api/knowledge/databases/{kb_id}/files/status/stream # 实时状态流
GET    /api/knowledge/databases/{kb_id}/statistics          # 统计信息
```

### 6. 高级功能

#### 实时处理
- **异步文档处理**: 大文件后台处理
- **状态流**: Server-Sent Events 实时更新
- **任务管理**: 后台任务调度和监控

#### 模型配置
- **个性化配置**: 每个知识库独立的 LLM 配置
- **多提供商支持**: OpenAI、本地模型等
- **动态切换**: 运行时模型配置切换

## 统一数据库管理

### 1. 数据库管理架构

#### 核心组件
- **统一数据库管理器** (`manager.py`): 所有数据库操作的中央协调器
- **连接管理器** (`connection_manager.py`): 连接池和重试逻辑
- **数据库适配器** (`adapters/`): 各数据库的专用适配器
- **仓储模式** (`repositories/`): 统一的数据访问接口

#### 支持的数据库
```yaml
# 主数据库配置
postgresql:
  host: localhost
  port: 5432
  database: yuxi_know
  username: postgres
  password: ${POSTGRES_PASSWORD}
  pool_size: 20

# 图数据库
neo4j:
  uri: bolt://localhost:7687
  username: neo4j
  password: ${NEO4J_PASSWORD}
  pool_size: 10

# 向量数据库
milvus:
  host: localhost
  port: 19530
  database: yuxi_know_vectors
  pool_size: 10

# 缓存数据库
redis:
  host: localhost
  port: 6379
  password: ${REDIS_PASSWORD}
  db: 0
  pool_size: 20

# 对象存储
minio:
  endpoint: localhost:9000
  access_key: ${MINIO_ACCESS_KEY}
  secret_key: ${MINIO_SECRET_KEY}
  bucket_name: yuxi-know-files
```

### 2. 连接管理

#### 连接池配置
- **PostgreSQL**: 20 个连接池
- **Neo4j**: 10 个连接池
- **Milvus**: 10 个连接池
- **Redis**: 20 个连接池
- **MinIO**: 按需连接

#### 高可用特性
- **健康检查**: 持续监控所有数据库连接
- **自动重连**: 指数退避重试机制
- **故障转移**: 自动切换到备用连接
- **连接复用**: 高效的连接池管理

### 3. 仓储模式

#### 基础仓储
```python
class BaseRepository(Generic[T]):
    async def create(self, entity: T) -> T
    async def get_by_id(self, id: UUID) -> Optional[T]
    async def update(self, entity: T) -> T
    async def delete(self, id: UUID) -> bool
    async def list(self, **filters) -> List[T]
```

#### 专用仓储
- **UserRepository**: 用户数据操作，集成缓存
- **KnowledgeRepository**: 知识库数据操作
- **GraphRepository**: Neo4j 图操作
- **FileRepository**: MinIO 文件操作

### 4. 缓存策略

#### 多层缓存
- **内存缓存**: 应用程序级缓存
- **Redis 缓存**: 分布式缓存
- **数据库缓存**: 查询结果缓存

#### 缓存管理
- **自动失效**: 数据变更时自动清理
- **TTL 控制**: 可配置的过期时间
- **缓存穿透**: 防护机制
- **缓存雪崩**: 预防策略

### 5. 事务管理

#### 跨数据库事务
```python
async def knowledge_base_transaction():
    async with transaction_manager.begin():
        # PostgreSQL 操作
        await postgres_repo.create_knowledge_base(kb_data)
        
        # Milvus 操作
        await milvus_repo.create_collection(collection_name)
        
        # Neo4j 操作
        await neo4j_repo.create_graph_node(node_data)
        
        # Redis 缓存
        await redis_repo.set_cache(cache_key, cache_data)
```

#### 事务特性
- **ACID 保证**: 原子性、一致性、隔离性、持久性
- **补偿机制**: 失败时自动回滚
- **分布式事务**: 跨多个数据库的一致性
- **异步支持**: 全异步事务处理

### 6. 监控和运维

#### 性能监控
- **连接池状态**: 实时监控连接使用情况
- **查询性能**: 慢查询检测和优化
- **缓存命中率**: 缓存效率监控
- **错误率追踪**: 数据库错误监控

#### 运维工具
- **健康检查端点**: `/health/database`
- **性能指标**: Prometheus 集成
- **日志记录**: 结构化数据库日志
- **备份恢复**: 自动化备份策略

## 配置和部署

### 1. 环境配置

#### 开发环境
```bash
# 设置环境变量
export POSTGRES_PASSWORD=your_password
export NEO4J_PASSWORD=your_password
export REDIS_PASSWORD=your_password
export MINIO_ACCESS_KEY=your_access_key
export MINIO_SECRET_KEY=your_secret_key
export JWT_SECRET_KEY=your_jwt_secret

# 启动应用
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

#### 生产环境
```bash
# 使用生产配置
cp src/static/database.production.template.yaml src/static/database.yaml

# 配置生产环境变量
source .env.production

# 启动应用
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 2. 数据库初始化

#### 自动初始化
```python
# 运行数据库初始化
python -m src.database.init_tables

# 创建超级管理员用户
python -m src.auth.create_admin_user
```

#### 手动初始化
```bash
# PostgreSQL 表创建
psql -U postgres -d yuxi_know -f migrations/001_initial.sql

# Neo4j 约束创建
cypher-shell -u neo4j -p password -f migrations/neo4j_constraints.cypher
```

### 3. 健康检查

#### 系统健康检查
```bash
# 检查所有数据库连接
curl http://localhost:8000/health/database

# 检查权限系统
curl http://localhost:8000/health/auth

# 检查知识库系统
curl http://localhost:8000/health/knowledge
```

### 4. 性能优化

#### 数据库优化
- **索引优化**: 为频繁查询的字段创建索引
- **连接池调优**: 根据负载调整连接池大小
- **缓存策略**: 合理配置缓存TTL和清理策略
- **分页查询**: 大数据量查询使用分页

#### 系统优化
- **异步处理**: 使用异步I/O提升并发性能
- **批量操作**: 减少数据库往返次数
- **资源监控**: 监控内存和CPU使用情况
- **日志优化**: 合理配置日志级别

## 最佳实践

### 1. 安全最佳实践

#### 认证安全
- 使用强JWT密钥，定期轮换
- 实施适当的令牌过期时间
- 启用HTTPS，加密传输数据
- 实施防暴力破解机制

#### 权限安全
- 遵循最小权限原则
- 定期审计用户权限
- 记录敏感操作日志
- 实施权限变更审批流程

### 2. 性能最佳实践

#### 数据库性能
- 使用连接池，避免频繁连接
- 合理使用缓存，减少数据库查询
- 优化查询语句，避免N+1问题
- 定期维护数据库索引

#### 应用性能
- 使用异步编程模型
- 实施适当的缓存策略
- 监控应用性能指标
- 优化内存使用

### 3. 运维最佳实践

#### 监控和告警
- 设置数据库连接监控
- 配置性能指标告警
- 实施日志聚合和分析
- 定期进行性能测试

#### 备份和恢复
- 定期备份所有数据库
- 测试备份恢复流程
- 实施版本控制和回滚
- 制定灾难恢复计划

## 常见问题和解决方案

### 1. 数据库连接问题

#### 问题: 数据库连接超时
```python
# 解决方案: 增加连接超时时间
postgresql:
  connect_timeout: 30
  pool_recycle: 3600
```

#### 问题: 连接池耗尽
```python
# 解决方案: 调整连接池大小
postgresql:
  pool_size: 30
  max_overflow: 20
```

### 2. 权限问题

#### 问题: 权限检查失败
```python
# 解决方案: 检查权限缓存
await redis_repo.delete_cache(f"user_permissions:{user_id}")
```

#### 问题: 角色权限不生效
```python
# 解决方案: 刷新权限框架
await permission_manager.refresh_permissions()
```

### 3. 知识库问题

#### 问题: 文档处理失败
```python
# 解决方案: 检查文档格式和大小
if file_size > MAX_FILE_SIZE:
    raise HTTPException(400, "文件过大")
```

#### 问题: 搜索结果不准确
```python
# 解决方案: 重新构建向量索引
await milvus_repo.rebuild_index(collection_name)
```

## 更新日志

### 版本 1.0.0 (当前版本)
- 实现统一数据库管理架构
- 完成RBAC权限系统
- 集成LightRAG知识管理
- 支持多种AI模型
- 实现文档处理流程
- 添加实时状态监控

### 未来计划
- 添加更多AI模型支持
- 实现分布式部署
- 增强监控和告警功能
- 优化性能和扩展性
- 添加更多文档格式支持

## 技术支持

### 联系方式
- 项目地址: https://github.com/your-org/yuxi-know
- 文档地址: https://docs.yuxi-know.com
- 技术支持: support@yuxi-know.com

### 贡献指南
1. Fork 项目仓库
2. 创建功能分支
3. 提交代码变更
4. 发起 Pull Request
5. 通过代码审查
6. 合并到主分支

---

*最后更新: 2024年*