"""Webhook Subscriptions (PagerDuty -> our endpoint push notifications).
Async, full @chat.function metadata, ActionResult.success()/.error() --
same shape as MuleSoft Connector's handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListWebhookSubscriptionsParams, WebhookSubscriptionEntry, WebhookSubscriptionList,
    CreateWebhookSubscriptionParams, GetWebhookSubscriptionParams,
    UpdateWebhookSubscriptionParams, DeleteWebhookSubscriptionParams,
    PingWebhookSubscriptionParams,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


def _wh_from(raw: dict) -> WebhookSubscriptionEntry:
    filt = raw.get("filter") or {}
    events = raw.get("events") or []
    return WebhookSubscriptionEntry(
        id=raw.get("id", ""), description=raw.get("description") or "",
        delivery_url=raw.get("delivery_method", {}).get("url", "") if raw.get("delivery_method") else "",
        events=", ".join(events), active=bool(raw.get("active", True)),
        filter_type=filt.get("type", ""), filter_id=filt.get("id", ""),
    )


@chat.function(
    "list_webhook_subscriptions",
    "List webhook subscriptions (Webhooks v3) configured on the connected PagerDuty account -- which events push notifications to which URL.",
    action_type="read",
    chain_callable=True,
    data_model=WebhookSubscriptionList,
    event="pagerduty-connector.list_webhook_subscriptions",
)
async def list_webhook_subscriptions(ctx, params: ListWebhookSubscriptionsParams) -> ActionResult:
    """List webhook subscriptions."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/webhook_subscriptions", conn["api_key"], "webhook_subscriptions")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [_wh_from(w) for w in rows]
    return ActionResult.success(WebhookSubscriptionList(items=items), f"{len(items)} webhook subscription(s).")


@chat.function(
    "create_webhook_subscription",
    "Subscribe to PagerDuty events (e.g. incident.triggered, incident.acknowledged, incident.resolved) so PagerDuty POSTs them to your URL as they happen.",
    action_type="write",
    chain_callable=True,
    data_model=WebhookSubscriptionEntry,
    event="pagerduty-connector.create_webhook_subscription",
    effects=["pagerduty.webhook_subscription.created"],
)
async def create_webhook_subscription(ctx, params: CreateWebhookSubscriptionParams) -> ActionResult:
    """Create a webhook subscription."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.delivery_url or not params.events:
        return ActionResult.error("Please provide a delivery URL and at least one event type.")
    events = [e.strip() for e in params.events.split(",") if e.strip()]
    payload: dict = {"webhook_subscription": {
        "delivery_method": {"type": "http_delivery_method", "url": params.delivery_url},
        "description": params.description or "Imperal PagerDuty webhook",
        "events": events,
        "active": True,
        "type": "webhook_subscription",
    }}
    if params.filter_type and params.filter_id:
        payload["webhook_subscription"]["filter"] = {"type": params.filter_type, "id": params.filter_id}
    try:
        body = await pc.rest_request(ctx, "POST", "/webhook_subscriptions", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    w = body.get("webhook_subscription", {})
    return ActionResult.success(
        _wh_from(w), f"Webhook subscription created (id {w.get('id', '')}).",
        refresh_panels=["pd_webhooks"],
    )


@chat.function(
    "get_webhook_subscription",
    "Read one webhook subscription's full configuration.",
    action_type="read",
    chain_callable=True,
    data_model=WebhookSubscriptionEntry,
    event="pagerduty-connector.get_webhook_subscription",
)
async def get_webhook_subscription(ctx, params: GetWebhookSubscriptionParams) -> ActionResult:
    """Read one webhook subscription."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/webhook_subscriptions/{params.webhook_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    entity = _wh_from(body.get("webhook_subscription", {}))
    return ActionResult.success(entity, f"Webhook subscription {entity.id}.")


@chat.function(
    "update_webhook_subscription",
    "Change a webhook subscription's URL, event list, and/or active state.",
    action_type="write",
    chain_callable=True,
    data_model=WebhookSubscriptionEntry,
    event="pagerduty-connector.update_webhook_subscription",
    effects=["pagerduty.webhook_subscription.updated"],
)
async def update_webhook_subscription(ctx, params: UpdateWebhookSubscriptionParams) -> ActionResult:
    """Update a webhook subscription."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        current = await pc.rest_request(ctx, "GET", f"/webhook_subscriptions/{params.webhook_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    wh = current.get("webhook_subscription", {})
    if params.delivery_url:
        wh.setdefault("delivery_method", {"type": "http_delivery_method"})["url"] = params.delivery_url
    if params.events:
        wh["events"] = [e.strip() for e in params.events.split(",") if e.strip()]
    if params.active is not None:
        wh["active"] = params.active
    try:
        await pc.rest_request(ctx, "PUT", f"/webhook_subscriptions/{params.webhook_id}", conn["api_key"],
                               json_body={"webhook_subscription": wh})
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success(_wh_from(wh), "Webhook subscription updated.", refresh_panels=["pd_webhooks"])


@chat.function(
    "delete_webhook_subscription",
    "Permanently remove a webhook subscription. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_webhook_subscription",
    effects=["pagerduty.webhook_subscription.deleted"],
)
async def delete_webhook_subscription(ctx, params: DeleteWebhookSubscriptionParams) -> ActionResult:
    """Delete a webhook subscription."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/webhook_subscriptions/{params.webhook_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Webhook subscription deleted.", refresh_panels=["pd_webhooks"])


@chat.function(
    "ping_webhook_subscription",
    "Send a test ping event to a webhook subscription so you can confirm your endpoint receives it.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.ping_webhook_subscription",
    effects=["pagerduty.webhook_subscription.pinged"],
)
async def ping_webhook_subscription(ctx, params: PingWebhookSubscriptionParams) -> ActionResult:
    """Send a test ping."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "POST", f"/webhook_subscriptions/{params.webhook_id}/ping", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Test ping sent to the webhook endpoint.")
