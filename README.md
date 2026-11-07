# Eunoia——倾听者

Eunoia is a local-first emotional reflection companion powered by Ollama. Conversations and memories stay in a local SQLite database; the app makes requests only to the local backend and Ollama service.

## Requirements

- Windows 10/11
- Python 3.11+
- Node.js 20+
- Ollama for Windows

Install a local model in PowerShell:

```powershell
ollama pull qwen2.5:7b
```

Then run `start.bat`. It creates a Python virtual environment, installs backend dependencies, installs frontend dependencies, and starts both local services. Open http://127.0.0.1:6081; the browser title is Eunoia倾听者. The first launch needs internet access only to install Python and npm packages; the running application itself uses local services only. For an offline first install, preinstall those dependencies before disconnecting.

Set `EUNOIA_MODEL` to choose a different installed model. Select among installed models in the app's top bar as well. `EUNOIA_DATA_DIR` changes the local data directory; by default data is stored in `%LOCALAPPDATA%\Eunoia`.

Ollama manages GPU acceleration and falls back to CPU when a compatible GPU is unavailable. Install an Ollama build with the appropriate GPU support for your machine. Model size and generation speed depend on available RAM/VRAM. The backend binds to `127.0.0.1` only.

## Privacy and boundaries

The app binds to localhost and sends chat and retrieval requests only to the local backend and local Ollama. SQLite stores conversation content, knowledge metadata, and optional user-approved memories on this device. Importing a webpage is an explicit user action: Eunoia fetches that public HTTPS page and stores its extracted text locally; it does not send chat or memory data to the page. This is a reflection tool, not therapy or diagnosis. In urgent danger, contact local emergency services or a trusted person.

## V3 长期认知画像

侧栏“我的认知画像”会对每条用户消息进行本地关键词结构化提取，生成待确认线索，覆盖情绪、思维、人际、价值观、行为和自我认知六个维度。观察附有来源证据和可信度等级，用户可以认同、部分认同、不认同、补充或删除；已确认观察会在后续对话、双重分析和反事实模拟中作为可纠正上下文。认知差异以问题呈现，不自动判断用户前后矛盾。

档案页面支持暂停更新、关闭认知分析、月度/季度变化查看、手动快照、JSON 导出与恢复、清空认知档案。V3 迁移只新增表，并在旧 SQLite 文件旁生成一次 `eunoia.pre-v3-backup.sqlite3`。短期情境默认 30 天后清理。新观察默认等待用户确认。

## V4 四个人格空间

侧栏提供 Evelyn（情感解剖）、Arthur（理性辩论）、Sophia（生活指导）、Iris（自我探索）、Lucien（文学艺术）和 Felix（日常闲谈）六个独立空间。每个空间使用独立的本地 system prompt 文件，历史会话固定在创建时的空间。Lucien 以文学、艺术、音乐、电影和美学交流为主；Felix 擅长轻松日常对话，避免主动心理分析。两者使用各自隔离的知识检索领域，但沿用同一 SQLite/RAG 架构；长期记忆继续沿用现有设置和管理方式。旧会话和消息保留，并将旧模式映射到最接近的新空间。历史对话支持收藏、取消收藏和删除。主页不展示情绪侧栏和示例话题卡，认知功能入口仅保留可编辑的“我的认知画像”。

## 本地专业知识库

`knowledge_base/` 为六个人格维护独立领域。Lucien 的文学、诗歌、艺术史、视觉艺术、音乐、电影戏剧、美学资料分别位于 `knowledge_base/lucien/`；Felix 的幽默理论、语言学、网络文化、流行文化、游戏娱乐、社会心理、日常知识和原创对话案例位于 `knowledge_base/felix/`。新资料为带来源元数据的项目自写摘要或原创案例，不冒充下载的原文；每个 `.md.meta.json` 记录作者/机构、来源链接、学科、版本、许可、摘要、适用范围和处理说明。许可未确认的来源只保存书目信息与自写摘要，不复制正文。对话检索严格按当前空间隔离，并把本地资料作为上下文交给 Ollama；模型被要求只引用检索到的出处，不编造研究。

知识库页面可按人格与领域查看来源、打开详情、更新/删除用户导入资料、查看本地检索命中并重建索引。导入格式为 PDF、TXT、Markdown 和公开 HTTPS 网页；EPUB 尚不支持。SQLite 保存来源、许可元数据、分块和检索命中记录；导入的原始文件保存在 `%LOCALAPPDATA%\Eunoia\knowledge`（或 `EUNOIA_DATA_DIR\knowledge`），不进入 Git 项目目录。升级时会将旧版本保存在项目 `knowledge_base` 下的导入文件迁到该本地目录，并保留已有来源 ID、分块和向量。默认向量模型为 `nomic-embed-text`；运行 `ollama pull nomic-embed-text` 后在页面选择“重建索引”启用语义检索。没有该模型时仍可使用本地词项检索，页面会显示实际检索方式。可用 `EUNOIA_EMBEDDING_MODEL` 指定其他兼容 Ollama `/api/embed` 的本地模型。PDF 文本提取由本地 `pypdf` 依赖完成。

## Development

Backend tests: from `backend`, run `..\.venv\Scripts\python.exe -m pytest`.

Frontend: `cd frontend; npm install; npm run dev`

The API documentation is at http://127.0.0.1:8000/docs while the backend is running.
