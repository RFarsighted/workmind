# WorkMind 本地运行与校验

本文分为两部分：第一部分用一条 Docker Compose 命令启动全部服务并校验基础聊天；第二部分验证知识库 RAG。适用于 Windows PowerShell。

## 第一部分：启动和校验本地服务

### 准备环境

只需安装并启动 Docker Desktop（包含 Docker Compose）。不需要在本机分别安装 Node.js、pnpm 或 uv；这些运行时都在容器中。

### 首次配置密钥

在仓库根目录打开 PowerShell。首次运行时复制模板并填写 DeepSeek 密钥；准备校验 RAG 时也填写 SiliconFlow 密钥：

```powershell
if (-not (Test-Path .\server\.env)) { Copy-Item .\server\.env.example .\server\.env }
notepad .\server\.env
```

配置示例：

```dotenv
DEEPSEEK_API_KEY=你的密钥
SILICONFLOW_API_KEY=你的硅基流动密钥
```

只在本机的 `server/.env` 保存真实密钥，不要提交该文件。

### 启动全部服务

仍在仓库根目录运行：

```powershell
docker compose up -d --build
```

Compose 会启动 PostgreSQL、Chroma、FastAPI 和 Vue 前端；后端容器启动时会自动执行 Alembic 数据库迁移。首次启动需要下载镜像并构建，稍等片刻即可。

- 前端：<http://localhost:5173>
- 后端健康检查：<http://localhost:3000/health/ready>

查看服务状态和日志：

```powershell
docker compose ps
docker compose logs -f server
```

就绪检查应显示 PostgreSQL 和 Chroma 均为 `ok`。这项检查不会验证模型 API Key。

### 校验基础聊天

在前端聊天页面发送一句话，确认回答逐步显示并正常结束。也可在 PowerShell 直接看 SSE：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"message":"请用一句话介绍 WorkMind。","sessionId":"local-check","userId":"user-demo","role":"default"}' http://localhost:3000/api/chat/stream
```

成功流包含 `event: start`、一个或多个 `event: token` 和 `event: done`。聊天消息会保存到 PostgreSQL。

## 第二部分：校验 RAG 知识库问答

### 上传校验文档

确认 `server/.env` 已填写 `SILICONFLOW_API_KEY` 和 `DEEPSEEK_API_KEY`。前者用于文档向量化，后者用于生成回答。若刚修改 `.env`，让 Compose 重新创建后端容器以加载新密钥：

```powershell
docker compose up -d --force-recreate server
```

在 <http://localhost:5173> 打开知识库，选择“粘贴文本”，标题填 `差旅报销制度-本地校验`，分类选 `HR制度`，粘贴以下内容并入库：

```text
公司差旅报销制度：员工出差住宿每晚报销上限为600元，报销时需提交住宿发票。国内出差应优先选择经济舱。购买机票前需获得直属主管批准。市内交通费用凭合规票据报销。
```

页面应显示入库成功，文档列表应显示标题、分类和片段数。文件上传也支持 TXT、Markdown 和可提取文字的 PDF，单文件最大 10 MB；扫描版 PDF 暂不支持 OCR。

### 提问并检查结果

在知识库问答框依次提问：

1. `出差住宿每晚报销上限是多少？` 应回答每晚 600 元，并显示来源 `差旅报销制度-本地校验`。展开来源可查看原始片段和相似度。
2. `今天上海天气怎么样？` 文档没有天气资料，应回答未找到相关内容，不应编造天气。
3. 另添加一份分类为 `技术文档` 的文本，把搜索范围选为 `HR制度`，再询问该技术文档中的内容；结果不应引用技术文档。

再删除差旅文档并重复问住宿上限，确认该文档不再出现在来源中。刷新页面后文档仍应存在；问答历史只保存在当前页面状态。

需要观察原始 SSE 时可运行：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"question":"出差住宿每晚报销上限是多少？","category":"HR制度"}' http://localhost:3000/api/knowledge/query/stream
```

响应顺序应包含 `event: status`、`event: sources`、生成状态、一个或多个 `event: token`，最后是 `event: done`；失败时为 `event: error`。

### 常见问题

- `/health/ready` 失败：运行 `docker compose ps`，再查看 `docker compose logs server postgres chroma`。
- 提示配置 `SILICONFLOW_API_KEY` 或 `DEEPSEEK_API_KEY`：检查 `server/.env` 拼写，并执行上面的 `--force-recreate server` 命令。
- 上传 10 MB 以上文件、损坏 PDF 或无可提取文字的 PDF：接口会拒绝入库并返回错误。
- 无关问题被召回或相关问题被拒答：`RAG_MIN_SIMILARITY` 默认 `0.3`，只是起始值。修改 `server/.env` 后重新创建 server 容器，并用正反例复验。
- 托管 API 会收到文档片段、问题或命中的上下文；只使用获准发往 SiliconFlow 和 DeepSeek 的资料。

### 停止服务

在仓库根目录运行：

```powershell
docker compose down
```

该命令移除容器和网络，但保留 PostgreSQL、Chroma 数据卷。再次启动时重新运行 `docker compose up -d` 即可。
