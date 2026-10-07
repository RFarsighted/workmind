# 知识库问答（RAG）

## 功能范围

首版支持 `.txt`、`.md`、可提取文本的 `.pdf` 和粘贴文本，文件上限 10 MB。暂不支持扫描件 OCR、Office 文件、登录和用户级知识库隔离。

文档按 500 字符切分、相邻片段重叠 50 字符。PostgreSQL 保存标题、分类、原文件名、片段数、字符数和预览；Chroma 保存片段、向量和检索所需元数据。重复上传同名文档会创建独立条目。

## 数据流

**入库：** 文件或粘贴文本 → 文本提取 → 分片 → SiliconFlow `BAAI/bge-m3` Embedding → 写入 Chroma → 写入 PostgreSQL 文档登记。

**问答：** 问题 → SiliconFlow Embedding → Chroma 余弦检索（可按分类过滤，最多取 4 个片段）→ 相似度阈值判断 → DeepSeek 按参考片段流式回答并标注文档来源。

Chroma 与 PostgreSQL 不共享事务。入库任一步骤失败会尝试补偿删除已写入的向量；删除时先删 Chroma 片段，再删数据库登记。补偿失败会写入后端日志，需检查服务状态并重试。

## API

- `POST /api/knowledge/documents`：multipart 文件或 JSON 文本入库。
- `GET /api/knowledge/documents?category=HR制度`：列出文档，可按分类筛选。
- `GET /api/knowledge/categories`：返回前端分类选项。
- `DELETE /api/knowledge/documents/{document_id}`：删除文档及对应向量。
- `POST /api/knowledge/query/stream`：接收 `question` 和可选 `category`，返回 SSE。

问答 SSE 顺序为 `status`、`sources`、`status`、`token`（一个或多个）、`done`；失败时发送 `error`。来源包含标题、片段内容和相似度分数。

## 配置与校验

在 `server/.env` 配置 `SILICONFLOW_API_KEY`。提问生成答案还需 `DEEPSEEK_API_KEY`。Embedding 模型、SiliconFlow API 地址和拒答阈值分别可用 `SILICONFLOW_EMBEDDING_MODEL`、`SILICONFLOW_BASE_URL` 和 `RAG_MIN_SIMILARITY` 配置。

本地上传、相关问题、无关问题、分类过滤、删除和异常输入的操作步骤见[本地运行与校验中的 RAG 步骤](local-run.md#2-校验-rag-知识库问答)。阈值 `0.3` 是初始值，应使用项目实际文档和正反例调优。Chroma 返回余弦距离，代码将其转换为界面分数；分数不是模型置信度。

## 数据与安全边界

文档片段会发送到 SiliconFlow 做 Embedding；召回片段和问题会发送到 DeepSeek 生成答案。只上传获准交由托管 API 处理的材料。首版是单知识库本地开发功能，没有身份认证或用户间数据隔离；上线前需补充权限、安全控制、日志和限流。
