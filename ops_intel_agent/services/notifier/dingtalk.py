"""DingTalk (钉钉) custom-robot notifier with optional signature."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx

from .base import Notifier


class DingTalkNotifier(Notifier):
    def __init__(self, webhook: str | None, secret: str | None) -> None:
        if not webhook:
            raise ValueError("DingTalk notifier requires OIA_DINGTALK_WEBHOOK")
        self._webhook = webhook
        self._secret = secret

    def _signed_url(self) -> str:
        if not self._secret:
            return self._webhook
        ts = str(round(time.time() * 1000))
        string_to_sign = f"{ts}\n{self._secret}"
        hmac_code = hmac.new(
            self._secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        sep = "&" if "?" in self._webhook else "?"
        return f"{self._webhook}{sep}timestamp={ts}&sign={sign}"

    async def send(self, payload) -> dict:
        url = self._signed_url()
        body = {
            "msgtype": "markdown",
            "markdown": {"title": payload.title, "text": payload.markdown},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return {"ok": True, "channel": "dingtalk", "raw": resp.json()}
