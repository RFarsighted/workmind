# WorkMind 本地运行与校验

本文分为两部分：第一部分启动并校验本地基础服务；第二部分验证知识库 RAG。命令适用于 Windows PowerShell。

## 第一部分：本地运行和基础校验

### 准备环境

安装并启动 Docker Desktop（包含 Docker Compose）、Node.js、pnpm 和 [uv](https://docs.astral.sh/uv/)。准备三个 PowerShell 终端：分别运行数据库/向量库、FastAPI 和前端。

### 1. 启动 PostgreSQL 和 Chroma

在第一个终端进入仓库根目录：

```powershell
docker compose up -d postgres chroma
docker compose ps
```

等待 PostgreSQL 显示 `healthy`，并确认 Chroma 容器正在运行。

| 服务 | 本机地址 | 容器端口 |
| --- | --- | --- |
| PostgreSQL | `localhost:5433` | `5432` |
| Chroma | `localhost:8000` | `8000` |

### 2. 配置并运行 FastAPI

在第二个终端进入 `server` 目录，创建本地配置：

```powershell
Set-Location .\server
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

设置 `DATABASE_URL` 为 `postgresql+asyncpg://workmind:workmind_dev@localhost:5433/workmind`，并填写聊天模型密钥：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

RAG 的 SiliconFlow 密钥在第二部分配置。不要把真实密钥提交到 Git。保存后，在 `server` 目录执行：

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 3001
```

保持该终端运行。后端从当前目录的 `.env` 读取配置。

### 3. 检查后端和依赖

在任一 PowerShell 终端运行：

```powershell
Invoke-RestMethod http://127.0.0.1:3001/health/live
Invoke-RestMethod http://127.0.0.1:3001/health/ready
```

`/health/live` 应返回 `status: ok`；`/health/ready` 应显示 PostgreSQL 和 Chroma 均为 `ok`。就绪检查不验证模型 API Key。

### 4. 启动前端

在第三个终端进入 `frontend` 目录：

```powershell
Set-Location .\frontend
pnpm install --frozen-lockfile
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:3001'
pnpm exec vite --host 127.0.0.1 --port 5174
```

浏览器打开 <http://127.0.0.1:5174>。Vite 会将 `/api` 请求代理到本地 FastAPI。

### 5. 校验基础聊天

在聊天页面发送一句话，确认回答逐步显示并正常结束。也可以直接观察 SSE：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"message":"请用一句话介绍 WorkMind。","sessionId":"local-check","userId":"user-demo","role":"default"}' http://127.0.0.1:3001/api/chat/stream
```

成功流应包含 `event: start`、一个或多个 `event: token` 和 `event: done`。聊天消息会保存到 PostgreSQL。

## 第二部分：校验 RAG 知识库问答

### 1. 配置 SiliconFlow

在 `server/.env` 添加 SiliconFlow 密钥：

```dotenv
SILICONFLOW_API_KEY=你的硅基流动密钥
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_EMBEDDING_MODEL=BAAI/bge-m3
RAG_MIN_SIMILARITY=0.3
```

保存后重启 FastAPI。文档入库需要 SiliconFlow；生成回答还需要 `DEEPSEEK_API_KEY`。首次按第一部分启动时执行的 `alembic upgrade head` 已创建文档元数据表。

当前实现把文本片段发送到 SiliconFlow 做向量化，把命中的片段和问题发送到 DeepSeek 生成回答。只使用获准发往托管 API 的资料。首版不支持扫描版 PDF 的 OCR、Office 文件或用户级权限。

### 2. 上传一份可验证的制度文档

打开知识库页面，选择“粘贴文本”，标题填 `差旅报销制度-本地校验`，分类选 `HR制度`，粘贴以下内容并入库：

```text
公司差旅报销制度：员工出差住宿每晚报销上限为600元，报销时需提交住宿发票。国内出差应优先选择经济舱。购买机票前需获得直属主管批准。市内交通费用凭合规票据报销。
```

确认页面出现入库成功提示，文档列表显示标题、分类和片段数。文件上传另可选 TXT、Markdown 或可提取文字的 PDF，单文件上限为 10 MB。

### 3. 校验回答、来源和拒答

在知识库问答框中按顺序试问：

1. `出差住宿每晚报销上限是多少？` 应回答每晚 600 元，并显示来源 `差旅报销制度-本地校验`。展开来源应能看到对应文本片段和相似度。
2. `今天上海天气怎么样？` 文档没有天气资料，应回复“知识库中未找到相关内容”或同义拒答，不应编造天气。
3. 再添加一份分类为 `技术文档` 的文本，然后把搜索范围设为 `HR制度`，询问该技术文档里的内容，应不检索到技术文档。

检查回答期间出现检索/生成状态、来源在回答 token 之前显示，并且清空记录按钮可用。刷新页面后文档仍在列表中；问答历史按设计只保存在当前页面状态。

### 4. 校验删除和异常输入

- 删除刚才添加的文档，确认列表移除；再问住宿上限，应不再引用该文档。
- 上传超过 10 MB 的文件、损坏的 PDF 或没有可提取文字的扫描 PDF，应收到明确错误，且文档列表不应新增失败记录。
- 缺少 `SILICONFLOW_API_KEY` 时，入库/检索接口会返回配置错误；缺少 `DEEPSEEK_API_KEY` 时，问答不能生成回答。查看 FastAPI 终端日志定位网络、鉴权或上游服务错误。

`RAG_MIN_SIMILARITY=0.3` 是可调整的初始阈值，不是经你的语料评估后的准确率承诺。若无关问题被召回或相关问题被拒答，用本节正反例调节该值后重启后端复验。Chroma 使用余弦距离，API 将距离换算为用于界面显示的相似度。

### 停止服务

在 FastAPI 和 Vite 终端按 `Ctrl+C`。停止数据库和向量库（数据卷保留）：

```powershell
docker compose stop postgres chroma
```
