"""
Hugging Face Spaces 入口
HF Spaces 自动查找 app.py 作为 Gradio 应用入口
"""
from rag_engine import index_posts, get_collection_stats
from main import build_ui

# 首次启动自动索引种子数据
stats = get_collection_stats()
if not stats["loaded"]:
    print("[HF] First run, indexing seed data...")
    index_posts()
print(f"[HF] Knowledge base: {get_collection_stats()}")

app = build_ui()

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
