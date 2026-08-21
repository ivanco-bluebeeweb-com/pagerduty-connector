"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), SAME REASONING AS MuleSoft Connector /
Stripe Connector / Automation Anywhere Connector.

PagerDuty is the user's OWN incident-management account -- Imperal cannot
and should not broker access to someone else's on-call/escalation setup
centrally. The user pastes their own REST API key once, Vault-encrypted
via `ctx.secrets`, and every call runs against their own PagerDuty account.

WHY A PLAIN TOKEN KEY (REST API key), NOT OAUTH2, FOR THE PRIMARY
CONNECTION -- SAME REASONING AS Stripe Connector.

PagerDuty's REST API v2 authenticates with a single API key sent as
`Authorization: Token token=<key>` (support.pagerduty.com/main/docs/
api-access-keys, confirmed during Discovery 2026-08-21) -- there is no
client-credentials or authorization-code dance needed for a user managing
their OWN account. `connect_pagerduty` validates the pasted key against
`GET /abilities` (cheap, always-available call) and stores it.

WHY A SEPARATE, PER-SERVICE SECRET STORE FOR INTEGRATION KEYS
(routing_key), NOT THE SAME FIELD AS THE REST API KEY.

Events API v2 and Change Events API do NOT use the REST API key at all
-- they use a `routing_key` scoped to one specific Service Integration
(developer.pagerduty.com/docs/events-api-v2/trigger-events/, confirmed
2026-08-21). A user may want to send events for several different
services from Imperal, so integration keys are stored as a named JSON
array (`save_integration_key` / `list_integration_keys` /
`delete_integration_key`), same "one secret holding a JSON array"
precedent as MuleSoft Connector's multi-environment connections.

WHY ONE SECRET HOLDING A JSON ARRAY FOR CONNECTIONS TOO, SAME PRECEDENT
AS MuleSoft Connector / Power Automate Connector.

A user may have more than one PagerDuty account (e.g. one per client, if
this is used by an MSP). `ctx.secrets` only supports a fixed,
manifest-declared set of NAMES -- there is no "one secret per connection"
primitive, so `pagerduty_connections` holds a JSON array of
`{id, label, api_key, from_email, subdomain}` objects, and every tool's
`connection_id` parameter addresses one entry in that array -- see
handlers_connection.py's `_load_connections`/`_save_connections` helpers.
"""
from __future__ import annotations

from imperal_sdk import ChatExtension, Extension

ext = Extension(
    "pagerduty-connector",
    version="0.1.0",
    display_name="PagerDuty",
    description=(
        "Connect your own PagerDuty account to manage incident response "
        "from Imperal -- list/create/acknowledge/resolve/reassign/merge/"
        "snooze incidents, manage services and escalation policies, "
        "on-call schedules, users and teams, business services and "
        "service dependencies, tags and custom fields, event "
        "orchestration and incident workflows, automation actions, "
        "webhook subscriptions, and send/acknowledge/resolve alerts and "
        "change events via Events API v2. Uses your own REST API key and "
        "per-service Integration Keys -- nothing is hosted or proxied by "
        "Imperal beyond the request itself."
    ),
    icon="icon.svg",
    capabilities=[
        "pagerduty:read",
        "pagerduty:write",
    ],
    actions_explicit=True,
    system=False,
)

chat = ChatExtension(
    ext,
    tool_name="pagerduty",
    description=(
        "PagerDuty Connector -- connect your own PagerDuty account via "
        "your REST API key, then manage incidents, services, escalation "
        "policies, on-call schedules, users, teams, business services, "
        "tags, custom fields, event orchestration, incident workflows, "
        "automation actions, webhooks, and send/acknowledge/resolve "
        "events and change events."
    ),
)

ext.secret(
    "pagerduty_connections",
    (
        "Your connected PagerDuty accounts -- stored as a JSON array, one "
        "entry per account, each with its own REST API key. Managed "
        "through connect_pagerduty / disconnect_pagerduty -- you should "
        "not need to edit this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=180,
)(lambda: None)

ext.secret(
    "pagerduty_integration_keys",
    (
        "Your saved per-service Integration Keys (routing keys) for "
        "Events API v2 / Change Events API -- stored as a JSON array. "
        "Managed through save_integration_key / delete_integration_key."
    ),
    required=False,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=180,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one account connection is stored, same shape as MuleSoft
    Connector's health_check."""
    import json as _json
    raw = await ctx.secrets.get("pagerduty_connections")
    try:
        count = len(_json.loads(raw)) if raw else 0
    except Exception:
        count = 0
    return {
        "healthy": True,
        "detail": (
            f"{count} PagerDuty account(s) connected." if count
            else "Not connected yet -- run connect_pagerduty."
        ),
    }
