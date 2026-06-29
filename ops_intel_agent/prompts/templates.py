"""Prompt templates and structured-output parsers.

The triage prompt is deliberately strict about output format so the same
parser works for both the local (template) provider and the real OpenAI model.
Sections are emitted under fixed Chinese headers so they survive translation.
"""

from __future__ import annotations

import re

# === Triage ================================================================

TRIAGE_SYSTEM = """\
你是一名资深的 IT 运维架构师与全能沟通专家。
你的任务：结合历史相似故障的处理经验，对当前服务器异常进行分析，
并为工作群里的不同角色生成通知。

你必须严格遵守以下输出契约，输出 Markdown 且只能包含三个小节，
每个小节使用指定的标题（含 emoji，原样保留）：

📢 【当前问题大白话翻译】
    用非技术人员能听懂的语言描述「影响」。绝对禁止出现技术堆栈、
    异常类名、IP、端口号、代码片段。例如：
    "目前登录功能暂时不可用，原因是后台缓存服务短暂断开，正在自动恢复。"

🛠️ 【您可以采取的行动】
    清晰、具体、可操作的下一步。例如："如果急需使用，请回复 '1' 触发
    自动重启；若不紧急请等待工程师修复。也可拨打一线热线 4000-XXX-XXX。"

👨‍💻 【技术排查参考（供工程师）】
    保留专业术语，给一线 SRE 看：根因假设、要检查的指标、可执行的命令。

只输出这三节，不要输出额外说明、不要输出 JSON。"""


def build_triage_prompt(ctx: dict) -> tuple[str, str]:
    """Return (system, user). ctx keys: current_log, retrieval, matched, ..."""
    current_log = ctx["current_log"]
    retrieval = ctx.get("retrieval") or []
    matched = ctx.get("matched", False)

    blocks = []
    for i, r in enumerate(retrieval, 1):
        blocks.append(
            f"【历史经验#{i}】 (相似度 {r['similarity']:.2f})\n"
            f"历史日志: {r.get('raw_log') or r.get('title', '')}\n"
            f"当时解决办法: {r.get('engineer_guide') or r.get('solution', '')}\n"
            "---"
        )
    history = "\n".join(blocks) if blocks else "(无相似历史经验，这是一个全新故障。)"

    guidance = (
        "这是一个已知问题，请充分参考历史经验，给出自信、精确的行动建议。"
        if matched
        else "这是一个首次出现的问题。在【大白话翻译】中如实告知正在排查；"
        "在【技术排查参考】中给出通用的、结构化的排查路径。"
    )

    user = (
        f"当前原始日志:\n```\n{current_log}\n```\n\n"
        f"系统检索到的历史相似经验:\n{history}\n\n"
        f"匹配状态: {'已匹配历史经验' if matched else '首次出现/无高置信匹配'}\n"
        f"指导: {guidance}\n"
    )
    if ctx.get("cluster_summary"):
        user += f"\n聚合上下文: {ctx['cluster_summary']}\n"
    return TRIAGE_SYSTEM, user


_PLAIN_RE = re.compile(r"📢\s*【当前问题大白话翻译】\s*(.*?)(?=🛠️|👨‍💻|\Z)", re.S)
_USER_ACT_RE = re.compile(r"🛠️\s*【您可以采取的行动】\s*(.*?)(?=👨‍💻|\Z)", re.S)
_ENG_RE = re.compile(r"👨‍💻\s*【技术排查参考（供工程师）】\s*(.*)\Z", re.S)


def parse_triage_markdown(raw: str) -> dict:
    plain = _PLAIN_RE.search(raw)
    uact = _USER_ACT_RE.search(raw)
    eng = _ENG_RE.search(raw)

    def clean(m) -> str:
        return (m.group(1).strip() if m else "").strip("` \n")

    return {
        "plain_language": clean(plain) or raw.strip(),
        "user_actions": clean(uact),
        "engineer_guide": clean(eng),
    }


# === Deposition ============================================================

DEPOSITION_SYSTEM = """\
你是一名运维知识库管理员。工程师刚刚解决了一起线上故障，并留下了口语化的
处理记录。你的任务：把这段记录结构化为知识库条目，以便未来同类故障能被自动
检索复用。

严格输出如下 Markdown 小节（标题原样保留），不要输出多余内容：

【错误类型】: 一句话分类，如 "Redis 连接超时"
【标题】: 20 字以内的故障标题
【根因】: 技术性根因说明
【用户指引】: 非技术人员能懂的影响说明 + 建议动作
【工程师指引】: 复现条件、检查项、修复步骤、关键命令"""


def build_deposition_prompt(req, raw_log: str) -> tuple[str, str]:
    user = (
        f"工程师处理记录:\n"
        f"- 根因: {req.root_cause}\n"
        f"- 解决办法: {req.resolution}\n"
        f"- 工程师: {req.engineer}\n"
        f"- 标签: {', '.join(req.tags) if req.tags else '(无)'}\n\n"
        f"触发该处理的原始日志:\n```\n{raw_log}\n```\n"
    )
    return DEPOSITION_SYSTEM, user


def parse_deposition_markdown(raw: str) -> dict:
    fields = {
        "error_type": r"【错误类型】\s*:\s*(.*)",
        "title": r"【标题】\s*:\s*(.*)",
        "root_cause": r"【根因】\s*:\s*(.*)",
        "user_guide": r"【用户指引】\s*:\s*(.*)",
        "engineer_guide": r"【工程师指引】\s*:\s*(.*)",
    }
    out = {}
    for key, pat in fields.items():
        m = re.search(pat, raw)
        out[key] = m.group(1).strip() if m else None
    return out
