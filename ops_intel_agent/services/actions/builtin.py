"""Built-in remediation actions.

Each action is a pure coroutine that receives a target and arbitrary params.
In production these shell out to Ansible / kubectl / internal runbooks; here
they are safe no-ops that record what *would* happen, so the demo never
mutates real infrastructure.
"""

from __future__ import annotations

import asyncio

from .registry import ActionContext, ActionResult


async def restart_service(ctx: ActionContext) -> ActionResult:
    target = ctx.params.get("target") or ctx.target or "unknown-service"
    await asyncio.sleep(0.05)  # simulate
    return ActionResult(
        ok=True,
        message=f"重启指令已下发：{target}（kubectl rollout restart / systemctl restart）",
    )


async def clear_cache(ctx: ActionContext) -> ActionResult:
    target = ctx.params.get("target") or "redis"
    await asyncio.sleep(0.05)
    return ActionResult(ok=True, message=f"已清空 {target} 缓存（FLUSHDB 指令已执行）。")


async def scale_up(ctx: ActionContext) -> ActionResult:
    target = ctx.params.get("target") or "deployment/api"
    await asyncio.sleep(0.05)
    return ActionResult(ok=True, message=f"已将 {target} 副本数 +1，等待就绪。")


async def rollback(ctx: ActionContext) -> ActionResult:
    target = ctx.params.get("target") or "deployment/api"
    await asyncio.sleep(0.05)
    return ActionResult(ok=True, message=f"已触发 {target} 回滚到上一可用版本。")


async def notify_oncall(ctx: ActionContext) -> ActionResult:
    await asyncio.sleep(0.02)
    return ActionResult(ok=True, message="已电话/企微升级通知值班高级工程师。")
