from __future__ import annotations

from datetime import time

import pytest

from scripts.orchestrator.notifications import Notifier
from scripts.orchestrator.runtime_config import NotificationSettings


def settings(provider: str = "auto") -> NotificationSettings:
    return NotificationSettings(
        enabled=True,
        provider=provider,
        webhook_url_env="ORCHESTRATOR_NOTIFICATION_WEBHOOK_URL",
        daily_report_enabled=True,
        daily_report_time=time(21, 0),
        critical_error_enabled=True,
        usage_limit_stop_enabled=True,
        autonomy_stopped_enabled=True,
    )


def test_auto_falls_back_to_console_without_webhook(
    capsys: pytest.CaptureFixture[str],
) -> None:
    notifier = Notifier(settings(), environment={})
    assert notifier.send("critical_error", "boom", {"x": 1}) is True
    assert '"kind": "critical_error"' in capsys.readouterr().err


def test_disabled_event_is_not_sent(capsys: pytest.CaptureFixture[str]) -> None:
    configured = settings()
    configured = NotificationSettings(
        enabled=True,
        provider=configured.provider,
        webhook_url_env=configured.webhook_url_env,
        daily_report_enabled=configured.daily_report_enabled,
        daily_report_time=configured.daily_report_time,
        critical_error_enabled=False,
        usage_limit_stop_enabled=configured.usage_limit_stop_enabled,
        autonomy_stopped_enabled=configured.autonomy_stopped_enabled,
    )
    notifier = Notifier(configured, environment={})
    assert notifier.send("critical_error", "boom", {}) is False
    assert capsys.readouterr().err == ""
