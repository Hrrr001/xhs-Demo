"""
小红书内容生成+合规校验 — 全局配置
从 .env 文件读取敏感信息，其余使用合理默认值。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
VECTORDB_DIR = ROOT_DIR / "vectordb"

# 加载 .env
load_dotenv(ROOT_DIR / ".env")

# ============================================================
# LLM 配置（默认使用智谱AI GLM-4-Flash，完全免费，OpenAI 兼容）
# ============================================================
LLM_API_KEY = os.getenv("LLM_API_KEY", "your-api-key-here")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
LLM_MODEL = os.getenv("LLM_MODEL", "GLM-4-Flash")

# ============================================================
# Embedding 模型（本地运行，免费）
# ============================================================
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"

# ============================================================
# ChromaDB
# ============================================================
CHROMA_COLLECTION = "xiaohongshu_posts"

# ============================================================
# RAG 参数
# ============================================================
RAG_TOP_K = 5          # 检索返回的相似文案数
RAG_SIMILARITY_THRESHOLD = 0.3  # 最低相似度阈值

# ============================================================
# 爆款评分权重
# ============================================================
SCORE_WEIGHTS = {
    "title_appeal": 0.30,      # 标题吸引力
    "structure_match": 0.25,   # 结构匹配度
    "tag_quality": 0.15,       # 标签质量
    "engagement_potential": 0.20,  # 互动潜力
    "compliance_bonus": 0.10,  # 合规加分
}
