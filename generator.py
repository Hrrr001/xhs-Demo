"""
内容生成引擎
- LLM 调用生成小红书文案（OpenAI 兼容 API）
- 爆款潜力评分（基于知识库数据）
- 对比模式：同时生成多版本文案
"""

import json
import re
from dataclasses import dataclass, field

from openai import OpenAI

from config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    RAG_TOP_K,
    SCORE_WEIGHTS,
)
from rag_engine import search_similar
from compliance import compliance_summary


# ============================================================
# LLM 客户端
# ============================================================
def _get_llm_client() -> OpenAI:
    return OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


# ============================================================
# Prompt 模板
# ============================================================

SYSTEM_PROMPT = """你是一位资深的小红书企业号内容运营专家，擅长撰写高互动率的种草文案。

你的写作原则：
1. 口语化、有亲近感，像闺蜜在聊天而不是官方广告
2. 善用 emoji 分段，但不过度堆砌
3. 开头要有痛点共鸣或好奇钩子，前3行决定用户会不会点进来
4. 中间输出干货/真实体验，不要空洞的形容词堆砌
5. 结尾引导互动（提问、征集评论）
6. 必须带 #话题标签，3-5个
7. 绝对不使用广告法违禁词（最好、第一、唯一、国家级等）
8. 美妆护肤类不宣称医疗功效（美白、祛斑、消炎等）
9. 不添加微信号、二维码等导流信息

产出格式要求：
- 标题：单独一行，用【】或直接写，要有吸引力
- 正文：自然分段，适当使用 emoji
- 结尾：互动引导 + 话题标签
- 字数：按要求控制"""


def _build_user_prompt(
    product_name: str,
    category: str,
    selling_points: str,
    target_audience: str,
    style: str,
    word_count: int,
    reference_posts: list[dict],
) -> str:
    """组装 user prompt，包含产品信息 + RAG 检索到的爆款参考"""
    
    # 构建爆款参考
    ref_text = ""
    if reference_posts:
        ref_text = "\n\n【爆款文案参考（请学习以下文案的语调、结构和互动技巧，但内容必须原创）】\n"
        for i, ref in enumerate(reference_posts[:3], 1):
            ref_text += f"\n--- 参考 {i}（{ref['style']}，点赞 {ref['likes']}，相似度 {ref['score']:.0%}）---\n"
            ref_text += ref["full_content"][:400]
            ref_text += "\n"

    style_map = {
        "种草笔记": "以第一人称分享使用体验，真实、亲切、突出使用前后的变化",
        "测评合集": "横向对比多个产品/方案，列出优缺点，给出选择建议",
        "教程攻略": "步骤化讲解，像教程一样清晰，适合收藏",
        "避雷拔草": "反向推荐，说哪些不要买/不要做，真实吐槽风格",
        "经验分享": "分享个人经历和心得感悟，注重故事性和情感共鸣",
    }

    prompt = f"""请为以下产品撰写一篇小红书{style}文案：

【产品信息】
- 产品名称：{product_name}
- 品类：{category}
- 核心卖点：{selling_points}
- 目标人群：{target_audience}
- 内容类型：{style}（{style_map.get(style, '自然分享风格')}）
- 字数要求：约{word_count}字
{ref_text}
请直接输出文案内容，不要加任何前缀说明。"""
    
    return prompt


# ============================================================
# 内容生成
# ============================================================
def generate_content(
    product_name: str,
    category: str = "护肤",
    selling_points: str = "",
    target_audience: str = "",
    style: str = "种草笔记",
    word_count: int = 300,
    use_rag: bool = True,
    stream_callback=None,
) -> dict:
    """
    生成小红书文案 + 爆款评分 + 合规初筛。

    返回:
        {
            "content": str,           # 生成的文案
            "references": [...],      # RAG 参考的爆款
            "scores": {...},          # 爆款潜力评分
            "compliance": {...},      # 合规检查摘要
        }
    """
    # 1. RAG 检索
    references = []
    if use_rag:
        ref_query = f"{product_name} {selling_points} {category}"
        references = search_similar(ref_query, top_k=RAG_TOP_K, category=category)
        # 如果指定品类没结果，扩大检索
        if not references:
            references = search_similar(ref_query, top_k=RAG_TOP_K)

    # 2. 组装 Prompt & 调用 LLM
    user_prompt = _build_user_prompt(
        product_name, category, selling_points,
        target_audience, style, word_count, references,
    )

    client = _get_llm_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        if stream_callback:
            # 流式输出
            stream = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0.8,
                max_tokens=min(word_count * 3, 2000),
                stream=True,
            )
            full_content = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_content += chunk.choices[0].delta.content
                    stream_callback(full_content)
            content = full_content
        else:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0.8,
                max_tokens=min(word_count * 3, 2000),
            )
            content = response.choices[0].message.content
    except Exception as e:
        content = f"[生成失败] LLM API 调用出错: {str(e)}\n请检查 .env 中的 API Key 和网络连接。"

    # 3. 爆款潜力评分
    scores = _score_viral_potential(content, references, style)

    # 4. 合规初筛
    comp = compliance_summary(content)

    return {
        "content": content,
        "references": references,
        "scores": scores,
        "compliance": comp,
    }


def generate_comparison(
    product_name: str,
    category: str = "护肤",
    selling_points: str = "",
    target_audience: str = "",
    word_count: int = 300,
    stream_callback=None,
) -> dict:
    """
    对比模式：同时生成 2 版不同风格的文案，并排比较。
    """
    # 版本A：种草笔记
    result_a = generate_content(
        product_name, category, selling_points, target_audience,
        style="种草笔记", word_count=word_count,
        stream_callback=lambda c: stream_callback("A", c) if stream_callback else None,
    )

    # 版本B：测评合集 或 教程攻略
    style_b = "测评合集" if category in ("护肤", "穿搭") else "教程攻略"
    result_b = generate_content(
        product_name, category, selling_points, target_audience,
        style=style_b, word_count=word_count,
        stream_callback=lambda c: stream_callback("B", c) if stream_callback else None,
    )

    return {
        "version_a": {
            "style": "种草笔记",
            "content": result_a["content"],
            "scores": result_a["scores"],
            "compliance": result_a["compliance"],
            "references": result_a["references"],
        },
        "version_b": {
            "style": style_b,
            "content": result_b["content"],
            "scores": result_b["scores"],
            "compliance": result_b["compliance"],
            "references": result_b["references"],
        },
    }


# ============================================================
# 爆款潜力评分
# ============================================================
def _score_viral_potential(content: str, references: list[dict], style: str) -> dict:
    """
    基于启发式规则 + 知识库数据，给文案打出 0-100 分的爆款潜力评分。
    
    评分维度：
    - title_appeal: 标题吸引力（是否有钩子、数字、emoji、情绪词）
    - structure_match: 结构匹配度（与同类爆款的结构相似度）
    - tag_quality: 标签质量（数量是否合理、是否精准）
    - engagement_potential: 互动潜力（是否有互动引导）
    - compliance_bonus: 合规加分（无违规 = 满分）
    """
    weights = SCORE_WEIGHTS
    
    # --- 标题吸引力 ---
    lines = content.strip().split("\n")
    title = lines[0] if lines else ""
    title_score = 50
    if re.search(r"[？！!?]", title):
        title_score += 10
    if re.search(r"\d+", title):
        title_score += 10
    if re.search(r"(居然|竟然|爆|疯了|绝了|救命|求求|千万|别再)", title):
        title_score += 10
    if len(title) >= 10 and len(title) <= 40:
        title_score += 10
    if any(emo in title for emo in ["✨", "🔥", "💎", "🌟", "‼️", "😭", "🥹"]):
        title_score += 10
    title_score = min(100, title_score)

    # --- 结构匹配度 ---
    # 检查是否具备爆款常见结构元素
    struct_score = 40
    if re.search(r"(首先|第[一二三四五]|1[.、]|📌|✅|❌|🏆|💡|✨|🔧)", content):
        struct_score += 15
    if re.search(r"(姐妹们|宝宝们|大家)", content):
        struct_score += 10
    if re.search(r"#\S+", content):
        struct_score += 10
    if re.search(r"(评论区|点赞|收藏|关注)", content):
        struct_score += 10
    if len(content) >= 200 and len(content) <= 800:
        struct_score += 15
    struct_score = min(100, struct_score)

    # --- 标签质量 ---
    tags = re.findall(r"#([\w\u4e00-\u9fff]+)", content)
    tag_score = 40
    if 3 <= len(tags) <= 5:
        tag_score += 30
    elif 1 <= len(tags) <= 2:
        tag_score += 15
    elif len(tags) > 5:
        tag_score += 5
    # 标签是否有高频爆款词
    hot_words = ["穿搭", "护肤", "美食", "测评", "教程", "合集", "避雷", "种草", "分享", "好物", "推荐"]
    match_count = sum(1 for tag in tags if any(hw in tag for hw in hot_words))
    tag_score += match_count * 6
    tag_score = min(100, tag_score)

    # --- 互动潜力 ---
    engagement_score = 30
    if re.search(r"(评论区|评论|留言|说说|聊聊|分享)", content):
        engagement_score += 25
    if re.search(r"(姐妹们|宝子们|大家|你们|各位)", content):
        engagement_score += 15
    if re.search(r"(觉得|怎么样|好不好|有没有|试过|踩过|用过)", content):
        engagement_score += 15
    if re.search(r"\?|？", content):
        engagement_score += 15
    engagement_score = min(100, engagement_score)

    # --- 合规加分 ---
    comp = compliance_summary(content)
    compliance_score = 100 - comp["errors"] * 20 - comp["warnings"] * 10
    compliance_score = max(0, min(100, compliance_score))

    # --- 加权总分 ---
    total = (
        weights["title_appeal"] * title_score +
        weights["structure_match"] * struct_score +
        weights["tag_quality"] * tag_score +
        weights["engagement_potential"] * engagement_score +
        weights["compliance_bonus"] * compliance_score
    )

    # --- 参考爆款对标 ---
    ref_avg_likes = 0
    if references:
        ref_avg_likes = sum(r.get("likes", 0) for r in references) / len(references)
    
    # 爆款等级
    if total >= 85:
        level = "S级 · 爆款预定"
        level_emoji = "🔥🔥🔥"
    elif total >= 70:
        level = "A级 · 优质内容"
        level_emoji = "🔥🔥"
    elif total >= 55:
        level = "B级 · 合格内容"
        level_emoji = "🔥"
    else:
        level = "C级 · 需要优化"
        level_emoji = "💪"

    return {
        "total": round(total, 1),
        "level": level,
        "level_emoji": level_emoji,
        "dimensions": {
            "title_appeal": {"score": title_score, "label": "标题吸引力", "weight": weights["title_appeal"]},
            "structure_match": {"score": struct_score, "label": "结构匹配度", "weight": weights["structure_match"]},
            "tag_quality": {"score": tag_score, "label": "标签质量", "weight": weights["tag_quality"]},
            "engagement_potential": {"score": engagement_score, "label": "互动潜力", "weight": weights["engagement_potential"]},
            "compliance_bonus": {"score": compliance_score, "label": "合规加分", "weight": weights["compliance_bonus"]},
        },
        "ref_avg_likes": round(ref_avg_likes),
        "ref_count": len(references),
    }


# ============================================================
# 测试（需要配置 API Key）
# ============================================================
if __name__ == "__main__":
    test_result = generate_content(
        product_name="某品牌神经酰胺修护面霜",
        category="护肤",
        selling_points="含神经酰胺+积雪草，修护皮肤屏障，敏感肌可用，质地清爽不油腻",
        target_audience="25-35岁敏感肌女性",
        style="种草笔记",
        word_count=300,
    )
    print("=" * 60)
    print("生成结果:\n")
    print(test_result["content"][:500])
    print(f"\n--- 评分 ---")
    print(json.dumps(test_result["scores"], ensure_ascii=False, indent=2))
    print(f"\n--- 合规 ---")
    print(f"违规总数: {test_result['compliance']['total']} (严重: {test_result['compliance']['errors']}, 警告: {test_result['compliance']['warnings']})")
