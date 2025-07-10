# Yuxi-Know 项目开发指南

## 项目概述
语析(Yuxi-Know)是一个基于大模型的知识库与知识图谱问答系统，结合了RAG知识库与知识图谱技术，基于FastAPI + Vue.js + Neo4j构建。

## 项目架构
- **后端**: FastAPI (Python) - 位于 `server/` 目录
- **前端**: Vue.js - 通过Docker部署
- **数据库**: 
  - Neo4j (图数据库)
  - Milvus (向量数据库)
  - PostgreSQL (关系数据库)
  - Redis (缓存)
  - MinIO (对象存储)

## 开发环境设置

### 必需配置
1. 创建 `src/.env` 文件，参考 `src/.env.template`
2. 必需的API密钥：
   ```
   SILICONFLOW_API_KEY=your_key_here
   ```

### 可选配置
```
OPENAI_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here
ZHIPUAI_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here  # 联网搜索功能
```

## 启动项目

### 开发环境
```bash
docker compose up --build
```

### 后台运行
```bash
docker compose up --build -d
```

### 查看日志
```bash
docker logs api-dev -f
```

### 关闭服务
```bash
docker compose down
```

## 服务端口
- 前端: http://localhost:5173
- 后端API: http://localhost:5050
- Neo4j: http://localhost:7474 (neo4j/0123456789)
- MinIO: http://localhost:9000
- Milvus: http://localhost:19530

## 项目结构

### 后端 (server/)
- `main.py` - FastAPI应用入口
- `routers/` - API路由
- `auth/` - 认证和权限管理
- `models/` - 数据模型
- `utils/` - 工具函数

### 核心模块 (src/)
- `core/` - 核心功能(图谱适配器、索引等)
- `database/` - 数据库适配器和管理器
- `models/` - AI模型适配器
- `plugins/` - 插件(OCR等)
- `services/` - 业务服务

## 开发工作流

### 添加新功能
1. 在 `server/routers/` 添加新的路由
2. 在 `server/models/` 定义数据模型
3. 在 `src/database/repositories/` 实现数据访问层
4. 在 `src/services/` 实现业务逻辑

### 测试
```bash
# 检查容器状态
docker ps

# 重启特定服务
docker restart api-dev

# 检查Milvus状态
docker compose up milvus -d
```

### 调试
- 后端日志: `docker logs api-dev -f`
- 数据库连接: 检查 `src/database/connection_manager.py`
- 权限问题: 查看 `server/auth/` 目录

## 模型配置

### 支持的模型供应商
- SiliconFlow (默认)
- OpenAI
- DeepSeek
- 智谱清言
- 阿里云
- 豆包等

### 添加新模型
在 `src/static/models.yaml` 中添加配置

### 本地模型
使用vllm或ollama部署本地模型，参考 `scripts/vllm/run.sh`

## 数据库操作

### Neo4j图谱
- 访问: http://localhost:7474
- 账户: neo4j/0123456789
- 数据格式: `{"h": "实体1", "t": "实体2", "r": "关系"}`

### Milvus向量数据库
- 用于存储文档向量
- 支持相似度搜索

## 常见问题

### 内存不足
```bash
docker compose up milvus -d
docker restart api-dev
```

### 权限问题
检查 `server/auth/permission_framework/` 权限配置

### 模型不可用
1. 检查API密钥配置
2. 查看 `src/static/models.yaml` 配置
3. 确认网络连接

## 文件上传支持
- PDF, TXT, Markdown, Docx
- 支持URL添加文件
- 支持OCR处理(MinerU, PP-Structure-V3)

## 部署注意事项
- 确保Docker和nvidia-container-toolkit已安装
- 配置环境变量在 `src/.env`
- 生产环境建议使用稳定版本分支

## 贡献指南
1. Fork项目
2. 创建功能分支
3. 提交Pull Request
4. 确保代码通过测试

## 相关文档
- [官方GitHub](https://github.com/xerrors/Yuxi-Know)
- [MinerU文档](https://github.com/opendatalab/MinerU)
- [FastAPI文档](https://fastapi.tiangolo.com/)
- [Neo4j文档](https://neo4j.com/docs/)