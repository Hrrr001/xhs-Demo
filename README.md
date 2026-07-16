# 小红书写手 · 爆款决策助手

基于 RAG + Prompt 的小红书内容生成与合规校验工具。

## 功能亮点

- **双版对比生成**：输入产品信息，AI 基于爆款知识库同时生成两版不同风格的文案
- **爆款潜力评分**：五维度打分（标题吸引力、结构匹配、标签质量、互动潜力、合规加分）
- **合规自动检测**：16条规则覆盖广告法违禁词、行业红线、平台导流规范
- **知识库管理**：15条种子爆款文案，支持语义检索

## 本地运行

```bash
pip install -r requirements.txt
cp .env.example .env   # 编辑填入 LLM_API_KEY
python main.py         # http://localhost:7860
```

## 部署到 Hugging Face Spaces

### 1. 创建 Space

打开 https://huggingface.co/new-space ，SDK 选 **Gradio**，Hardware 选 **CPU (free)**。

### 2. 设置 API Key

在 Space 的 **Settings > Secrets** 中添加：

| Name | Value |
|------|-------|
| `LLM_API_KEY` | 你的智谱AI Key |

### 3. 推送代码

```bash
git clone https://huggingface.co/spaces/你的用户名/你的Space名
cd 你的Space名
# 把本项目所有文件复制进去（.env 和 vectordb/ 不需要）
git add . && git commit -m "deploy" && git push
```

推送后 HF Spaces 自动构建，约 2-3 分钟可访问。

## 项目结构

```
├── app.py             # HF Spaces 入口
├── main.py            # Gradio 界面
├── generator.py       # LLM 生成 + 评分引擎
├── compliance.py      # 合规规则引擎
├── rag_engine.py      # ChromaDB 语义检索
├── config.py          # 全局配置
├── rules.yaml         # 合规规则（16条）
├── data/seed_posts.jsonl  # 15条种子爆款文案
└── requirements.txt
```

## 技术栈

| 组件 | 技术 |
|------|------|
| UI | Gradio 6.x |
| 向量库 | ChromaDB |
| Embedding | BAAI/bge-small-zh-v1.5（本地） |
| LLM | 智谱AI GLM-4-Flash（免费） |
| 合规规则 | YAML + 正则 |
