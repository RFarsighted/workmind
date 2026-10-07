# Prompt 调试与 Token 用量看板

本文说明 WorkMind 第六章“Prompt 调试工具”和第七章“用量与成本看板”的当前实现、接口和本地验收方法。当前看板按 Token 统计，不显示货币费用；Token 预算用于提醒，不会阻断模型请求。

## 第六章：Prompt 调试工具

### 功能

- **单次测试：**输入 System Prompt 和用户问题，设置 Temperature（0–2）及 Max Tokens（100–4096），查看流式回答、延迟和输入/输出 Token。
- **A/B 对比：**相同问题并行请求两种 Prompt，再分别对两个答案按相关性、准确性、清晰度、简洁度和综合质量评分。比较 `overall` 分数决定胜者；同分显示平局。
- **模板库：**内置通用问答、代码助手和内容写作模板。模板及版本保存在 PostgreSQL；保存内容会形成版本快照，最多保留最近 10 个版本。内置模板禁止删除。

A/B 一次对比包含 4 次模型请求：A、B 两个回答，以及两个独立评分。看板会按“ A/B 回答”和“A/B 评分”分别记录。

### 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/prompt/test/stream` | 单次 Prompt 流式测试 |
| `POST` | `/api/prompt/ab-test` | 并行生成 A/B 答案并评分 |
| `GET` | `/api/prompt/templates` | 列出模板；首次读取时初始化内置模板 |
| `POST` | `/api/prompt/templates` | 新建模板 |
| `PUT` | `/api/prompt/templates/{id}` | 保存模板新版本 |
| `DELETE` | `/api/prompt/templates/{id}` | 删除用户模板；内置模板返回 `403` |

单次测试请求示例：

```json
{
  "systemPrompt": "你是一个简洁的技术助手。",
  "userMessage": "解释什么是 HTTP。",
  "temperature": 0.3,
  "maxTokens": 500
}
```

流式响应使用 SSE：`start`、一个或多个 `token`，最后为带延迟和 Token 用量的 `done`；失败时发送 `error`。A/B 请求字段为 `question`、`systemPromptA`、`systemPromptB`、`temperature` 和 `maxTokens`。响应包含 `answerA`、`answerB` 及 `evaluation.scoreA`、`evaluation.scoreB`、`evaluation.winner`、`evaluation.reason`。

## 第七章：Token 用量看板

### 统计范围与口径

- 按服务端实际模型请求计数，覆盖聊天、知识库生成与 Embedding、Agent、工作流、ERP、Prompt 单测、A/B 回答和评分。
- 记录功能类别、模型名、延迟、成功状态和输入/输出 Token；不把请求正文或模型回答写入监控表。
- 失败或中断的请求计入请求数和明细，但不计入 Token 预算或成功请求的延迟分位数。
- 模型没有返回准确 Token 用量时，记录请求和延迟，Token 显示为“未知”。预算百分比按已知 Token 计算，并在页面提示未知用量请求数。
- 日期按 `Asia/Shanghai` 统计。保留近 90 天明细；访问统计接口时清理 90 天以前的记录。
- 默认每日 Token 预算为 1,000,000 Token。达到 80% 显示预警，达到 100% 显示超额状态；超过预算仍可继续请求。

DeepSeek 流式接口通过 `stream_options.include_usage` 获取末尾 usage 数据；如果供应商未返回 usage，页面保留未知值，不根据文本长度估算。当前不显示 API 货币费用，因此 Token 预算不能当作货币成本上限。

### 看板内容

- 今日模型请求次数、输入 Token、输出 Token及平均延迟。
- 近 7 日输入/输出 Token 柱状图。
- 今日各功能请求数和已知 Token 分布。
- 成功请求的平均延迟及 P50、P90、P99。
- 最近调用明细，包含功能、模型、成功状态、Token 和延迟。
- 每 10 秒刷新一次；预算设置及监控数据存入数据库。

### 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/monitor/stats` | 获取今日概况、近 7 日、功能分布、延迟和最近记录 |
| `PUT` | `/api/monitor/budget` | 修改每日 Token 预算，请求字段为 `dailyBudgetTokens` |

设置预算请求示例：

```json
{
  "dailyBudgetTokens": 500000
}
```

## 本地启动与验收

在仓库根目录启动服务。Compose 配置会在后端启动时执行 Alembic 迁移：

```powershell
docker compose up -d --build
```

先确认 `server/.env` 配置了 `DEEPSEEK_API_KEY`。进行知识库 Embedding 测试时还需 `SILICONFLOW_API_KEY`。

1. 打开 Prompt 调试页，填写 Prompt 和问题，执行单测；确认回答流式显示，完成后显示延迟及 Token 数，缺失用量显示“未知”。
2. 在 A/B 页面填入两种 Prompt，执行对比；确认两边均有答案、五项评分、胜者或平局及评判理由。
3. 新建模板并保存；修改后再次保存，确认版本历史新增。恢复历史内容后保存，确认产生新快照。内置模板删除按钮禁用。
4. 打开 Token 用量看板；发起聊天、Agent 或 Prompt 请求后等待轮询或点击刷新，确认请求数、功能分类和近期记录变化。
5. 把每日 Token 预算改小，观察 80%/100% 提示。超出预算后仍可发起请求。
6. 确认失败请求在明细中标为失败，不能增加 Token 使用量或延迟分位数。

也可直接访问 `http://localhost:3000/docs` 查看 FastAPI OpenAPI 页面，或使用 `GET /api/monitor/stats` 检查统计响应。

模板和预算当前是此应用实例共享数据，没有用户登录或用户级隔离。监控明细只存请求元数据，但 Prompt 模板会持久化其正文。
