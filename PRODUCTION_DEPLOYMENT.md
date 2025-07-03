# 生产环境部署指南

## 概述

本指南介绍如何在生产环境中部署 Yuxi-Know 系统，包括数据库配置、环境变量设置和性能优化。

## 系统架构

生产环境使用以下数据库架构：

- **PostgreSQL**: 服务器主数据库和LightRAG知识库
- **Neo4j**: 知识图谱存储
- **Milvus**: 向量数据库
- **MinIO**: 对象存储

## 部署步骤

### 1. 准备生产环境配置

#### 复制配置模板
```bash
# 复制数据库配置模板
cp src/static/database.production.template.yaml src/static/database.production.yaml

# 复制环境变量模板
cp .env.production.template .env.production
```

#### 编辑数据库配置
编辑 `src/static/database.production.yaml`，将模板中的占位符替换为实际值。

#### 编辑环境变量
编辑 `.env.production`，填入所有必要的环境变量值。

### 2. 数据库准备

#### PostgreSQL 主数据库
```sql
-- 创建主数据库
CREATE DATABASE yuxi_prod;
CREATE USER yuxi_user WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE yuxi_prod TO yuxi_user;

-- 安装必要扩展
\c yuxi_prod;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

#### PostgreSQL LightRAG数据库
```sql
-- 创建LightRAG数据库
CREATE DATABASE lightrag_prod;
CREATE USER lightrag_user WITH PASSWORD 'your-lightrag-password';
GRANT ALL PRIVILEGES ON DATABASE lightrag_prod TO lightrag_user;

-- 安装扩展
\c lightrag_prod;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
```

#### Neo4j图数据库
```cypher
-- 创建用户和设置密码
CREATE USER neo4j_prod SET PASSWORD 'your-neo4j-password';
GRANT ROLE admin TO neo4j_prod;
```

### 3. 应用配置

#### 设置环境变量
```bash
# 设置生产环境
export ENVIRONMENT=production

# 加载生产环境配置
source .env.production
```

#### 修改应用配置
确保应用使用生产环境的数据库配置：

```python
# 在应用启动时
from src.config import config
config.database.set_environment('production')
```

### 4. 启动服务

#### 使用Docker Compose（推荐）
```bash
# 生产环境启动
docker-compose -f docker-compose.prod.yml up -d
```

#### 手动启动
```bash
# 启动API服务器
python server/main.py

# 启动Web前端
cd web && npm run build && npm run start
```

### 5. 数据库迁移

如果从开发环境迁移到生产环境：

```bash
# 备份开发环境数据
pg_dump yuxi_dev > yuxi_dev_backup.sql
pg_dump lightrag_dev > lightrag_dev_backup.sql

# 恢复到生产环境
psql yuxi_prod < yuxi_dev_backup.sql
psql lightrag_prod < lightrag_dev_backup.sql
```

## 配置选项说明

### 数据库连接池配置

- **pool_size**: 基础连接池大小
- **max_overflow**: 最大溢出连接数
- **connect_timeout**: 连接超时时间

推荐生产环境配置：
- 主数据库：pool_size=20, max_overflow=50
- LightRAG数据库：pool_size=50, max_overflow=100

### 性能优化配置

#### PostgreSQL优化
```yaml
postgres:
  statement_timeout: 30000      # 30秒语句超时
  idle_in_transaction_session_timeout: 600000  # 10分钟事务空闲超时
```

#### Neo4j优化
```yaml
neo4j:
  max_connection_pool_size: 100 # 连接池大小
  connection_timeout: 30        # 连接超时
```

#### Milvus优化
```yaml
milvus:
  timeout: 30                   # 操作超时
  batch_size: 1000             # 批量操作大小
```

## 监控和日志

### 启用监控
```yaml
monitoring:
  enabled: true
  metrics_endpoint: "/metrics"
```

### 日志配置
```yaml
logging:
  level: WARNING                # 生产环境使用WARNING级别
  log_queries: false           # 不记录查询日志
  log_slow_queries: true       # 记录慢查询
  slow_query_threshold: 2.0    # 2秒慢查询阈值
```

## 安全最佳实践

### 1. 密码安全
- 使用强密码（至少16个字符，包含大小写字母、数字和特殊字符）
- 定期轮换密码
- 不在代码或配置文件中硬编码密码

### 2. 网络安全
- 启用SSL/TLS加密连接
- 配置防火墙限制数据库访问
- 使用VPN或私有网络

### 3. 访问控制
- 为每个数据库创建专用用户
- 授予最小必要权限
- 启用审计日志

### 4. 备份策略
```bash
# 设置定时备份
0 2 * * * pg_dump yuxi_prod > /backup/yuxi_$(date +\%Y\%m\%d).sql
0 3 * * * pg_dump lightrag_prod > /backup/lightrag_$(date +\%Y\%m\%d).sql
```

## 故障排除

### 数据库连接问题
1. 检查网络连通性
2. 验证用户名密码
3. 确认数据库服务运行状态
4. 检查防火墙设置

### 性能问题
1. 监控连接池使用情况
2. 检查慢查询日志
3. 分析数据库统计信息
4. 优化查询和索引

### 配置问题
```bash
# 验证配置文件
python -c "from src.config import config; print(config.database.get_connection_info('server_db'))"

# 测试数据库连接
python -c "from server.db_manager import db_manager; print(db_manager.health_check())"
```

## 维护任务

### 定期维护
- 每周运行数据库统计更新
- 每月检查和清理日志文件
- 每季度审查性能指标
- 每年更新密码和证书

### 监控指标
- 数据库连接数
- 查询响应时间
- 磁盘使用情况
- 内存使用情况
- CPU利用率

## 联系支持

如遇到部署问题，请：
1. 查看应用日志
2. 检查数据库日志
3. 验证配置文件
4. 提供错误信息和环境详情