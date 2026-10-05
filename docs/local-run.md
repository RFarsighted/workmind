# WorkMind AI 本地运行与验证

本文介绍如何在 Windows 上本地运行前端和 FastAPI，并通过 Docker 启动 PostgreSQL 与 Chroma。按步骤操作后，可以检查服务健康状态，并用 DeepSeek 完成一次真实的流式聊天。

## 准备环境

请先安装并启动：

- Docker Desktop（包含 Docker Compose）
- Node.js 与 pnpm
- [uv](https://docs.astral.sh/uv/)

打开三个 PowerShell 终端。第一个用于启动数据库和向量库，第二个运行后端，第三个运行前端。

## 1. 启动 PostgreSQL 和 Chroma

在第一个终端进入仓库根目录，运行：

```powershell
docker compose up -d postgres chroma
docker compose ps
```

等待 PostgreSQL 显示 `healthy`，并确认 Chroma 容器处于运行状态。主机端口映射为：

| 服务 | 本机地址 | 容器端口 |
| --- | --- | --- |
| PostgreSQL | `localhost:5433` | `5432` |
| Chroma | `localhost:8000` | `8000` |

PostgreSQL 在容器内仍使用 `5432`；`5433` 是本机访问端口，用来避开本机可能已运行的 PostgreSQL 服务。

## 2. 配置并运行 FastAPI

在第二个终端进入仓库的 `server` 目录：

```powershell
Set-Location .\server
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

在 `.env` 中填写你自己的 DeepSeek API Key：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

不要把真实密钥提交到 Git 或发到聊天中。配置文件里的数据库地址应为 `localhost:5433`，Chroma 地址应为 `http://localhost:8000`。保存文件后，在同一终端运行：

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 3001
```

请从 `server` 目录启动后端，配置会从当前目录下的 `.env` 读取。保持这个终端运行。

## 3. 检查后端健康状态

在另一个 PowerShell 终端运行：

```powershell
Invoke-RestMethod http://127.0.0.1:3001/health/live
Invoke-RestMethod http://127.0.0.1:3001/health/ready
```

存活检查应返回 `status: ok`；就绪检查应返回类似结果：

```text
status   postgres   chroma
------   --------   ------
ready    ok         ok
```

`/health/ready` 会实际连接 PostgreSQL 并检查 Chroma，因此它通过表示这两个依赖均已就绪。

## 4. 运行前端

在第三个终端进入 `frontend` 目录并运行：

```powershell
Set-Location .\frontend
pnpm install --frozen-lockfile
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:3001'
pnpm exec vite --host 127.0.0.1 --port 5174
```

保持该终端运行，在浏览器打开 <http://127.0.0.1:5174>。Vite 会将 `/api` 请求代理到本地 FastAPI 的 `3001` 端口。

## 5. 验证真实聊天

在页面中打开聊天，发送一条消息。成功时应看到回答逐步显示并正常结束。

聊天接口为 `POST /api/chat/stream`，请求体包含 `message`、`sessionId`、`userId` 和 `role`。也可以从 PowerShell 直接观察 SSE 流：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"message":"请用一句话介绍 WorkMind。","sessionId":"local-check","userId":"user-demo","role":"default"}' http://127.0.0.1:3001/api/chat/stream
```

一次成功的流应依次包含 `event: start`、一个或多个 `event: token`，最后是 `event: done`。聊天成功后，用户消息和助手回复也会写入 PostgreSQL。

### 常见失败信号

- HTTP `503` 且提示设置 `DEEPSEEK_API_KEY`：后端没有读取到密钥。确认 `server/.env` 已填写，并重启 FastAPI。
- SSE 流出现 `event: error`：请求已进入流式响应，但模型调用或后端处理失败。查看 FastAPI 终端日志，并核对密钥、网络和 DeepSeek 服务状态。
- `/health/ready` 返回 `503`：检查 `docker compose ps`，确认 PostgreSQL 与 Chroma 正在运行；再核对 `.env` 中的 `5433` 和 `8000` 地址。
- 页面打不开：确认 Vite 终端没有报错，并访问 `http://127.0.0.1:5174`。本地验证使用 `3001` 和 `5174`，Docker 全栈默认使用 `3000` 和 `5173`。

## 停止本地服务

在运行 FastAPI 和 Vite 的终端分别按 `Ctrl+C`。需要停止 PostgreSQL 和 Chroma 时，在仓库根目录运行：

```powershell
docker compose stop postgres chroma
```

该命令会停止容器，但保留 Compose 管理的数据卷。

## 提交并推送到 GitHub

本项目当前分支为 `main`，远程仓库名为 `origin`。提交前在仓库根目录检查变更：

```powershell
git status --short
git check-ignore server/.env
```

`server/.env` 应显示为已忽略文件。它包含本机 API Key，不要强制添加或上传。`.env.example` 是不含真实密钥的模板，可以提交。

确认变更内容后，将项目文件加入暂存区并检查：

```powershell
git add .gitignore docker-compose.yml docs frontend server
git diff --cached --check
git diff --cached --stat
git status --short
```

确认暂存内容没有密钥或本地运行产物后，提交并推送：

```powershell
git commit -m "feat: add WorkMind AI MVP foundation"
git push origin main
```

后续每次修改后，重复检查、暂存、提交和推送。只暂存准备上传的文件；不要使用 `git add -f` 上传 `.env`。

## 后续开发清单

当前完成了基础运行骨架：前端、FastAPI、PostgreSQL、Chroma 可以本地或通过 Docker 运行；基础聊天支持流式输出并将消息写入 PostgreSQL。七个业务模块的状态如下：

| 模块 | 当前状态 | 后续工作 |
| --- | --- | --- |
| 智能对话助手 | 基础聊天可用 | 补齐用户画像接口和前后端会话历史对接；当前画像请求会返回 404 |
| 知识库问答 | 未实现 | 文档上传、解析切分、向量化、Chroma 检索、带来源的回答 |
| 任务 Agent | 未实现 | 工具定义、Function Calling、ReAct 执行步骤和失败恢复 |
| 内容工作流 | 未实现 | 用 LangGraph 实现周报、会议纪要、邮件等生成流程 |
| ERP / OA 助手 | 未实现 | 报销和请假表单、校验及模拟审批流程 |
| Prompt 调试平台 | 未实现 | Prompt 编辑、版本管理、测试集和效果对比 |
| AI 用量看板 | 未实现 | 调用次数、Token、费用和响应耗时统计 |

建议先补齐聊天模块的画像与历史接口，再实现知识库问答；随后依次推进任务 Agent、内容工作流、ERP / OA、Prompt 管理和用量看板。准备对外部署前，还需要补充用户认证与权限、日志和限流、生产环境密钥管理、自动化测试及部署配置。
