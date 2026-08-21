"""Events API v2 (send/ack/resolve alerts from external monitoring) and
Change Events API (track deploys/changes). Both use a routing_key (per-
service Integration Key saved via handlers_connection.save_integration_key),
NOT the REST API key. Async, full @chat.function metadata,
ActionResult.success()/.error() -- same shape as MuleSoft Connector's
handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import _load_keys
from schemas import TriggerEventParams, AckOrResolveEventParams, EventResult, SendChangeEventParams, ChangeEventResult

_NO_KEY = "No routing key -- save one with save_integration_key or pass routing_key directly."


async def _resolve_routing_key(ctx, integration_key_id: str, routing_key: str) -> str | None:
    if routing_key:
        return routing_key
    if not integration_key_id:
        return None
    for k in await _load_keys(ctx):
        if k.get("id") == integration_key_id:
            return k.get("routing_key")
    return None


@chat.function(
    "trigger_event",
    "Send a new alert into PagerDuty via Events API v2 -- creates (or adds to) an incident on the service tied to the given integration key. Provide either integration_key_id (from list_integration_keys) or a raw routing_key directly.",
    action_type="write",
    chain_callable=True,
    data_model=EventResult,
    event="pagerduty-connector.trigger_event",
    effects=["pagerduty.event.triggered"],
)
async def trigger_event(ctx, params: TriggerEventParams) -> ActionResult:
    """Trigger a new alert via Events API v2."""
    key = await _resolve_routing_key(ctx, params.integration_key_id, params.routing_key)
    if not key:
        return ActionResult.error(_NO_KEY)
    payload: dict = {
        "routing_key": key,
        "event_action": "trigger",
        "payload": {
            "summary": params.summary,
            "source": params.source or "Imperal",
            "severity": params.severity or "error",
        },
    }
    if params.component:
        payload["payload"]["component"] = params.component
    if params.group:
        payload["payload"]["group"] = params.group
    if params.custom_details:
        payload["payload"]["custom_details"] = {"detail": params.custom_details}
    if params.dedup_key:
        payload["dedup_key"] = params.dedup_key
    try:
        body = await pc.events_request(ctx, payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    dedup_key = body.get("dedup_key", "")
    return ActionResult.success(
        EventResult(ok=True, dedup_key=dedup_key, detail="Event triggered."),
        f"Event triggered (dedup_key {dedup_key}).",
    )


@chat.function(
    "ack_or_resolve_event",
    "Acknowledge or resolve an existing alert via Events API v2, using the dedup_key returned by trigger_event (or your own external key).",
    action_type="write",
    chain_callable=True,
    data_model=EventResult,
    event="pagerduty-connector.ack_or_resolve_event",
    effects=["pagerduty.event.updated"],
)
async def ack_or_resolve_event(ctx, params: AckOrResolveEventParams) -> ActionResult:
    """Acknowledge or resolve an alert via Events API v2."""
    key = await _resolve_routing_key(ctx, params.integration_key_id, params.routing_key)
    if not key:
        return ActionResult.error(_NO_KEY)
    if params.event_action not in ("acknowledge", "resolve"):
        return ActionResult.error("event_action must be 'acknowledge' or 'resolve'.")
    payload = {"routing_key": key, "event_action": params.event_action, "dedup_key": params.dedup_key}
    try:
        body = await pc.events_request(ctx, payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    dedup_key = body.get("dedup_key", params.dedup_key)
    return ActionResult.success(
        EventResult(ok=True, dedup_key=dedup_key, detail=f"Event {params.event_action}d."),
        f"Event {params.event_action}d.",
    )


@chat.function(
    "send_change_event",
    "Send a change event (e.g. a deploy) to PagerDuty's Change Events API -- tracked alongside incidents for correlation, without creating an incident itself. Provide either integration_key_id or a raw routing_key.",
    action_type="write",
    chain_callable=True,
    data_model=ChangeEventResult,
    event="pagerduty-connector.send_change_event",
    effects=["pagerduty.change_event.sent"],
)
async def send_change_event(ctx, params: SendChangeEventParams) -> ActionResult:
    """Send a change event via Change Events API."""
    key = await _resolve_routing_key(ctx, params.integration_key_id, params.routing_key)
    if not key:
        return ActionResult.error(_NO_KEY)
    payload: dict = {
        "routing_key": key,
        "payload": {
            "summary": params.summary,
            "source": params.source or "Imperal",
        },
    }
    if params.custom_details:
        payload["payload"]["custom_details"] = {"detail": params.custom_details}
    if params.link_url:
        payload["links"] = [{"href": params.link_url, "text": params.link_text or "Details"}]
    try:
        body = await pc.change_events_request(ctx, payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success(
        ChangeEventResult(ok=True, id=body.get("id", ""), detail="Change event recorded."),
        "Change event recorded.",
    )
