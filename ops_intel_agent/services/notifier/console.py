"""Stdout notifier — the default for local development."""

from __future__ import annotations

from .base import Notifier


class ConsoleNotifier(Notifier):
    async def send(self, payload) -> dict:
        bar = "=" * 78
        actions = "".join(
            f"   🔘 [{a.label}]  risk={a.risk_level}  action={a.name}\n"
            for a in payload.suggested_actions
        )
        print(  # noqa: T201
            f"\n{bar}\n"
            f"📨 {payload.title}\n"
            f"{bar}\n"
            f"{payload.markdown}\n" + (f"\n按钮:\n{actions}" if actions else "") + f"{bar}\n",
            flush=True,
        )
        return {"ok": True, "channel": "console", "audience": "stdout"}
