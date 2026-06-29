"""Abstract notifier + factory."""

from __future__ import annotations

import abc

from ...schemas.report import NotificationPayload


class Notifier(abc.ABC):
    @abc.abstractmethod
    async def send(self, payload: NotificationPayload) -> dict: ...


_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        from ...config import get_settings

        settings = get_settings()
        if settings.notifier_provider == "wechat":
            from .wechat import WeChatNotifier

            _notifier = WeChatNotifier(settings.wechat_webhook)
        elif settings.notifier_provider == "dingtalk":
            from .dingtalk import DingTalkNotifier

            _notifier = DingTalkNotifier(settings.dingtalk_webhook, settings.dingtalk_secret)
        else:
            from .console import ConsoleNotifier

            _notifier = ConsoleNotifier()
    return _notifier
