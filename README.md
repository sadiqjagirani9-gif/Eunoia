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

## V2 高级认知功能

左侧“高级认知”入口包含三个本地功能：双重人格分析分别使用温柔导师和理性观察者两套独立提示词；情感关系图谱保存人物、单向或双向关系、来源和关系事件；反事实模拟生成原有选择与两个替代路径，并明确短期、中期、长期影响及不确定性。新增表通过版本迁移创建，首次升级会生成 `eunoia.pre-v2-backup.sqlite3`，不会删除旧对话或记忆。

## V3 长期认知画像

侧栏“我的认知画像”会对每条用户消息进行本地关键词结构化提取，生成待确认线索，覆盖情绪、思维、人际、价值观、行为和自我认知六个维度。观察附有来源证据和可信度等级，用户可以认同、部分认同、不认同、补充或删除；已确认观察会在后续对话、双重分析和反事实模拟中作为可纠正上下文。认知差异以问题呈现，不自动判断用户前后矛盾。

档案页面支持暂停更新、关闭认知分析、月度/季度变化查看、手动快照、JSON 导出与恢复、清空认知档案。V3 迁移只新增表，并在旧 SQLite 文件旁生成一次 `eunoia.pre-v3-backup.sqlite3`。短期情境默认 30 天后清理。新观察默认等待用户确认。

## V4 四个人格空间

侧栏提供情感解剖、理性辩论、生活指导和自我探索四个独立空间。每个空间使用独立的本地 system prompt 文件，拥有不同的思维框架、回答结构和提问策略；情感解剖由 Evelyn 人格负责，理性辩论由 Arthur 人格负责。理性辩论输入区可选择正常讨论、反方辩论、钢人论证或双方辩论。历史会话会固定在创建时的空间。旧会话和消息保留，并将旧模式映射到最接近的新空间。历史对话支持收藏、取消收藏和删除。主页不展示情绪侧栏和示例话题卡，认知功能入口仅保留可编辑的“我的认知画像”。

## 本地专业知识库

`knowledge_base/` 含 Evelyn、Arthur、Sophia、Iris 四个空间各自的七个知识领域。每份种子资料按理论/研究名称、提出者、历史背景、概念、观点、研究、经典文献、适用范围、局限、案例、关联理论和参考文献组织，并标注理论的实证、争议、历史或哲学性质。对话检索严格按当前空间隔离，并把本地资料作为上下文交给 Ollama；模型被要求只引用检索到的出处，不编造研究。

知识库页面可导入 PDF、TXT、Markdown 或公开 HTTPS 网页，更新同名导入文件，删除来源并重建索引。SQLite 保存来源和分块元数据。默认向量模型为 `nomic-embed-text`；要启用语义向量检索，运行 `ollama pull nomic-embed-text` 后在页面选择“重建索引”。没有该模型时仍可使用本地词项检索，页面会显示实际检索方式。可用 `EUNOIA_EMBEDDING_MODEL` 指定其他兼容 Ollama `/api/embed` 的本地模型。PDF 文本提取由本地 `pypdf` 依赖完成。

## Development

Backend tests: from `backend`, run `..\.venv\Scripts\python.exe -m pytest`.

Frontend: `cd frontend; npm install; npm run dev`

The API documentation is at http://127.0.0.1:8000/docs while the backend is running.
