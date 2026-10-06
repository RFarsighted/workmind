# WorkMind AI

WorkMind AI 是一个面向办公场景的 AI 助手示例项目。当前仓库包含 Vue 3 前端、FastAPI 后端、PostgreSQL 和 Chroma。

## 功能状态

- **聊天助手：** DeepSeek 流式对话，消息写入 PostgreSQL。
- **知识库问答：** 支持 TXT、Markdown、可提取文本的 PDF 和粘贴文本；按分类检索，展示来源片段，并用 DeepSeek 生成回答。PostgreSQL 保存文档元数据，Chroma 保存向量片段。Embedding 使用 SiliconFlow `BAAI/bge-m3`。
- **其他模块：** Agent、工作流、ERP/OA、Prompt 管理和用量看板目前以界面骨架为主，后续逐项实现。

## 技术组成

- 前端：Vue 3、Vite、Pinia、Element Plus
- 后端：Python 3.12+、FastAPI、SQLAlchemy、Alembic
- 存储：PostgreSQL、Chroma
- 模型：DeepSeek（聊天与回答）、SiliconFlow `BAAI/bge-m3`（Embedding）

## 本地运行

Windows 本地启动、健康检查、聊天验证及 RAG 逐步校验见[本地运行与校验](docs/local-run.md)。首次配置好 `server/.env` 后，在仓库根目录用 Docker Compose 启动全栈；无需在本机分别运行前后端。

```powershell
docker compose up -d --build
```

打开 <http://localhost:5173> 使用前端，健康检查地址为 <http://localhost:3000/health/ready>。RAG 需要 DeepSeek 和 SiliconFlow API Key；`.env` 只放本机，不能提交。

## 文档

- [本地运行与校验](docs/local-run.md)：环境准备、服务启动、聊天和 RAG 验收步骤。
- [知识库问答（RAG）](docs/knowledge-base-rag.md)：RAG 数据流、接口、模型配置及当前限制。

后续每完成一个业务模块，应在 `docs/` 新增对应的 Markdown 文档，记录如何配置、运行和校验，并在本节添加链接。
