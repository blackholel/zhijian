# 数据库架构重构迁移指南

## 概述

本项目已完成数据库架构的统一重构，将原有分散的数据库管理代码整合到一个统一的、可扩展的架构中。

## 新架构特点

### 1. 统一配置管理
- 所有数据库配置集中在 `src/static/database.yaml`
- 支持多环境配置（development, test, production）
- 自动环境变量解析

### 2. 适配器模式
- 每种数据库类型都有独立的适配器
- 统一的接口规范
- 支持连接池、健康检查、重试机制

### 3. 仓储模式
- 数据访问层抽象
- 支持缓存、事务、批量操作
- 类型安全的数据操作接口

### 4. 连接管理
- 统一的连接生命周期管理
- 自动健康监控
- 连接池复用

## 新架构组件

```
src/database/
├── __init__.py              # 模块入口
├── base.py                  # 基础抽象类
├── config_manager.py        # 配置管理器
├── connection_manager.py    # 连接管理器
├── manager.py              # 统一数据库管理器
├── adapters/               # 数据库适配器
│   ├── postgresql.py       # PostgreSQL适配器
│   ├── neo4j.py           # Neo4j适配器
│   ├── redis.py           # Redis适配器
│   ├── milvus.py          # Milvus适配器
│   └── minio.py           # MinIO适配器
└── repositories/          # 数据仓储层
    ├── base.py            # 仓储基类
    ├── user_repository.py  # 用户仓储
    ├── knowledge_repository.py # 知识库仓储
    ├── graph_repository.py # 图数据仓储
    └── file_repository.py  # 文件仓储
```

## 使用方法

### 1. 基本用法

```python
from src.database.manager import UnifiedDatabaseManager

# 创建数据库管理器
async with UnifiedDatabaseManager() as db_manager:
    # 获取适配器
    postgres_adapter = await db_manager.get_postgresql_adapter('server_db')
    neo4j_adapter = await db_manager.get_neo4j_adapter()
    
    # 获取仓储
    user_repo = db_manager.get_user_repository()
    
    # 执行操作
    user = await user_repo.get_by_id('user_123')
```

### 2. FastAPI依赖注入

```python
from src.database.manager import get_database_manager_dependency, get_user_repository_dependency
from fastapi import Depends

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    user_repo: UserRepository = Depends(get_user_repository_dependency)
):
    return await user_repo.get_by_id(user_id)
```

### 3. 直接使用适配器

```python
from src.database.manager import get_database_manager

db_manager = get_database_manager()
await db_manager.initialize()

# PostgreSQL操作
async with await db_manager.get_postgresql_adapter().get_session_context() as session:
    result = session.query(User).all()

# Neo4j操作
neo4j_adapter = await db_manager.get_neo4j_adapter()
results = await neo4j_adapter.execute_cypher("MATCH (n) RETURN n LIMIT 10")

# Redis操作
redis_adapter = await db_manager.get_redis_adapter()
await redis_adapter.set("key", "value", ttl=3600)
```

## 迁移步骤

### 1. 更新导入语句

**原来：**
```python
from server.db_manager import db_manager, get_session
from src.core.graphbase import GraphDatabase
```

**现在：**
```python
from src.database.manager import get_database_manager_dependency
from src.database.repositories import UserRepository
```

### 2. 更新FastAPI依赖

**原来：**
```python
from server.db_manager import get_db

@router.get("/users")
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

**现在：**
```python
from src.database.manager import get_user_repository_dependency

@router.get("/users")
async def get_users(user_repo: UserRepository = Depends(get_user_repository_dependency)):
    return await user_repo.find_all()
```

### 3. 更新配置访问

**原来：**
```python
from src import config
db_config = config.get_database_config('server_db')
```

**现在：**
```python
from src.database.manager import get_database_manager
db_manager = get_database_manager()
db_config = db_manager.get_database_config('server_db')
```

## 兼容性

为保证平滑迁移，提供了兼容性模块：

```python
# 兼容性导入（会有警告）
from server.db_manager_compat import db_manager, get_session
```

## 新功能

### 1. 统一健康检查

```python
# 获取所有数据库健康状态
health = await db_manager.health_check()
```

### 2. 连接监控

```python
# 获取连接状态摘要
summary = db_manager.connection_manager.get_connection_summary()
```

### 3. 缓存支持

```python
# 仓储自动缓存
user_repo = db_manager.get_user_repository()
user_repo.enable_cache(ttl=1800)  # 30分钟缓存
```

### 4. 批量操作

```python
# 批量创建用户
users = [UserInfo(...), UserInfo(...)]
created_users = await user_repo.batch_create(users)
```

## API接口

新增数据库管理API：

- `GET /api/database/health` - 数据库健康检查
- `GET /api/database/connections` - 连接状态
- `GET /api/database/adapters` - 适配器信息
- `POST /api/database/reconnect` - 重连数据库
- `GET /api/database/config` - 配置信息

## 测试

运行测试脚本验证新架构：

```bash
python test_new_architecture.py
```

## 注意事项

1. **异步操作**：新架构全面支持异步操作，建议使用async/await
2. **资源管理**：使用async context manager确保资源正确释放
3. **错误处理**：适配器会自动重试连接失败，仓储会fallback到内存缓存
4. **性能**：连接池复用提升性能，缓存减少数据库访问

## 故障排除

### 1. 连接失败
检查 `src/static/database.yaml` 配置是否正确，确保所有必需的环境变量已设置。

### 2. 导入错误
确保新的数据库模块路径正确，清理Python缓存：
```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +
```

### 3. 适配器不可用
某些适配器需要额外的依赖包：
- Neo4j: `pip install neo4j`
- Redis: `pip install redis`
- Milvus: `pip install pymilvus`
- MinIO: `pip install minio`

## 性能优化建议

1. **连接池**：根据负载调整连接池大小
2. **缓存**：为高频访问的数据启用缓存
3. **批量操作**：对大量数据使用批量操作接口
4. **健康监控**：监控数据库健康状态，及时发现问题

## 未来扩展

新架构支持：
- 添加新的数据库类型适配器
- 扩展仓储功能
- 集成更多监控指标
- 支持分布式缓存
- 数据库分片