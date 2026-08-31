"""Best-effort notification delivery for autonomous runtime events."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.orchestrator.runtime_config import NotificationSettings


class Notifier:
    """Deliver structured events to a webhook when configured, otherwise stderr."""

    def __init__(
        self,
        settings: NotificationSettings,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._environment = os.environ if environment is None else environment

    def send(self, kind: str, message: str, payload: Mapping[str, Any]) -> bool:
        """Deliver one enabled event without ever raising into the workflow."""
        if not self._event_enabled(kind):
            return False
        event = {
            "kind": kind,
            "message": message,
            "payload": dict(payload),
        }
        provider = self._provider()
        if provider == "console":
            print(json.dumps({"notification": event}, sort_keys=True), file=sys.stderr)
            return True

        url = self._environment.get(self._settings.webhook_url_env, "")
        if not url:
            print(
                json.dumps(
                    {
                        "notification_delivery_failed": {
                            "kind": kind,
                            "reason": f"{self._settings.webhook_url_env} is not configured",
                        }
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return False
        request = Request(
            url,
            data=json.dumps(event).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                return 200 <= response.status < 300
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            print(
                json.dumps(
                    {
                        "notification_delivery_failed": {
                            "kind": kind,
                            "reason": str(exc),
                        }
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return False

    def _provider(self) -> str:
        if self._settings.provider != "auto":
            return self._settings.provider
        return "webhook" if self._environment.get(self._settings.webhook_url_env, "") else "console"

    def _event_enabled(self, kind: str) -> bool:
        if not self._settings.enabled:
            return False
        enabled = {
            "daily_report": self._settings.daily_report_enabled,
            "critical_error": self._settings.critical_error_enabled,
            "usage_limit_stop": self._settings.usage_limit_stop_enabled,
            "autonomy_stopped": self._settings.autonomy_stopped_enabled,
        }
        return enabled.get(kind, True)
