
# 项目目录结构 (Project Overview)

Yuxi-Know 是一个基于大模型的智能知识库与知识图谱智能体开发平台，融合了 RAG 技术与知识图谱技术，基于 LangGraph v1 + Vue.js + FastAPI + LightRAG 架构构建。

项目支持两种开发方式：
- Docker Compose（全栈容器化，默认/推荐）
- 本地开发（前后端在宿主机运行；依赖服务由宿主机或外部环境提供）

## 开发准则

Avoid over-engineering. Only make changes that are directly requested or clearly necessary. Keep solutions simple and focused.

Don't add features, refactor code, or make "improvements" beyond what was asked. A bug fix doesn't need surrounding code cleaned up. A simple feature doesn't need extra configurability.

Don't add error handling, fallbacks, or validation for scenarios that can't happen. Trust internal code and framework guarantees. Only validate at system boundaries (user input, external APIs). Don't use backwards-compatibility shims when you can just change the code.

Don't create helpers, utilities, or abstractions for one-time operations. Don't design for hypothetical future requirements. The right amount of complexity is the minimum needed for the current task. Reuse existing abstractions where possible and follow the DRY principle.

## 开发与调试工作流 (Development & Debugging Workflow)

### 方式 1：Docker Compose（全栈）

- 启动：`docker compose up -d --build`
- 看日志：`docker logs api-dev --tail 100` / `docker logs web-dev --tail 100`
- 核心原则：`api-dev` / `web-dev` 都是热重载，本地改代码一般无需重启容器

### 方式 2：本地开发（不使用 Docker 运行前后端）

前提：Postgres / Milvus / Neo4j / Minio 等依赖服务已在本机或外部环境稳定运行，并在根目录 `.env` 中配置为可访问地址（建议使用 `127.0.0.1` 而非 `localhost`）。

- 启动后端：`uv run uvicorn server.main:app --reload --host 127.0.0.1 --port 5050`
- 启动前端：`cd web && VITE_API_URL=http://127.0.0.1:5050 corepack pnpm dev -- --host 127.0.0.1 --port 5173`

### 前端开发规范

- API 接口规范：所有的 API 接口都应该定义在 web/src/apis 下面
- Icon 应该从 @ant-design/icons-vue 或者 lucide-vue-next （推荐，但是需要注意尺寸）
- Vue 中的样式使用 less，非必要情况必须使用[base.css](web/src/assets/css/base.css) 中的颜色变量。
- UI风格要简洁，同时要保持一致性，不要悬停位移，不要过度使用阴影以及渐变色。
- 本地启动前端请使用 `corepack pnpm`（不要用 `npm`）。


### 后端开发规范

```bash
# 代码检查和格式化
make lint          # 检查代码规范
make format        # 格式化代码

# 本地执行
uv run python test/your_script.py  # 放在 test 文件夹

# 容器内执行（使用 Docker Compose 开发时）
docker compose exec api uv run python test/your_script.py
```

注意：

- Python 代码要符合 Python 的规范，符合 pythonic 风格
- 尽量使用较新的语法，避免使用旧版本的语法（版本兼容到 3.12+）

**其他**：

- 首次启动初始化超级管理员：UI 会提示创建；也可以直接调用 `POST /api/auth/initialize`（配合 `GET /api/auth/check-first-run` 判断是否需要初始化）
- 如果需要新建说明文档（仅开发者可见，非必要不创建），则保存在 `docs/vibe` 文件夹下面
- 代码更新后要检查文档部分是否有需要更新的地方，文档的目录定义在 `docs/.vitepress/config.mts` 中。文档应该更新最新版（`docs/latest`）
