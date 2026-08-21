"""Entrypoint for the web-kernel and CLI tools (imperal validate/build).

Sets up sys.path, purges stale module cache, then imports ext/chat and all
handler modules so their decorators register on the same Extension instance
-- same pattern as MuleSoft Connector's / Stripe Connector's main.py.
"""

import os
import sys

_EXT_DIR = os.path.dirname(os.path.abspath(__file__))
if _EXT_DIR not in sys.path:
    sys.path.insert(0, _EXT_DIR)

_LOCAL = (
    "app", "schemas", "pagerduty_client",
    "handlers_connection", "handlers_incidents", "handlers_services",
    "handlers_schedules", "handlers_users_teams", "handlers_business_tags",
    "handlers_orchestration_workflows", "handlers_automation",
    "handlers_webhooks", "handlers_events", "handlers_analytics",
    "panels", "panels_settings",
)
for _mod in _LOCAL:
    sys.modules.pop(_mod, None)

from app import ext, chat  # noqa: E402,F401
import handlers_connection  # noqa: E402,F401
import handlers_incidents  # noqa: E402,F401
import handlers_services  # noqa: E402,F401
import handlers_schedules  # noqa: E402,F401
import handlers_users_teams  # noqa: E402,F401
import handlers_business_tags  # noqa: E402,F401
import handlers_orchestration_workflows  # noqa: E402,F401
import handlers_automation  # noqa: E402,F401
import handlers_webhooks  # noqa: E402,F401
import handlers_events  # noqa: E402,F401
import handlers_analytics  # noqa: E402,F401
import panels  # noqa: E402,F401
import panels_settings  # noqa: E402,F401
