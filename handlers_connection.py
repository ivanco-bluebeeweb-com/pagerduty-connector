"""Connection management: connect/disconnect PagerDuty accounts, save/list/
delete per-service Integration Keys for Events API v2 / Change Events API.
Same shape as MuleSoft Connector's connection handlers -- async, one secret
holding a JSON array per store, ActionResult.success()/.error().
"""
from __future__ import annotations

import json
import uuid

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import ext, chat
from schemas import (
    NoParams,
    ConnectPagerdutyParams, ProviderConnection, ProviderConnectionList,
    DisconnectPagerdutyParams, DeleteResult,
    SaveIntegrationKeyParams, IntegrationKeyEntry, IntegrationKeyList,
    DeleteIntegrationKeyParams,
)

_CONN_SECRET = "pagerduty_connections"
_KEYS_SECRET = "pagerduty_integration_keys"


async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_CONN_SECRET)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _save_connections(ctx, items: list[dict]) -> None:
    await ctx.secrets.set(_CONN_SECRET, json.dumps(items))


async def _load_keys(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_KEYS_SECRET)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _save_keys(ctx, items: list[dict]) -> None:
    await ctx.secrets.set(_KEYS_SECRET, json.dumps(items))


async def resolve_connection(ctx, connection_id: str = "") -> dict | None:
    conns = await _load_connections(ctx)
    if not conns:
        return None
    if connection_id:
        for c in conns:
            if c.get("id") == connection_id:
                return c
        return None
    return conns[0]


async def resolve_or_error(ctx, connection_id: str = ""):
    """Shared guard: resolve a connection or return the standard
    'not connected' ActionResult.error. Returns (conn, error_or_None)."""
    conn = await resolve_connection(ctx, connection_id)
    if conn is None:
        return None, ActionResult.error(
            "No PagerDuty account is connected yet. Use connect_pagerduty first.",
            code="PAGERDUTY_ACCOUNT_MISSING",
        )
    return conn, None


def _connection_to_entity(c: dict) -> ProviderConnection:
    return ProviderConnection(
        id=c.get("id", ""), title=c.get("label") or "PagerDuty account",
        connected=True, detail=f"key ...{c.get('api_key', '')[-4:]}" if c.get("api_key") else "",
        subdomain=c.get("subdomain", ""),
    )


@chat.function(
    "connect_pagerduty",
    "Connect your own PagerDuty account by saving your REST API key, after "
    "checking it actually works. Get a key from PagerDuty: Integrations > "
    "Developer Tools > API Access Keys > Create New API Key.",
    action_type="write",
    chain_callable=True,
    data_model=ProviderConnection,
    event="pagerduty-connector.connect_pagerduty",
    effects=["pagerduty.provider.connected"],
)
async def connect_pagerduty(ctx, params: ConnectPagerdutyParams) -> ActionResult:
    """Connect your own PagerDuty account by saving your REST API key."""
    api_key = (params.api_key or "").strip()
    if not api_key:
        return ActionResult.error("Please paste your PagerDuty REST API key.", code="PAGERDUTY_MISSING_FIELD")

    try:
        await pc.validate_rest_key(ctx, api_key)
    except pc.ClientFail as e:
        return ActionResult.error(str(e), code="PAGERDUTY_CONNECT_FAILED")

    conns = await _load_connections(ctx)
    new_id = uuid.uuid4().hex[:12]
    record = {
        "id": new_id,
        "api_key": api_key,
        "from_email": (params.from_email or "").strip(),
        "label": (params.label or "").strip() or "PagerDuty account",
    }
    conns.append(record)
    await _save_connections(ctx, conns)
    return ActionResult.success(
        _connection_to_entity(record),
        f"Connected PagerDuty account '{record['label']}'.",
        refresh_panels=["pagerduty_sidebar", "pagerduty_settings"],
    )


@chat.function(
    "list_connections",
    "List the connected PagerDuty accounts and whether each saved REST API key still works.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
    event="pagerduty-connector.list_connections",
)
async def list_connections(ctx, params: NoParams) -> ActionResult:
    """List the connected PagerDuty accounts."""
    conns = await _load_connections(ctx)
    items = []
    for c in conns:
        ok, detail = True, "Connected"
        try:
            await pc.validate_rest_key(ctx, c.get("api_key", ""))
        except pc.ClientFail as e:
            ok, detail = False, str(e)
        items.append(ProviderConnection(
            id=c.get("id", ""), title=c.get("label", ""),
            connected=ok, detail=detail, subdomain=c.get("subdomain", ""),
        ))
    return ActionResult.success(ProviderConnectionList(items=items), f"{len(items)} account(s) connected.")


@chat.function(
    "disconnect_pagerduty",
    "Disconnect a PagerDuty account: deletes the saved REST API key. Nothing "
    "in PagerDuty itself is changed; the account's own incidents, services, "
    "and configuration are untouched.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.disconnect_pagerduty",
    effects=["pagerduty.provider.disconnected"],
)
async def disconnect_pagerduty(ctx, params: DisconnectPagerdutyParams) -> ActionResult:
    """Disconnect a PagerDuty account."""
    conns = await _load_connections(ctx)
    remaining = [c for c in conns if c.get("id") != params.connection_id]
    if len(remaining) == len(conns):
        return ActionResult.error("Connection not found.", code="PAGERDUTY_NOT_FOUND")
    await _save_connections(ctx, remaining)
    return ActionResult.success(
        DeleteResult(ok=True, detail="Disconnected."), "Account disconnected.",
        refresh_panels=["pagerduty_sidebar", "pagerduty_settings"],
    )


@chat.function(
    "save_integration_key",
    "Save a per-service Integration Key (routing key) used by Events API v2 "
    "and/or Change Events API. Find it on the service's Integrations tab in "
    "PagerDuty -- each integration (e.g. 'Events API v2') has its own key.",
    action_type="write",
    chain_callable=True,
    data_model=IntegrationKeyEntry,
    event="pagerduty-connector.save_integration_key",
    effects=["pagerduty.integration_key.saved"],
)
async def save_integration_key(ctx, params: SaveIntegrationKeyParams) -> ActionResult:
    """Save a per-service Integration Key (routing key)."""
    key = (params.integration_key or "").strip()
    if not key:
        return ActionResult.error("Please paste the Integration Key (routing key).", code="PAGERDUTY_MISSING_FIELD")
    keys = await _load_keys(ctx)
    new_id = uuid.uuid4().hex[:12]
    record = {
        "id": new_id,
        "service_id": (params.service_id or "").strip(),
        "routing_key": key,
        "label": (params.label or "").strip() or "Integration key",
        "kind": params.kind or "events",
    }
    keys.append(record)
    await _save_keys(ctx, keys)
    return ActionResult.success(
        IntegrationKeyEntry(
            id=new_id, service_id=record["service_id"], kind=record["kind"],
            label=record["label"], masked_key="..." + key[-4:] if len(key) >= 4 else "***",
        ),
        f"Saved Integration Key '{record['label']}'.",
        refresh_panels=["pagerduty_settings"],
    )


@chat.function(
    "list_integration_keys",
    "List saved per-service Integration Keys (routing keys) for Events API v2 / "
    "Change Events API. Keys themselves are never echoed back in full.",
    action_type="read",
    chain_callable=True,
    data_model=IntegrationKeyList,
    event="pagerduty-connector.list_integration_keys",
)
async def list_integration_keys(ctx, params: NoParams) -> ActionResult:
    """List saved per-service Integration Keys."""
    keys = await _load_keys(ctx)
    items = [
        IntegrationKeyEntry(
            id=k.get("id", ""), service_id=k.get("service_id", ""),
            label=k.get("label", ""), kind=k.get("kind", "events"),
            masked_key=("..." + k.get("routing_key", "")[-4:]) if k.get("routing_key") else "",
        )
        for k in keys
    ]
    return ActionResult.success(IntegrationKeyList(items=items), f"{len(items)} integration key(s) saved.")


@chat.function(
    "delete_integration_key",
    "Permanently delete a saved Integration Key. Does not affect anything in "
    "PagerDuty itself -- only removes it from Imperal's storage.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_integration_key",
    effects=["pagerduty.integration_key.deleted"],
)
async def delete_integration_key(ctx, params: DeleteIntegrationKeyParams) -> ActionResult:
    """Permanently delete a saved Integration Key."""
    keys = await _load_keys(ctx)
    remaining = [k for k in keys if k.get("id") != params.key_id]
    if len(remaining) == len(keys):
        return ActionResult.error("Integration key not found.", code="PAGERDUTY_NOT_FOUND")
    await _save_keys(ctx, remaining)
    return ActionResult.success(
        DeleteResult(ok=True, detail="Integration key deleted."), "Integration key deleted.",
        refresh_panels=["pagerduty_settings"],
    )
