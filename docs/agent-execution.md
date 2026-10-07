# 任务执行 Agent

## 功能范围

任务执行 Agent 使用 LangGraph 在 FastAPI 后端运行多步工具循环，并通过 SSE 将工具调用和回答实时发送到 Vue 页面。首版提供 5 个工具：知识库检索、算术计算、日期查询、保存 Markdown 报告和模拟通知。当前不提供联网搜索，因此不能回答“最新版本”等实时信息问题。

Agent 最多执行 7 次工具调用。信息已足够时会立即回答；达到上限时会关闭工具调用，使用已有信息生成最终回答。任务与步骤历史仅保存在当前页面状态中。

## 执行流程

**提交任务：** 前端向 `POST /api/agent/run` 发送任务文本。后端以 LangGraph `StateGraph` 运行 Agent 节点和 `ToolNode`，模型采用 `ChatOpenAI` 兼容接口连接现有 DeepSeek 配置，温度为 0。

**推送步骤：** 后端使用 LangChain `astream_events(version="v2")` 读取工具和模型事件，再编码为 SSE。工具事件的 `run_id` 作为 `callId`，前端用它把结果归到对应卡片。模型流中带有工具调用片段的 chunk 不作为最终回答展示。

**结束任务：** Agent 在无须工具或达到调用上限后生成最终回答。工具返回错误时，错误作为工具结果交给模型决定是否继续；接口或模型本身失败时发送 `error` 事件。

## 工具

| 工具 | 用途 | 约束 |
| --- | --- | --- |
| `read_doc` | 检索内部制度、产品和技术资料 | 复用 RAG Embedding、Chroma 查询及相似度阈值；无结果时明确返回未找到 |
| `calculate` | 计算算术表达式 | 仅允许数字、括号及 `+ - * / // % **`；不执行任意 Python 代码，乘方指数绝对值最多为 12 |
| `get_date` | 查询今天、日期加减和日期差 | 使用 `Asia/Shanghai` 时区 |
| `write_report` | 保存 Markdown 报告 | 只写入固定 `data/reports` 目录，不接受用户指定路径 |
| `send_notify` | 生成通知结果 | 当前仅模拟；不会发送邮件、飞书或钉钉消息 |

每个工具有模型可读的描述和 Pydantic 参数校验。工具异常返回结构化错误，避免工具异常直接中断 Agent 图。

## API 与 SSE

- `GET /api/agent/tools`：返回工具名称、界面标签和描述。
- `GET /api/agent/examples`：返回页面示例任务。
- `POST /api/agent/run`：JSON 请求体为 `{"task":"..."}`，以 `text/event-stream` 返回执行过程。

SSE 事件采用 `event: <type>` 和 JSON `data`：

| 事件 | 主要数据 | 前端行为 |
| --- | --- | --- |
| `start` | `task`、`startedAt` | 建立运行中任务 |
| `tool_call` | `callId`、`toolName`、`label`、`args` | 创建运行中步骤卡片 |
| `tool_result` | `callId`、`toolName`、`status`、`resultText` | 按调用 ID 更新结果、状态和耗时 |
| `token` | `token` | 追加到最终 Markdown 回答 |
| `done` | `toolCalls` | 标记任务完成 |
| `error` | `message` | 标记任务失败并显示错误 |

工具列表和示例接口是普通 JSON 响应。请求缺少模型密钥时，任务接口返回 `503`；流建立后遇到异常则通过 SSE `error` 返回。

## 配置、运行与数据

Agent 使用已有 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL`。`AGENT_MAX_TOOL_CALLS` 默认是 7，可降低上限；Agent 的硬上限仍为 7。知识库工具还需配置 `SILICONFLOW_API_KEY` 并运行 Chroma。

通过仓库根目录的 `docker compose up -d --build` 启动。Compose 将命名卷 `agent_reports` 挂载到后端 `/app/data/reports`；直接从仓库运行后端时，报告写入 `server/data/reports`。工具结果返回相对位置 `data/reports/<文件名>.md`。任务步骤不写入数据库。

## 安全边界与限制

- 计算器通过 Python AST 解析白名单节点，不使用 `eval`。
- 报告标题用于生成受限文件名，报告写入固定目录；不能通过工具读取任意文件。
- 模拟通知只生成本地工具结果，不对外产生通知副作用。
- DeepSeek 会收到任务文本和工具返回内容；知识库工具还会向 SiliconFlow 发送查询文本并检索 Chroma 文档。不要提交未经授权发送到托管模型服务的材料。
- 首版没有身份认证或用户隔离；不要把当前本地演示服务直接暴露到不可信网络。
- 联网搜索暂缓，因此需要实时信息时应明确告知当前能力限制，不应把模型常识说成搜索结果。

## 校验场景

1. `计算 1500 + 800 的总和，并用一句话说明结果。`：调用 `calculate`，步骤显示完整入参和结果。
2. `今天是几号？从今天起 30 天后是什么日期？`：调用 `get_date`，日期以 `Asia/Shanghai` 计算。
3. `介绍一下 Vue3`：不调用工具，直接流式返回 Markdown 回答。
4. 提交知识库查询、报告生成及通知任务：确认知识库检索、报告文件保存和模拟通知结果。
5. 工具失败或达到 7 次调用上限：错误可见；Agent 使用已有信息结束任务。
6. 重复调用同一工具：开始和结果事件按 `callId` 对应到正确步骤。

本地启动与页面操作步骤见[本地运行与校验第三部分](local-run.md#第三部分校验任务执行-agent)。
