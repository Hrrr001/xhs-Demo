# 小红书写手 · 爆款决策助手

基于 RAG + Prompt 的小红书内容生成与合规校验工具。

## 功能亮点

- **双版对比生成**：输入产品信息，AI 基于爆款知识库同时生成两版不同风格的文案
- **爆款潜力评分**：五维度打分（标题吸引力、结构匹配、标签质量、互动潜力、合规加分）
- **合规自动检测**：16条规则覆盖广告法违禁词、行业红线、平台导流规范
- **知识库管理**：15条种子爆款文案，支持语义检索

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key
```

推荐使用 [硅基流动](https://siliconflow.cn) 免费额度：
```
LLM_API_KEY=sk-xxxxx
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3
```

也支持 [DeepSeek 开放平台](https://platform.deepseek.com)。

### 3. 启动

```bash
python main.py
```

浏览器访问 `http://localhost:7860`

## 项目结构

```
xiaohongshu-tool/
├── main.py           # Gradio 界面入口
├── generator.py      # LLM 内容生成 + 爆款评分引擎
├── compliance.py     # 合规规则引擎
├── rag_engine.py     # ChromaDB 向量检索
├── config.py         # 全局配置
├── rules.yaml        # 合规规则（16条，可热更新）
├── data/
│   └── seed_posts.jsonl  # 15条种子爆款文案
└── vectordb/         # ChromaDB 持久化目录
```

## 技术栈

| 组件 | 技术 |
|------|------|
| UI | Gradio 4.x |
| 向量库 | ChromaDB |
| Embedding | BAAI/bge-small-zh-v1.5（本地免费） |
| LLM | 硅基流动 / DeepSeek（OpenAI 兼容） |
| 合规规则 | YAML + 正则匹配 |
