# CLAUDE.md

本文件为Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。

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
- **Neo4j浏览器**: http://localhost:7474
- **MinIO控制台**: http://localhost:9001 (admin/minioadmin)

## 架构概览

### 核心组件
- **server/**: FastAPI后端，提供认证、对话和图谱API
- **src/**: 核心应用逻辑，包括代理、模型和插件
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
- 认证中间件位于 `server/utils/auth_middleware.py`
- 数据库模型位于 `server/models/`
- API路由位于 `server/routers/`

### 前端组件开发
- Vue.js 3组合式API
- Pinia状态管理位于 `web/src/stores/`
- 组件组织位于 `web/src/components/`
- API客户端位于 `web/src/apis/`

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

## 前端开发命令

### Web目录操作
```bash
# 进入前端目录
cd web

# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev

# 构建生产版本
pnpm build

# 类型检查
pnpm type-check

# 代码检查
pnpm lint
```

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