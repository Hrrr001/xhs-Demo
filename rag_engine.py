"""
RAG 检索引擎
- 基于 ChromaDB + sentence-transformers 本地 Embedding
- 索引小红书爆款文案，支持语义检索 + 标签过滤
"""

import json
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from config import (
    DATA_DIR,
    VECTORDB_DIR,
    EMBEDDING_MODEL,
    CHROMA_COLLECTION,
    RAG_TOP_K,
)

# ------------------------------------------------------------
# 单例 Embedding 模型（首次加载后缓存）
# ------------------------------------------------------------
_embedding_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        print(f"[LOAD] Embedding model: {EMBEDDING_MODEL} ...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print("[OK] Embedding model loaded")
    return _embedding_model


# ------------------------------------------------------------
# ChromaDB 客户端
# ------------------------------------------------------------
def get_chroma_client() -> chromadb.PersistentClient:
    os.makedirs(str(VECTORDB_DIR), exist_ok=True)
    return chromadb.PersistentClient(
        path=str(VECTORDB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def get_or_create_collection() -> chromadb.Collection:
    client = get_chroma_client()
    # 如果 collection 已存在就先删掉重建（开发阶段方便迭代）
    try:
        client.delete_collection(CHROMA_COLLECTION)
    except Exception:
        pass
    return client.create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


# ------------------------------------------------------------
# 文案索引
# ------------------------------------------------------------
def index_posts(jsonl_path: str | None = None):
    """
    从 JSONL 文件读取文案，向量化后写入 ChromaDB。
    每行一个 JSON 对象，字段：id, title, content, tags, likes, category, style
    """
    if jsonl_path is None:
        jsonl_path = str(DATA_DIR / "seed_posts.jsonl")

    if not os.path.exists(jsonl_path):
        print(f"[WARN] Data file not found: {jsonl_path}")
        return 0

    # 读取 JSONL
    posts = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                posts.append(json.loads(line))

    if not posts:
        print("[WARN] Data file is empty")
        return 0

    # 准备向量化文本：标题 + 正文前 300 字
    model = get_embedding_model()
    collection = get_or_create_collection()

    ids = []
    documents = []
    metadatas = []
    embeddings = []

    print(f"[INDEX] Vectorizing {len(posts)} posts...")
    for post in posts:
        pid = post["id"]
        doc_text = f"{post['title']}\n{post['content'][:300]}"
        embedding = model.encode(doc_text, normalize_embeddings=True).tolist()

        ids.append(pid)
        documents.append(doc_text)
        metadatas.append({
            "title": post["title"],
            "full_content": post["content"],
            "tags": ", ".join(post.get("tags", [])),
            "likes": post.get("likes", 0),
            "category": post.get("category", ""),
            "style": post.get("style", ""),
        })
        embeddings.append(embedding)

    # 批量写入
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    print(f"[OK] Indexed: {len(posts)} posts")
    return len(posts)


# ------------------------------------------------------------
# 语义检索
# ------------------------------------------------------------
def search_similar(
    query: str,
    top_k: int = RAG_TOP_K,
    category: str | None = None,
) -> list[dict]:
    """
    语义检索最相似文案。

    参数:
        query: 检索查询（如产品描述、关键词）
        top_k: 返回条数
        category: 可选品类过滤（护肤/穿搭/美食）

    返回:
        [{"id", "title", "full_content", "tags", "likes", "category", "style", "score"}, ...]
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(CHROMA_COLLECTION)
    except Exception:
        print("[WARN] Knowledge base is empty, please import data first!")
        return []

    model = get_embedding_model()
    query_embedding = model.encode(query, normalize_embeddings=True).tolist()

    # 构建过滤条件
    where_filter = None
    if category:
        where_filter = {"category": category}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
        include=["metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    posts = []
    for i, pid in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        # cosine distance → similarity (cosine distance ∈ [0, 2]; sim = 1 - distance/2)
        similarity = 1.0 - distance / 2.0

        posts.append({
            "id": pid,
            "title": meta.get("title", ""),
            "full_content": meta.get("full_content", ""),
            "tags": meta.get("tags", ""),
            "likes": meta.get("likes", 0),
            "category": meta.get("category", ""),
            "style": meta.get("style", ""),
            "score": round(similarity, 4),
        })

    return posts


# ------------------------------------------------------------
# 知识库统计
# ------------------------------------------------------------
def get_collection_stats() -> dict:
    """返回知识库统计信息"""
    try:
        client = get_chroma_client()
        collection = client.get_collection(CHROMA_COLLECTION)
        count = collection.count()
        return {
            "loaded": True,
            "count": count,
            "model": EMBEDDING_MODEL,
        }
    except Exception:
        return {
            "loaded": False,
            "count": 0,
            "model": EMBEDDING_MODEL,
        }


# ------------------------------------------------------------
# 自测
# ------------------------------------------------------------
if __name__ == "__main__":
    # 入库
    n = index_posts()
    print(f"\n知识库统计: {get_collection_stats()}\n")

    # 检索测试
    query = "敏感肌面霜推荐，修护皮肤屏障"
    print(f"[SEARCH] Query: {query}")
    results = search_similar(query, top_k=3)
    for r in results:
        print(f"  [{r['score']:.3f}] [{r['category']}] {r['title'][:40]}... (likes:{r['likes']})")
