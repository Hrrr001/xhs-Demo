"""
小红书内容生成 + 合规校验 — Gradio 交互界面

Tab 1: 文案生成（双版本对比模式）
Tab 2: 合规校验（独立检查）
Tab 3: 数据管理（导入/知识库状态）
"""

import sys
import os
import time

# 强制输出 UTF-8（Windows 兼容）
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import gradio as gr

from config import LLM_MODEL
from rag_engine import index_posts, get_collection_stats, search_similar
from generator import generate_comparison, generate_content, _score_viral_potential
from compliance import compliance_summary


# ============================================================
# 界面样式
# ============================================================
CUSTOM_CSS = """
.container { max-width: 1200px; margin: auto; }
.score-s { background: linear-gradient(135deg, #FF6B6B, #FF8E53); color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; }
.score-a { background: linear-gradient(135deg, #FFA726, #FFCA28); color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; }
.score-b { background: linear-gradient(135deg, #66BB6A, #43A047); color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; }
.violation-error { background: #ffebee; border-left: 4px solid #f44336; padding: 8px 12px; margin: 4px 0; border-radius: 4px; }
.violation-warning { background: #fff8e1; border-left: 4px solid #ff9800; padding: 8px 12px; margin: 4px 0; border-radius: 4px; }
.scroll-textarea textarea { max-height: 380px !important; overflow-y: auto !important; resize: vertical !important; }
"""

HEADER_HTML = """
<div style="text-align: center; padding: 20px 0 10px 0;">
    <h1>小红书写手 · 爆款决策助手</h1>
    <p style="color: #666; font-size: 16px;">
        基于 <b>15条真实爆款文案</b> 的 RAG 知识库 | 
        Embedding: BAAI/bge-small-zh-v1.5 | 
        LLM: {llm_model}
    </p>
</div>
""".format(llm_model=LLM_MODEL)


# ============================================================
# 回调函数
# ============================================================

def on_generate_comparison(
    product_name, category, selling_points, target_audience, word_count,
    progress=gr.Progress(),
):
    """对比生成两版文案"""
    if not product_name.strip():
        yield "请输入产品名称", "等待生成...", "等待生成...", "", {}, {}, {}, ""
        return

    progress(0.1, desc="RAG 检索中...")
    
    version_a_content = ""
    version_b_content = ""
    current_version = "A"
    
    def stream_cb(ver, text):
        nonlocal version_a_content, version_b_content
        if ver == "A":
            version_a_content = text
        else:
            version_b_content = text
    
    progress(0.3, desc="AI 创作中...")
    time.sleep(0.1)
    
    result = generate_comparison(
        product_name=product_name,
        category=category,
        selling_points=selling_points,
        target_audience=target_audience,
        word_count=int(word_count),
        stream_callback=stream_cb,
    )
    
    progress(0.9, desc="评分+合规检查中...")
    
    va = result["version_a"]
    vb = result["version_b"]
    
    # 版本A评分HTML
    scores_a_html = _build_score_html(va["scores"], va["compliance"])
    scores_b_html = _build_score_html(vb["scores"], vb["compliance"])
    
    # 参考文案HTML
    refs_html = _build_references_html(va["references"])
    
    # 两版对比汇总
    compare_html = _build_compare_summary(result)
    
    progress(1.0, desc="完成!")
    
    yield (
        va["content"],           # content_a
        vb["content"],           # content_b
        compare_html,            # compare_summary
        scores_a_html,           # scores_a
        scores_b_html,           # scores_b
        refs_html,               # references
        _build_compliance_html(va["compliance"]),   # compliance_a
        _build_compliance_html(vb["compliance"]),   # compliance_b
    )


def on_generate_single(
    product_name, category, selling_points, target_audience, style, word_count,
    progress=gr.Progress(),
):
    """单版本生成（用于合规Tab之后的演示）"""
    if not product_name.strip():
        return "请输入产品名称", {}, {}
    
    progress(0.3, desc="检索+生成中...")
    result = generate_content(
        product_name=product_name,
        category=category,
        selling_points=selling_points,
        target_audience=target_audience,
        style=style,
        word_count=int(word_count),
    )
    
    progress(0.9, desc="评分中...")
    scores_html = _build_score_html(result["scores"], result["compliance"])
    comp_html = _build_compliance_html(result["compliance"])
    refs_html = _build_references_html(result["references"])
    
    progress(1.0, desc="完成!")
    return result["content"], scores_html, comp_html, refs_html


def on_check_compliance(text):
    """独立合规校验"""
    if not text.strip():
        return "请粘贴文案内容", {}
    result = compliance_summary(text)
    return _build_compliance_html(result), result


def on_import_data(progress=gr.Progress()):
    """导入数据到知识库"""
    progress(0.2, desc="读取数据文件...")
    n = index_posts()
    progress(0.8, desc="向量化入库...")
    stats = get_collection_stats()
    progress(1.0, desc="完成!")
    return f"导入完成！知识库现有 {stats['count']} 条文案", stats


def on_search_kb(query, category):
    """知识库检索"""
    if not query.strip():
        return "请输入搜索关键词"
    results = search_similar(query, category=category if category != "全部" else None)
    if not results:
        return "未找到相似文案"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. [{r['category']}] {r['title']}")
        lines.append(f"相似度: {r['score']:.1%} | 点赞: {r['likes']} | 类型: {r['style']}")
        lines.append(f"标签: {r['tags']}")
        lines.append(f"> {r['full_content'][:200]}...")
        lines.append("")
    return "\n".join(lines)


# ============================================================
# HTML 构建辅助
# ============================================================

def _build_score_html(scores: dict, compliance: dict) -> str:
    """构建评分卡片 HTML"""
    dims = scores.get("dimensions", {})
    rows = ""
    for key, d in dims.items():
        color = "#4caf50" if d["score"] >= 70 else ("#ff9800" if d["score"] >= 50 else "#f44336")
        rows += f"""
        <tr>
            <td style="padding:4px 8px;">{d['label']}</td>
            <td style="padding:4px 8px; width:150px;">
                <div style="background:#eee; border-radius:10px; height:18px;">
                    <div style="background:{color}; width:{d['score']}%; height:100%; border-radius:10px; text-align:center; color:white; font-size:11px; line-height:18px;">{d['score']}</div>
                </div>
            </td>
            <td style="padding:4px 8px; font-size:12px; color:#999;">权重 {d['weight']:.0%}</td>
        </tr>"""
    
    level_color = {"S": "#FF6B6B", "A": "#FFA726", "B": "#66BB6A", "C": "#9E9E9E"}
    lvl = scores.get("level", "")[0]
    
    return f"""
    <div style="border:1px solid #e0e0e0; border-radius:12px; padding:16px;">
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
            <span style="font-size:48px; font-weight:bold; color:{level_color.get(lvl, '#666')};">{scores.get('total', 0)}</span>
            <div>
                <div style="font-size:18px; font-weight:bold;">{scores.get('level_emoji', '')} {scores.get('level', '')}</div>
                <div style="font-size:12px; color:#999;">参考 {scores.get('ref_count', 0)} 条爆款 (均赞 {scores.get('ref_avg_likes', 0):,}) | 合规: {compliance.get('errors', 0)}误</div>
            </div>
        </div>
        <table style="width:100%;">{rows}</table>
    </div>"""


def _build_compliance_html(compliance: dict) -> str:
    """构建合规检查结果 HTML"""
    if compliance.get("passed"):
        return '<div style="color:#4caf50; font-size:18px; padding:12px;">合规通过，未检测到违规内容</div>'
    
    html = f'<div style="font-size:14px; margin-bottom:8px;">检测到 <b>{compliance["total"]}</b> 条问题（<span style="color:#f44336;">{compliance["errors"]} 严重</span> / <span style="color:#ff9800;">{compliance["warnings"]} 警告</span>）</div>'
    
    for v in compliance.get("violations", []):
        cls = "violation-error" if v["severity"] == "error" else "violation-warning"
        badge = '<span style="background:#f44336; color:white; padding:2px 8px; border-radius:4px; font-size:12px;">严重</span>' if v["severity"] == "error" else '<span style="background:#ff9800; color:white; padding:2px 8px; border-radius:4px; font-size:12px;">警告</span>'
        html += f"""
        <div class="{cls}">
            <div style="display:flex; gap:8px; align-items:center;">
                {badge}
                <b>{v['category']}</b>
                <span style="color:#999; font-size:12px;">{v['rule_id']}</span>
            </div>
            <div style="margin:4px 0;">匹配: <code style="background:#fff; padding:2px 6px; border-radius:3px;">{v['matched_text']}</code></div>
            <div style="color:#666; font-size:13px;">{v['description']}</div>
            <div style="color:#1976d2; font-size:13px;">建议: {v['suggestion']}</div>
        </div>"""
    return html


def _build_references_html(references: list) -> str:
    """构建参考爆款 HTML"""
    if not references:
        return '<div style="color:#999;">未找到相关爆款参考（知识库可能为空）</div>'
    html = ""
    for i, r in enumerate(references, 1):
        html += f"""
        <div style="border:1px solid #e0e0e0; border-radius:8px; padding:10px; margin-bottom:8px;">
            <div style="font-weight:bold;">#{i} [{r['category']}] {r['title']}</div>
            <div style="font-size:12px; color:#999;">相似度 {r['score']:.1%} | 点赞 {r['likes']:,} | {r['style']}</div>
            <div style="font-size:12px; color:#666; margin-top:4px;">标签: {r['tags']}</div>
        </div>"""
    return html


def _build_compare_summary(result: dict) -> str:
    """两版对比汇总 HTML"""
    va = result["version_a"]
    vb = result["version_b"]
    
    better = "A" if va["scores"]["total"] >= vb["scores"]["total"] else "B"
    diff = abs(va["scores"]["total"] - vb["scores"]["total"])
    
    return f"""
    <div style="text-align:center; padding:16px; background:#f5f5f5; border-radius:12px;">
        <div style="font-size:20px; font-weight:bold; margin-bottom:8px;">
            版本{better}更优，领先 <span style="color:#f44336;">{diff:.1f} 分</span>
        </div>
        <div style="display:flex; justify-content:center; gap:24px;">
            <div>
                <div style="font-size:14px; color:#999;">版本A · 种草笔记</div>
                <div style="font-size:36px; font-weight:bold;">{va['scores']['total']}</div>
            </div>
            <div style="font-size:36px; color:#999;">VS</div>
            <div>
                <div style="font-size:14px; color:#999;">版本B · {vb['style']}</div>
                <div style="font-size:36px; font-weight:bold;">{vb['scores']['total']}</div>
            </div>
        </div>
        <div style="margin-top:8px; font-size:12px; color:#999;">
            合规: A版 {va['compliance']['errors']} 误 / B版 {vb['compliance']['errors']} 误 | 
            参考 {va['scores']['ref_count']} 条爆款
        </div>
    </div>"""


# ============================================================
# Gradio UI 构建
# ============================================================
def build_ui():
    with gr.Blocks(
        title="小红书写手 · 爆款决策助手",
    ) as app:
        gr.HTML(HEADER_HTML)

        with gr.Tabs():
            # ============ Tab 1: 对比生成 ============
            with gr.TabItem("对比生成", id="tab_generate"):
                gr.Markdown("输入产品信息，AI 将基于爆款知识库同时生成两版文案并打分对比。")

                with gr.Row():
                    with gr.Column(scale=1):
                        product_name = gr.Textbox(
                            label="产品名称",
                            placeholder="例如：XX品牌神经酰胺修护面霜",
                        )
                        category = gr.Dropdown(
                            label="品类",
                            choices=["护肤", "穿搭", "美食", "家居", "数码", "母婴", "其他"],
                            value="护肤",
                        )
                        selling_points = gr.Textbox(
                            label="核心卖点",
                            placeholder="例如：含神经酰胺+积雪草，修护皮肤屏障，敏感肌可用",
                            lines=3,
                        )
                        target_audience = gr.Textbox(
                            label="目标人群",
                            placeholder="例如：25-35岁敏感肌女性",
                        )
                        word_count = gr.Slider(
                            label="字数要求",
                            minimum=150,
                            maximum=800,
                            value=300,
                            step=50,
                        )
                        gen_btn = gr.Button("生成双版对比", variant="primary", size="lg")

                    with gr.Column(scale=2):
                        compare_summary = gr.HTML(label="对比结果")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### 版本A · 种草笔记")
                        content_a = gr.Textbox(label="文案内容", lines=10, elem_classes="scroll-textarea")
                        scores_a = gr.HTML(label="爆款潜力评分")
                        compliance_a = gr.HTML(label="合规检查")

                    with gr.Column():
                        gr.Markdown("### 版本B · 测评合集")
                        content_b = gr.Textbox(label="文案内容", lines=10, elem_classes="scroll-textarea")
                        scores_b = gr.HTML(label="爆款潜力评分")
                        compliance_b = gr.HTML(label="合规检查")

                with gr.Accordion("参考的爆款文案", open=False):
                    references = gr.HTML()

                gen_btn.click(
                    fn=on_generate_comparison,
                    inputs=[product_name, category, selling_points, target_audience, word_count],
                    outputs=[content_a, content_b, compare_summary, scores_a, scores_b, references, compliance_a, compliance_b],
                )

            # ============ Tab 2: 合规校验 ============
            with gr.TabItem("合规校验", id="tab_compliance"):
                gr.Markdown("独立合规检查工具：粘贴任意文案，一键检测广告法违禁词、行业红线和平台规范违规。")

                comp_input = gr.Textbox(
                    label="粘贴待检测文案",
                    placeholder="在小红书文案粘贴到这里...",
                    lines=10,
                )
                comp_btn = gr.Button("开始校验", variant="primary")
                comp_output = gr.HTML(label="检测结果")

                comp_btn.click(
                    fn=on_check_compliance,
                    inputs=[comp_input],
                    outputs=[comp_output],
                )

            # ============ Tab 3: 数据管理 ============
            with gr.TabItem("数据管理", id="tab_data"):
                gr.Markdown("管理爆款文案知识库：导入种子数据、查看检索效果。")

                with gr.Row():
                    with gr.Column(scale=1):
                        import_btn = gr.Button("导入种子数据到知识库", variant="secondary")
                        import_status = gr.Textbox(label="状态", lines=2)
                        kb_stats = gr.JSON(label="知识库统计")

                    with gr.Column(scale=2):
                        kb_query = gr.Textbox(label="检索关键词", placeholder="输入关键词测试知识库检索...")
                        kb_category = gr.Dropdown(
                            label="品类过滤",
                            choices=["全部", "护肤", "穿搭", "美食"],
                            value="全部",
                        )
                        kb_search_btn = gr.Button("检索")
                        kb_results = gr.Markdown(label="检索结果")

                import_btn.click(
                    fn=on_import_data,
                    outputs=[import_status, kb_stats],
                )
                kb_search_btn.click(
                    fn=on_search_kb,
                    inputs=[kb_query, kb_category],
                    outputs=[kb_results],
                )

                # 页面加载时自动刷新知识库状态
                app.load(
                    fn=get_collection_stats,
                    outputs=[kb_stats],
                )

    return app


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    app = build_ui()
    # 启动前确保数据已入库
    stats = get_collection_stats()
    if not stats["loaded"]:
        print("[INIT] Importing seed data...")
        index_posts()
    print(f"[INIT] Knowledge base: {get_collection_stats()}")
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        inbrowser=False,
        css=CUSTOM_CSS,
        theme=gr.themes.Soft(),
    )
