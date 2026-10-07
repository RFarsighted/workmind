# WorkMind 本地运行与校验

本文按 1–7 步骤说明：启动全部服务并校验基础聊天、验证知识库 RAG、验证任务执行 Agent、验证需求文档工作流、验证 ERP 报销与请假、验证 Prompt 调试工具，以及验证 Token 用量看板。适用于 Windows PowerShell。

## 1. 启动和校验本地服务

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

## 2. 校验 RAG 知识库问答

### 上传校验文档

确认 `server/.env` 已填写 `SILICONFLOW_API_KEY` 和 `DEEPSEEK_API_KEY`。前者用于文档向量化，后者用于生成回答。若刚修改 `.env`，让 Compose 重新创建后端容器以加载新密钥：

```powershell
docker compose up -d --force-recreate server
```

在 <http://localhost:5173> 打开知识库，选择“粘贴文本”，标题填 `差旅报销制度-本地校验`，分类选 `HR制度`，粘贴以下内容并入库：

```text
公司差旅报销制度：员工出差住宿每晚报销上限为800元，报销时需提交住宿发票。国内出差应优先选择经济舱。购买机票前需获得直属主管批准。市内交通费用凭合规票据报销。
```

页面应显示入库成功，文档列表应显示标题、分类和片段数。文件上传也支持 TXT、Markdown 和可提取文字的 PDF，单文件最大 10 MB；扫描版 PDF 暂不支持 OCR。

### 提问并检查结果

在知识库问答框依次提问：

1. `出差住宿每晚报销上限是多少？` 应回答每晚 800 元，并显示来源 `差旅报销制度-本地校验`。展开来源可查看原始片段和相似度。
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

## 3. 校验任务执行 Agent

### 配置并启动

Agent 使用现有 `DEEPSEEK_API_KEY`，不需要搜索服务密钥。确认 `server/.env` 已填写 DeepSeek Key；知识库工具还需要 `SILICONFLOW_API_KEY`。首次创建或修改配置后，在仓库根目录启动或重新创建后端：

```powershell
docker compose up -d --build
```

Agent 最多执行 7 次工具调用。可用工具包括知识库检索、数学计算、日期查询、生成并保存报告、模拟通知。当前不提供联网搜索；模拟通知不会联系真实人员。

### 验证 SSE 与页面

在前端打开“任务执行 Agent”，提交 `计算 1500 + 800 的总和，并用一句话说明结果。`。应看到计算步骤的入参、结果和 Markdown 最终回答。也可在 PowerShell 查看原始 SSE：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"task":"计算 1500 + 800 的总和，并用一句话说明结果。"}' http://localhost:3000/api/agent/run
```

流中应包含 `event: start`、一组 `tool_call` / `tool_result`、最终回答的一个或多个 `token`，以及 `done`。开始和结果事件用相同 `callId` 关联；若 Agent 或工具失败，流会以 `error` 结束。

再验证以下输入：

1. `今天是几号？从今天起 30 天后是什么日期？` 应使用日期工具，按 `Asia/Shanghai` 计算。
2. `介绍一下 Vue3` 应直接回答，不产生工具步骤。
3. 从示例任务选“生成报告”，确认步骤结果显示 `data/reports/...md`。Compose 使用 `agent_reports` 命名卷保存报告；`docker compose down` 会保留该卷，`docker compose down -v` 会删除卷数据。
4. 展开和折叠工具卡片，确认参数、结果、执行耗时、答案复制和示例填入可用。

工具目录和示例也可通过 `GET /api/agent/tools` 与 `GET /api/agent/examples` 查看。Agent 设计、工具参数和错误处理详见[任务执行 Agent 文档](03-任务执行Agent.md)。

### 常见问题

- Agent 接口返回 `503` 并提示 `DEEPSEEK_API_KEY`：填写 `server/.env` 后执行 `docker compose up -d --force-recreate server`。
- 知识库工具报告检索失败：检查 `SILICONFLOW_API_KEY`、Chroma 状态和后端日志；Agent 会把工具错误作为步骤结果展示。
- 报告保存失败：检查后端目录 `/app/data/reports` 的卷状态；Compose 中卷名为 `agent_reports`。
- 想查询 Vue、React 等最新版本：当前版本没有联网搜索工具，不能把模型回答当作实时搜索结果。

## 4. 校验需求文档工作流

工作流使用现有 `DEEPSEEK_API_KEY`。确认 `server/.env` 已填写密钥并启动 Compose 服务后，在前端打开“内容生成工作流”，选择“需求文档”，输入需求描述。流程应依次提取功能点、识别约束，在人工审核处暂停；填写可选反馈并继续后，页面流式显示 Markdown 需求文档。

也可在 PowerShell 直接查看启动 SSE。响应中的 `paused` 事件会包含 `threadId` 和审核中间结果：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"workflowId":"替换成模板列表返回的标识","input":{"description":"做一个用户评论功能，支持点赞和回复"}}' http://localhost:3000/api/workflow/start/stream
```

把上一步 `start` 或 `paused` 事件中的 `threadId` 填入恢复请求：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"threadId":"替换成上一步的threadId","feedback":"重点说明回复权限，未明确的内容标为待确认"}' http://localhost:3000/api/workflow/resume/stream
```

恢复流应包含生成过程和 `completed` 事件。取消审核可调用 `POST /api/workflow/cancel`，请求体为 `{"threadId":"..."}`。模板列表可通过 `GET /api/workflow/templates` 查看。本首版使用进程内 checkpoint，服务重启后暂停任务需要重新开始；详细设计见[需求文档工作流](04-需求文档工作流.md)。

## 5. 校验 ERP 报销与请假

ERP 使用 `DEEPSEEK_API_KEY` 和 PostgreSQL；启动时 Compose 会自动执行申请历史表迁移。确认密钥已配置后，在前端打开“报销请假”，输入 `上周去上海出差，高铁票800元，住宿两晚960元，餐费300元，请帮我填报销单` 并解析。结果应包含费用明细、正确合计和警告列表；住宿应按两晚折算为 480 元/晚。

提交审批后，应看到主管和财务步骤以及按“审查问题、申请人回应、审批结论”依次出现的消息。金额超过 5000 元时计划中应包含总监；如果财务驳回，后续角色不再启动。审批记录会出现在左侧历史摘要中。

切换到请假模式，输入 `请病假3天，感冒了`，系统应按今天起算并显示日期确认警告及医院证明提醒；提交后 HR 对话应提醒补充证明。

也可查看持久化记录摘要：

```powershell
curl.exe http://localhost:3000/api/erp/applications
```

从摘要中复制申请 ID 后查看完整表单和对话：

```powershell
curl.exe http://localhost:3000/api/erp/applications/替换成申请ID
```

历史当前为共享演示数据，没有用户级隔离。更多规则、接口字段及当前限制见[ERP 报销与请假](05-ERP报销与请假.md)。

## 6. 校验 Prompt 调试工具

Prompt 调试使用现有 `DEEPSEEK_API_KEY`。在前端打开“Prompt 调试工具”，输入 System Prompt 和用户问题，点击“运行测试”。确认回答逐步显示，结束后显示响应时间及输入/输出 Token；供应商未返回 Token 用量时应显示“未知”。Temperature 范围为 0–2，Max Tokens 范围为 100–4096。

在 A/B 对比页填入同一问题和两种 System Prompt，点击“开始对比”。确认 A、B 两个回答并行完成后分别显示相关性、准确性、清晰度、简洁度和综合评分；综合分较高者高亮，同分时显示平局和评判理由。一次 A/B 对比会发出两次答案请求及两次评分请求。

模板库首次加载时会创建通用问答、代码助手和内容写作三个内置模板。新建一个用户模板并保存，再修改后保存；版本历史应增加，最多保留 10 个版本。恢复旧版本并再次保存后应产生新的版本快照，内置模板不可删除。

接口也可用以下命令检查：

```powershell
curl.exe -N -H "Content-Type: application/json" -d '{"systemPrompt":"你是一个简洁的助手。","userMessage":"用一句话解释 HTTP。","temperature":0.3,"maxTokens":300}' http://localhost:3000/api/prompt/test/stream
curl.exe -H "Content-Type: application/json" -d '{"question":"用一句话解释 HTTP。","systemPromptA":"简洁回答。","systemPromptB":"用生活类比回答。","temperature":0,"maxTokens":300}' http://localhost:3000/api/prompt/ab-test
curl.exe http://localhost:3000/api/prompt/templates
```

API 字段、SSE 事件及模板版本接口详见[Prompt 调试与 Token 用量看板文档](06-07-Prompt调试与Token用量看板.md)。

## 7. 校验 Token 用量看板

在前端打开“Token 用量看板”。聊天、知识库、Agent、工作流、ERP 或 Prompt 请求成功后，等待最多 10 秒自动刷新，或点击“刷新”；确认请求记录、功能分类、Token 和延迟出现。A/B 对比会分别统计回答与评分请求。失败请求应标记为失败，不增加 Token 使用量。

看板显示近 7 日输入/输出 Token，以及成功请求的平均延迟、P50、P90 和 P99。用量未知时显示未知请求数；预算进度仅按已知 Token 计算。默认预算为每日 1,000,000 Token，在看板修改预算后验证进度达到 80% 和 100% 时的颜色及提醒。预算超额只提醒，不会阻断请求；当前不展示货币费用。

查看统计接口：

```powershell
curl.exe http://localhost:3000/api/monitor/stats
```

修改每日 Token 预算：

```powershell
curl.exe -X PUT -H "Content-Type: application/json" -d '{"dailyBudgetTokens":500000}' http://localhost:3000/api/monitor/budget
```

监控和模板数据保存在 PostgreSQL；调用明细保留 90 天，访问统计接口时清理过期记录。监控表不存 Prompt 或回答正文。模板正文会保存到数据库；当前模板和预算由此应用实例共享，没有用户级隔离。更多口径和接口字段见[Prompt 调试与 Token 用量看板文档](06-07-Prompt调试与Token用量看板.md)。

### 停止服务

在仓库根目录运行：

```powershell
docker compose down
```

该命令移除容器和网络，但保留 PostgreSQL、Chroma 数据卷。再次启动时重新运行 `docker compose up -d` 即可。
