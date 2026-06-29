"""Schemas for remediation actions."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ActionSpec(BaseModel):
    """A remediation action offered as an inline button on the bot message."""

    name: str
    label: str = Field(..., description="Button label shown to users")
    description: str
    risk_level: str = "low"
    # Opaque params carried back to the action endpoint on click.
    params: dict[str, str] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class ActionInvocationRead(BaseModel):
    id: int
    action_name: str
    alert_id: int | None = None
    target: str | None = None
    triggered_by: str
    status: str
    result: str | None = None

    model_config = {"from_attributes": True}
