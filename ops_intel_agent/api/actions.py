"""Execute remediation actions offered by the bot."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ActionInvocation
from ..services.actions import ActionContext, get_action_registry
from .deps import db_session

router = APIRouter(prefix="/actions", tags=["actions"])


class ActionRequest(BaseModel):
    action_name: str
    target: str | None = None
    params: dict[str, str] = {}
    triggered_by: str = "user"
    alert_id: int | None = None
    knowledge_id: int | None = None


@router.get("", summary="List available remediation actions")
async def list_actions() -> list[dict]:
    reg = get_action_registry()
    return [s.model_dump() for s in reg.specs()]


@router.post("/invoke", summary="Run a remediation action")
async def invoke_action(req: ActionRequest, session: AsyncSession = Depends(db_session)) -> dict:
    reg = get_action_registry()
    spec = reg.get_spec(req.action_name)
    if spec is None:
        raise HTTPException(404, f"unknown action: {req.action_name}")
    ctx = ActionContext(
        target=req.target,
        params=req.params,
        triggered_by=req.triggered_by,
        alert_id=req.alert_id,
        knowledge_id=req.knowledge_id,
    )
    result = await reg.execute(req.action_name, ctx)
    inv = ActionInvocation(
        action_name=req.action_name,
        alert_id=req.alert_id,
        knowledge_id=req.knowledge_id,
        target=req.target,
        triggered_by=req.triggered_by,
        status="ok" if result.ok else "failed",
        result=result.message,
    )
    session.add(inv)
    await session.commit()
    return {
        "ok": result.ok,
        "message": result.message,
        "spec": spec.model_dump(),
        "invocation_id": inv.id,
    }
