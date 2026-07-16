"""
合规校验引擎
- 基于 YAML 规则做正则匹配
- 返回违规列表：位置、类别、严重程度、修改建议
- 预留 LLM 二次审核接口
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field

RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


@dataclass
class Violation:
    rule_id: str
    category: str
    severity: str          # error / warning
    description: str
    suggestion: str
    matched_text: str
    position: int          # 匹配位置（字符偏移）
    context: str           # 匹配处前后20字上下文


def load_rules() -> list[dict]:
    """加载并编译规则（每次调用重新读取，支持热更新）"""
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules = []
    for r in data["rules"]:
        rules.append({
            "id": r["id"],
            "category": r["category"],
            "severity": r["severity"],
            "pattern": re.compile(r["pattern"]),
            "description": r["description"],
            "suggestion": r["suggestion"],
        })
    return rules


def check_compliance(text: str) -> list[Violation]:
    """
    对文本执行全部合规规则检查。
    返回 Violation 列表，按严重程度排序（error 在前）。
    同一规则下匹配到的相同词语只保留第一次出现（去重）。
    """
    rules = load_rules()
    violations: list[Violation] = []
    seen: set[tuple] = set()  # (rule_id, matched_text) 去重

    for rule in rules:
        for m in rule["pattern"].finditer(text):
            matched = m.group(0)
            dedup_key = (rule["id"], matched)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            start = m.start()
            end = m.end()
            # 截取上下文（前后各20字符）
            ctx_start = max(0, start - 20)
            ctx_end = min(len(text), end + 20)
            context = text[ctx_start:ctx_end]

            violations.append(Violation(
                rule_id=rule["id"],
                category=rule["category"],
                severity=rule["severity"],
                description=rule["description"],
                suggestion=rule["suggestion"],
                matched_text=matched,
                position=start,
                context=context,
            ))

    # 排序：error > warning，同级别按位置
    severity_order = {"error": 0, "warning": 1}
    violations.sort(key=lambda v: (severity_order.get(v.severity, 99), v.position))
    return violations


def compliance_summary(text: str) -> dict:
    """
    返回合规检查摘要（给前端展示用）。
    """
    violations = check_compliance(text)
    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]
    return {
        "total": len(violations),
        "errors": len(errors),
        "warnings": len(warnings),
        "passed": len(violations) == 0,
        "violations": [
            {
                "rule_id": v.rule_id,
                "category": v.category,
                "severity": v.severity,
                "description": v.description,
                "suggestion": v.suggestion,
                "matched_text": v.matched_text,
                "context": v.context,
            }
            for v in violations
        ],
    }


def llm_second_review(text: str, violations: list[Violation], llm_client=None) -> list[Violation]:
    """
    LLM 二次审核（预留接口）。
    对规则引擎标记的违规项，调用 LLM 做上下文敏感判断，减少误报。
    例如："第一印象" 中的 "第一" 不应被判为违禁词。

    参数 llm_client 需要支持 chat.completions.create 接口。
    返回过滤后的 violations 列表。
    """
    if not llm_client or not violations:
        return violations

    # TODO: 实现 LLM 二次审核逻辑
    # 将每个违规项 + 上下文发给 LLM，让 LLM 判断是否真的违规
    return violations


# ============================================================
# 自测
# ============================================================
if __name__ == "__main__":
    test_texts = [
        "这是全网最好用的面霜！7天见效，美白祛斑效果立竿见影！加微信xxx了解更多～",
        "换季护肤小tips｜敏感肌也能用的温和面霜分享，保湿效果真的不错哦～",
        "全网第一的减肥神器！不运动不吃药，一周瘦10斤！加V: xxx 了解更多",
    ]
    for i, t in enumerate(test_texts, 1):
        print(f"\n{'='*60}")
        print(f"测试 {i}: {t[:50]}...")
        s = compliance_summary(t)
        print(f"总计 {s['total']} 条违规（{s['errors']} 严重 / {s['warnings']} 警告）")
        for v in s["violations"]:
            print(f"  [{v['severity'].upper()}] {v['category']}: 匹配「{v['matched_text']}」→ {v['suggestion']}")
