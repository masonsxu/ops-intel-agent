"""Remediation-action registry: the bridge between LLM suggestions and
executable automation (the "function calling" surface).

Actions are registered with metadata (risk level, button label) so the bot can
offer safe ones as inline buttons and gate dangerous ones behind explicit
confirmation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ...schemas.action import ActionSpec


@dataclass(slots=True)
class ActionContext:
    target: str | None
    params: dict[str, str]
    triggered_by: str = "bot"
    alert_id: int | None = None
    knowledge_id: int | None = None


@dataclass(slots=True)
class ActionResult:
    ok: bool
    message: str
    data: dict = field(default_factory=dict)


ActionHandler = Callable[[ActionContext], "Awaitable[ActionResult]"]


class ActionRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}
        self._meta: dict[str, ActionSpec] = {}

    def register(
        self,
        name: str,
        label: str,
        description: str,
        handler: ActionHandler,
        risk_level: str = "low",
    ) -> None:
        self._handlers[name] = handler
        self._meta[name] = ActionSpec(
            name=name,
            label=label,
            description=description,
            risk_level=risk_level,
        )

    def specs(self) -> list[ActionSpec]:
        return list(self._meta.values())

    def get_spec(self, name: str) -> ActionSpec | None:
        return self._meta.get(name)

    async def execute(self, name: str, ctx: ActionContext) -> ActionResult:
        handler = self._handlers.get(name)
        if handler is None:
            return ActionResult(ok=False, message=f"unknown action: {name}")
        try:
            return await handler(ctx)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(ok=False, message=f"action failed: {exc}")

    def suggest_for(
        self, root_cause_text: str, confidence: float, threshold: float
    ) -> list[ActionSpec]:
        """Pick which actions to surface as buttons for a given incident."""
        text = root_cause_text.lower()
        picks: list[tuple[str, str]] = []  # (name, risk)
        if any(k in text for k in ("redis", "cache", "缓存")):
            picks.append(("clear_cache", "low"))
            picks.append(("restart_service", "low"))
        if any(k in text for k in ("oom", "outofmemory", "heap", "内存")):
            picks.append(("scale_up", "medium"))
            picks.append(("restart_service", "low"))
        if any(k in text for k in ("rollback", "版本", "deploy", "release")):
            picks.append(("rollback", "high"))
        if not picks:
            picks.append(("notify_oncall", "low"))
        # Only offer actions when we are reasonably confident.
        if confidence < threshold:
            picks = [p for p in picks if p[1] == "low"] or [("notify_oncall", "low")]
        specs: list[ActionSpec] = []
        seen: set[str] = set()
        for name, _risk in picks:
            if name in seen:
                continue
            seen.add(name)
            spec = self._meta.get(name)
            if spec:
                specs.append(spec)
        return specs


def _build_default_registry() -> ActionRegistry:
    from . import builtin

    reg = ActionRegistry()
    reg.register(
        "restart_service", "一键重启服务", "重启受影响的服务进程/容器", builtin.restart_service
    )
    reg.register("clear_cache", "清空缓存", "清空 Redis 缓存", builtin.clear_cache)
    reg.register("scale_up", "扩容 +1", "扩容服务副本数", builtin.scale_up, risk_level="medium")
    reg.register("rollback", "回滚版本", "回滚到上一版本", builtin.rollback, risk_level="high")
    reg.register("notify_oncall", "升级通知", "电话/企微通知值班高级工程师", builtin.notify_oncall)
    return reg


_registry: ActionRegistry | None = None


def get_action_registry() -> ActionRegistry:
    global _registry
    if _registry is None:
        _registry = _build_default_registry()
    return _registry
