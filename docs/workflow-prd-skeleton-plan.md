# 模板四：PRD 骨架工作流计划

## 概要

周报、会议纪要、邮件润色和 PRD 骨架属于同一套固定工作流结构的四个业务模板：接收输入、运行固定分析节点、暂停供人工审核、生成最终内容。本文定义第四个模板——PRD 骨架——如何遵循这套共用结构。

实现参考 `cym-glm/workmind` 的 `py` 分支流程设计，并适配当前 WorkMind 的 FastAPI、LangGraph、DeepSeek 和 Vue 前端结构。

## 共用结构在模板四中的对应

| 共用阶段 | PRD 骨架模板中的内容 |
| --- | --- |
| 输入 | 用户提交需求描述 `description` |
| 分析节点 | `extract_features` 提取功能点，`identify_constraints` 识别技术与业务约束 |
| 人工审核 | `human_review` 前暂停，展示分析结果并接收可选反馈 |
| 最终生成 | `generate_prd` 根据原始描述、分析结果和审核反馈生成 Markdown |

模板状态包含 `description`、`features`、`constraints`、`human_feedback` 和 `prd`；固定节点顺序为：

`extract_features → identify_constraints → human_review → generate_prd`

- 功能点按 P0/P1/P2 排序，只提取需求中明确提出的能力。
- 约束覆盖技术与业务两类；未提供的信息标为“待确认”。
- 工作流在 `human_review` 前暂停，审核面板展示功能点和约束，用户可填写自然语言反馈后继续。
- PRD 固定包含背景与目标、范围、用户故事、功能需求、约束、验收标准、里程碑计划、待确认问题。生成内容不得把未提供信息写成已确认事实；无排期时里程碑标为建议阶段并待确认。

本次实现范围聚焦模板四的节点和 PRD 输出规范；其余三个模板遵循相同的共用结构，但不在本次加入可运行实现。

## API 与状态生命周期

- `GET /api/workflow/templates` 返回唯一可用模板 `prd_skeleton` 及节点元数据。
- `POST /api/workflow/start/stream` 接收 `{workflowId, input: {description}}`，返回 `start`、`node_start`、`node_done`、`paused`、`completed` 或 `error` SSE 事件。
- `POST /api/workflow/resume/stream` 接收 `{threadId, feedback}`，推送生成 `token`、`node_done`、`completed` 或 `error` 事件。
- `POST /api/workflow/cancel` 接收 `{threadId}`，清理暂停中的工作流实例。取消端点用于让审核面板的“取消”真正结束服务端暂停任务。
- 输入分析温度为 0，最终生成温度为 0.7。输入无效或模型节点失败时停止执行并返回错误事件。
- 首版采用 `MemorySaver` 和进程内线程表；进程重启后无法恢复，且多进程不共享暂停状态。完成、失败和取消时清理活跃实例。

## 验收

- 模板列表只显示 PRD 骨架；空描述及未知模板返回明确错误。
- 节点按固定顺序执行，审核暂停时能查看功能点和约束；空反馈和有反馈两种情况都能继续。
- 结果包含八个固定章节，缺失信息以“待补充”或“待确认”呈现。
- 暂停流程可按原 `threadId` 恢复；无效线程返回 404；不同线程状态相互隔离。
- 模型失败不发送成功事件；用户取消后对应线程不可恢复。
- 前端节点进度、审核面板、流式生成及 Markdown 结果均正常工作。

## 限制

本计划首版不实现其他三个工作流模板，也不提供跨服务重启恢复。若需要多 worker 或生产级恢复能力，应后续改用共享的持久化 checkpointer。
