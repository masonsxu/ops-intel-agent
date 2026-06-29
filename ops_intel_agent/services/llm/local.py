"""Offline, template-based LLM provider.

Generates genuinely useful, deterministic output for *both* the triage and the
knowledge-deposition prompts, so the full pipeline is demonstrable without an
API key. Output strictly follows the same Markdown contracts the real LLM is
prompted to produce, so downstream parsing is identical.
"""

from __future__ import annotations

from .base import LLMProvider

_TRIAGE_MARKER = "当前原始日志:"
_DEPOSITION_MARKER = "工程师处理记录:"


class LocalLLMProvider(LLMProvider):
    async def complete(self, system: str, user: str) -> str:
        if _DEPOSITION_MARKER in user:
            return _render_deposition(user)
        return _render_triage(user)


# === Triage ================================================================
def _render_triage(user_prompt: str) -> str:
    current_log = _grab(user_prompt, "当前原始日志:\n```", "\n```")
    history_blocks: list[tuple[str, str]] = []
    cursor = 0
    while True:
        i = user_prompt.find("【历史经验#", cursor)
        if i < 0:
            break
        cursor = i + 1
        h_log_start = user_prompt.find("历史日志:", i)
        h_sol_start = user_prompt.find("当时解决办法:", i)
        h_block_end = user_prompt.find("---", i)
        if h_block_end == -1:
            h_block_end = len(user_prompt)
        h_log = (
            user_prompt[h_log_start + len("历史日志:") : h_sol_start].strip()
            if h_log_start != -1 and h_sol_start != -1
            else ""
        )
        h_sol = (
            user_prompt[h_sol_start + len("当时解决办法:") : h_block_end].strip()
            if h_sol_start != -1
            else ""
        )
        history_blocks.append((h_log, h_sol))

    best_sol = history_blocks[0][1] if history_blocks else ""
    best_log = history_blocks[0][0] if history_blocks else ""

    plain = _plain_language(current_log)
    user_actions = (
        "如果您正在使用相关功能，请稍候 1-2 分钟后重试。\n"
        "如情况紧急，请回复 **1** 触发自动重启；非紧急可等待工程师自动修复。\n"
        "您也可以拨打一线值班热线：4000-XXX-XXX。"
    )
    eng = best_sol or (
        "1. 确认服务进程与依赖组件（数据库 / 缓存 / 消息队列）状态；\n"
        "2. 查看监控大盘，定位异常发生的时间窗口与影响范围；\n"
        "3. 必要时执行回滚或重启，并保留现场日志供事后复盘。"
    )
    if best_log:
        eng = f"参考历史相似案例（{best_log[:80]}…）：\n" + eng

    return (
        "📢 【当前问题大白话翻译】\n"
        f"{plain}\n\n"
        "🛠️ 【您可以采取的行动】\n"
        f"{user_actions}\n\n"
        "👨‍💻 【技术排查参考（供工程师）】\n"
        f"{eng}\n"
    )


def _plain_language(log: str) -> str:
    log_l = log.lower()
    if "redis" in log_l and ("timeout" in log_l or "refused" in log_l or "oom" in log_l):
        return (
            "后台缓存服务（Redis）出现了短暂故障，可能导致部分页面加载缓慢、"
            "登录状态丢失或验证码刷新失败，系统正在尝试自动恢复。"
        )
    if "gpu" in log_l or ("inference" in log_l):
        return (
            "AI 推理服务出现异常，可能导致智能推荐、图像识别等功能暂时不可用或结果异常，"
            "工程师正在处理。"
        )
    if "mysql" in log_l or "database" in log_l or "hikari" in log_l or "connection" in log_l:
        return (
            "后台数据库连接出现异常，可能导致提交订单、保存数据等操作失败，"
            "工程师正在紧急处理，请您稍后重试。"
        )
    if "oom" in log_l or "outofmemory" in log_l or "heap" in log_l:
        return (
            "后台服务内存资源临时耗尽，系统可能会自动重启相关模块，"
            "期间相关功能会有几秒钟不可用，请稍后重试。"
        )
    if "disk" in log_l or "nospace" in log_l or "no space" in log_l:
        return "服务器存储空间已满，正在自动清理，期间文件上传/生成功能可能暂时不可用。"
    if "certif" in log_l or "ssl" in log_l or "tls" in log_l:
        return "安全证书相关配置异常，可能导致部分接口访问失败，工程师正在更新证书。"
    return (
        "后台监测到一处服务异常，相关功能可能暂时不可用或响应变慢，"
        "工程师已收到通知并在处理中，给您带来不便非常抱歉。"
    )


# === Deposition ============================================================
def _render_deposition(user_prompt: str) -> str:
    root_cause = _grab(user_prompt, "- 根因: ", "\n")
    resolution = _grab(user_prompt, "- 解决办法: ", "\n")

    user_guide = _plain_language_for_root(root_cause)
    return (
        f"【错误类型】: {_guess_type(root_cause, user_prompt)}\n"
        f"【标题】: {_short_title(root_cause)}\n"
        f"【根因】: {root_cause}\n"
        f"【用户指引】: {user_guide}\n"
        f"【工程师指引】: {resolution}\n"
    )


def _guess_type(root_cause: str, user_prompt: str) -> str:
    text = (root_cause + " " + user_prompt).lower()
    # Most-specific signals first so "tensor cache + GPU" classifies as GPU.
    if "gpu" in text or "显存" in text:
        return "GPU 显存异常"
    if "kafka" in text or "积压" in text:
        return "消息队列积压"
    if "oom" in text or "outofmemory" in text or "heap" in text or "jvm" in text:
        return "JVM 内存溢出"
    if "mysql" in text or "数据库" in text or "hikari" in text or "连接池" in text:
        return "数据库连接异常"
    if "redis" in text or "缓存" in text:
        return "Redis 缓存异常"
    return "服务异常"


def _short_title(root_cause: str) -> str:
    return (root_cause[:40] + "…") if len(root_cause) > 40 else root_cause


def _plain_language_for_root(root_cause: str) -> str:
    rc = root_cause.lower()
    if "gpu" in rc or "显存" in rc:
        return "AI 推理服务出现异常，智能推荐/识别类功能可能暂时不可用，工程师正在处理。"
    if "redis" in rc or "缓存" in rc:
        return "后台缓存服务短暂异常，可能导致登录态丢失或页面变慢，请稍后重试。"
    if "内存" in rc or "oom" in rc:
        return "后台服务内存临时耗尽，系统正在自动恢复，相关功能请稍后重试。"
    return "相关服务出现异常，工程师已介入处理，给您带来不便敬请谅解。"


# === helpers ===============================================================
def _grab(text: str, start_marker: str, end_marker: str) -> str:
    i = text.find(start_marker)
    if i < 0:
        return ""
    rest = text[i + len(start_marker) :]
    j = rest.find(end_marker)
    if j < 0:
        return rest.strip()
    return rest[:j].strip()
