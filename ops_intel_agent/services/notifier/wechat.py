"""WeChat Work (企业微信) group-bot notifier.

Posts a Markdown card to the configured webhook. Action buttons are encoded as
numbered inline hints because the webhook Markdown format has no native button
support; a real deployment pairs this with the interactive callback message
type, which is out of scope for the open-source scaffold.
"""

from __future__ import annotations

import httpx

from .base import Notifier

_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"


class WeChatNotifier(Notifier):
    def __init__(self, webhook: str | None) -> None:
        if not webhook:
            raise ValueError("WeChat notifier requires OIA_WECHAT_WEBHOOK")
        # Accept either the full URL or just the key.
        self._url = webhook if webhook.startswith("http") else _WEBHOOK.format(key=webhook)

    async def send(self, payload) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            body = {
                "msgtype": "markdown",
                "markdown": {"content": f"## {payload.title}\n{payload.markdown}"},
            }
            resp = await client.post(self._url, json=body)
            resp.raise_for_status()
            return {"ok": True, "channel": "wechat", "raw": resp.json()}
