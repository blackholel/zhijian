# 快速开始指南

::: tip 提示
除了此文档网站外，用户还可以在 [Zread](https://zread.ai/xerrors/Yuxi-Know) 或 [DeepWiki](https://deepwiki.com/xerrors/Yuxi-Know) 平台查看自动生成的详细项目文档。
:::


## 快速开始


### 安装步骤

项目采用微服务架构，核心服务无需 GPU 支持。GPU 仅用于可选的 OCR 服务和本地模型推理，可通过环境变量配置外部服务。

#### 1. 获取项目代码

```bash
# 克隆稳定版本
git clone --branch v0.4.1 --depth 1 https://github.com/xerrors/Yuxi-Know.git
cd Yuxi-Know
```

::: warning 版本说明
- `v0.4.1`: 稳定版本
- `main`: 最新开发版本（不稳定，新特性可能会导致新 bug）
:::

#### 2. 项目启动

**方法 1**：使用 init 脚本（推荐）

我们提供了自动化的初始化脚本，可以帮您完成环境配置和 Docker 镜像拉取：

```bash
# Linux/macOS
./scripts/init.sh

# Windows PowerShell
.\scripts\init.ps1
```

脚本会：
- 检查并创建 `.env` 文件
- 提示您输入 `SILICONFLOW_API_KEY`（必需）
- 提示您输入 `TAVILY_API_KEY`（可选，用于搜索服务）
- 自动拉取所有必需的 Docker 镜像

::: tip API Key 获取
- [硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度
- [Tavily](https://app.tavily.com/) 获取搜索服务 API Key（可选）
:::

**方法 2**：手动配置环境变量

复制环境变量模板并编辑：

```bash
cp .env.template .env
```

编辑 `.env` 文件，配置必需的 API 密钥，这里强烈建议先使用硅基流动的 API 和模型（DeepSeek）验证平台的功能无误后，再尝试切换到自己的模型：


<<< @/../.env.template#model_provider{bash 5}


::: tip 免费获取 API Key
[硅基流动](https://cloud.siliconflow.cn/i/Eo5yTHGJ) 注册即送 14 元额度，支持多种开源模型。
:::

#### 3. 启动服务

```bash
# 构建并启动所有服务
docker compose up --build

# 后台运行（推荐）
docker compose up --build -d
```

### 本地联调（仅启动前后端）

如果你只在本机启动前后端进行联调（不使用 Docker Compose 的 `api-dev/web-dev`），可以按以下方式启动：

1) 确保根目录 `.env` 中已配置依赖服务地址（如 `POSTGRES_URI`、`MILVUS_URI`、`NEO4J_URI` 等），这些服务可以是本机或外部服务。

2) 启动后端（默认端口 `5050`）：

```bash
uv run uvicorn server.main:app --reload --host 127.0.0.1 --port 5050
```

3) 启动前端（Vite 通过代理转发 `/api/*` 到后端）：

```bash
cd web
VITE_API_URL=http://127.0.0.1:5050 corepack pnpm dev -- --host
```

::: tip 提示
建议使用 `127.0.0.1` 而不是 `localhost`：在部分 macOS 环境下 `localhost -> ::1(IPv6)` 会导致前端代理出现 `EPIPE/Broken pipe`。
:::

4) 首次启动初始化超级管理员（可选）

首次启动打开页面会提示初始化；也可以直接调用接口：

```bash
curl -X POST http://127.0.0.1:5050/api/auth/initialize \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"admin","password":"your_password"}'
```

#### 4. 访问系统

服务启动完成后，访问以下地址：

::: tip 提示
建议使用 `127.0.0.1` 而不是 `localhost`：在部分 macOS 环境下 `localhost -> ::1(IPv6)` 可能导致浏览器连接 `5173/5050` 失败（表现为 `ERR_SOCKET_NOT_CONNECTED` / `Failed to fetch dynamically imported module`）。
:::

- **Web 界面**: `http://127.0.0.1:5173`
- **API 文档**: `http://127.0.0.1:5050/docs`

#### 5. 停止服务

```bash
docker compose down
```

如果你是本地启动前后端（非 Docker），直接在对应终端 `Ctrl+C` 停止进程即可。

## 对话

项目第一次启动后，会要求填写超级管理员账号和密码，请确保填写正确。

然后在智能体页面可以进行对话，在右侧可以配置提示词、模型、工具等参数。

![agent.png](/images/agent.png)



## 故障排除

#### 查看服务状态

```bash
# 查看所有容器状态
docker ps

# 查看后端服务日志
docker logs api-dev -f

# 查看前端服务日志
docker logs web-dev -f
```

#### 常见问题

<details>
<summary><strong>Docker 镜像拉取失败</strong></summary>

如果拉取镜像失败，可以尝试手动拉取：

```bash
# Linux/macOS
bash docker/pull_image.sh python:3.12-slim

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File docker/pull_image.ps1 python:3.12-slim
```

**离线镜像拉取方案**：

```bash
# 在有网络的环境保存镜像（镜像名称需要确认是否和实际一致）
bash docker/save_docker_images.sh  # Linux/macOS
powershell -ExecutionPolicy Bypass -File docker/save_docker_images.ps1  # Windows

# 传输到目标设备
scp docker_images_xxx.tar <user>@<dev_host>:<path_to_save>

# 在目标设备加载镜像
docker load -i docker_images_xxx.tar
```

</details>

<details>
<summary><strong>构建失败</strong></summary>

如果构建失败，通常是网络问题，可以配置代理：

```bash
# Linux / macOS
export HTTP_PROXY=http://IP:PORT
export HTTPS_PROXY=http://IP:PORT

# Windows PowerShell
$env:HTTP_PROXY="http://IP:PORT"
$env:HTTPS_PROXY="http://IP:PORT"
```

如果已配置代理但构建失败，尝试移除代理后重试。

</details>

<details>
<summary><strong>Milvus 启动失败</strong></summary>

```bash
# 重启 Milvus 服务
docker compose up milvus -d
docker restart api-dev
```

</details>
