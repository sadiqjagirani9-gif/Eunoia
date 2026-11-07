# Eunoia

本地优先的六人格 AI 交流空间。Eunoia 不捆绑模型服务或 API Key；连接你自己选择的云端 API，或在本机运行 Ollama。聊天记录、记忆、模型配置和知识库默认保存在自己的设备上。

## 功能

- 六个独立人格空间：Evelyn（情感解剖）、Arthur（理性辩论）、Sophia（生活指导）、Iris（自我探索）、Lucien（文学艺术）和 Felix（日常闲谈）。
- 用户自带模型：OpenAI Compatible、Anthropic Messages、Ollama 和自定义服务商；人格可独立绑定模型。
- 模型管理：安全保存密钥、连接测试、全局默认模型、每人格参数和本地调用用量统计。
- 本地 SQLite 历史对话、用户可管理的长期记忆与认知画像。
- 按人格隔离的本地知识库检索；支持 PDF、TXT、Markdown 和公开 HTTPS 网页导入。
- Windows 一键启动脚本。

## Windows 快速开始

需要 Windows 10/11、Python 3.11+ 和 Node.js 20+。运行 `start.bat`，脚本会准备本地依赖并启动前后端。浏览器打开 [http://127.0.0.1:6081](http://127.0.0.1:6081)。首次启动安装依赖需要网络。

数据默认存放在 `%LOCALAPPDATA%\Eunoia`。可通过 `EUNOIA_DATA_DIR` 修改位置；可选环境变量见 `.env.example`。后端仅绑定本机回环地址。

## 配置模型

首次打开后选择「模型管理」并添加配置。Eunoia 不提供 API Key、免费额度或开发者代理。

**云端 API：**在所选服务商控制台申请 API Key，在模型管理中选服务商模板，按其当前文档填写 Base URL、协议和模型 ID。模板不会锁定模型列表。远程地址必须使用 HTTPS。连接测试提示很短，但服务商仍可能计费。云端模式会将该次请求所需的对话上下文发送给你配置的服务商，费用依其账单结算。

**Ollama 本地模型：**安装 Ollama 后，在 PowerShell 运行 `ollama pull qwen2.5:7b`，用 `ollama list` 查看模型 ID。添加「Ollama 本地」配置，Base URL 填 `http://127.0.0.1:11434`，协议选 Ollama，模型 ID 填列表中的名称；API Key 留空。保存后测试连接。

模型密钥只保存在后端，Windows 使用 DPAPI 加密；其他支持平台使用本地 Fernet 密钥文件。配置 API 不会返回已保存的密钥。删除模型配置会解除人格绑定并删除关联密钥。费用统计按用户填写的单价和接口返回的 Token 用量进行本地估算，不代表服务商真实账单。

## 数据与隐私

Eunoia 没有开发者托管的模型代理。选择云端模型时，请只配置可信服务商并查看其数据处理政策；选择本地 Ollama 模型时，请确认该模型为本地模型。SQLite 数据、知识库文件和记忆默认留在本机。API Key 不应提交到 GitHub；`.env`、数据库和运行数据已列入 `.gitignore`，`.env.example` 不包含密钥。

认知画像会记录带来源和可信度的可修正观察，用户可以查看、编辑、删除、导出或关闭认知分析。该工具不提供精神疾病诊断，也不替代专业心理支持。

## 知识库

六个人格的知识库按空间隔离，检索结果作为回答上下文，不跨人格默认混用。来源元数据记录作者/机构、链接、版本、许可和摘要；未经许可不复制受版权保护的完整作品。语义索引可使用本地 Ollama Embedding 模型 `nomic-embed-text`，安装后在知识库页面重建索引；没有向量模型时使用本地词项检索。

## 开发与测试

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
```

```powershell
cd frontend
npm install
npm run dev
```

后端运行时可在 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) 查看本地 API 文档。
