"""PagerDuty HTTP client -- three distinct auth surfaces, one shared request
helper per surface, thin wrappers over REST API v2, Events API v2 and
Change Events API. Same shape as mulesoft_client.py's fail()/ClientFail
pattern -- uses the platform's own `ctx.http` (async), never `requests`.

WHY THREE SEPARATE BASE URLS / AUTH SCHEMES, NOT ONE.

PagerDuty genuinely has no single API (confirmed CONNECTOR_DISCOVERY.md,
2026-08-21):
  - REST API v2 (api.pagerduty.com) -- configuration CRUD. Auth: a REST
    API key sent as `Authorization: Token token=<key>` (NOT Bearer --
    PagerDuty's REST API v2 explicitly uses its own `Token token=` scheme,
    support.pagerduty.com/main/docs/api-access-keys, confirmed 2026-08-21).
  - Events API v2 (events.pagerduty.com/v2/enqueue) -- send/ack/resolve
    alerts from external monitoring. Auth: a `routing_key` (the Service's
    Integration Key) carried IN THE JSON BODY, not a header at all.
  - Change Events API (events.pagerduty.com/v2/change/enqueue) -- track
    deploys/changes outside the incident flow. Same body-embedded
    `routing_key` shape as Events API v2, but a distinct endpoint and a
    distinct integration key value (a service can have separate Events
    and Change Events integrations).

Mixing these up silently produces confusing 400s (right shape, wrong
endpoint) or 401s (right endpoint, key meant for the other surface) --
so this module keeps them as three clearly separate function groups
instead of one generic `_request()` used for everything.

WHY 401 vs 403 ARE HANDLED DIFFERENTLY, SAME PRINCIPLE AS OTHER
IMPERAL CONNECTORS' CLIENTS.

A 401 means the REST API key itself is not accepted (revoked, wrong
value, or a key meant for a different account). A 403 means the key is
valid but lacks the permission for that specific action (e.g. a
read-only key used on a write call, or a non-admin key trying to manage
users). Distinguishing these two lets handlers give the user an accurate,
actionable reason instead of a flat "connection failed".

WHY 429 IS RETRIED ONCE WITH `Retry-After`, SAME AS EVERY OTHER
IMPERAL CONNECTOR CLIENT.

PagerDuty's REST API v2 rate-limits per account/token and returns a
`Retry-After` header on 429 (developer.pagerduty.com, confirmed
2026-08-21) -- a single bounded retry absorbs the common "slightly over
a burst limit" case without the caller needing to handle it.
"""
from __future__ import annotations

import asyncio
from typing import Any

REST_BASE = "https://api.pagerduty.com"
EVENTS_BASE = "https://events.pagerduty.com/v2/enqueue"
CHANGE_EVENTS_BASE = "https://events.pagerduty.com/v2/change/enqueue"

_REST_API_VERSION_HEADER = {"Accept": "application/vnd.pagerduty+json;version=2"}


class ClientFail(Exception):
    """Raised for any non-2xx PagerDuty response, carrying a human reason."""

    def __init__(self, reason: str, status: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _rest_headers(api_key: str, *, from_email: str = "") -> dict[str, str]:
    headers = {
        "Authorization": f"Token token={api_key}",
        "Content-Type": "application/json",
        **_REST_API_VERSION_HEADER,
    }
    if from_email:
        # Required by several write endpoints (e.g. creating an incident,
        # adding a note) to attribute the action to a real user
        # (developer.pagerduty.com, "From" header requirement, confirmed
        # 2026-08-21). Optional on pure reads.
        headers["From"] = from_email
    return headers


def _map_rest_error(status: int, body: Any) -> str:
    detail = ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            detail = err.get("message") or ""
            errors = err.get("errors")
            if isinstance(errors, list) and errors:
                detail = f"{detail}: {'; '.join(str(e) for e in errors)}" if detail else "; ".join(str(e) for e in errors)
    if status == 401:
        return "PagerDuty rejected this REST API key -- it may be wrong, revoked, or disabled."
    if status == 403:
        return f"PagerDuty accepted the key but refused this action (insufficient permissions).{(' ' + detail) if detail else ''}"
    if status == 404:
        return "That PagerDuty resource was not found (wrong id, or it was deleted)."
    if status == 422:
        return f"PagerDuty rejected the request data.{(' ' + detail) if detail else ''}"
    if status == 429:
        return "PagerDuty rate-limited this account -- too many requests too quickly."
    return f"PagerDuty REST API error ({status}).{(' ' + detail) if detail else ''}"


async def rest_request(
    ctx,
    method: str,
    path: str,
    api_key: str,
    *,
    from_email: str = "",
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    _retried: bool = False,
) -> dict[str, Any]:
    """One call against REST API v2. `path` starts with '/', e.g. '/incidents'."""
    url = f"{REST_BASE}{path}"
    headers = _rest_headers(api_key, from_email=from_email)
    try:
        method_l = method.upper()
        if method_l == "GET":
            resp = await ctx.http.get(url, headers=headers, params=params)
        elif method_l == "POST":
            resp = await ctx.http.post(url, headers=headers, params=params, json=json_body)
        elif method_l == "PUT":
            resp = await ctx.http.put(url, headers=headers, params=params, json=json_body)
        elif method_l == "DELETE":
            resp = await ctx.http.delete(url, headers=headers, params=params)
        else:
            raise ClientFail(f"Unsupported HTTP method: {method}")
    except ClientFail:
        raise
    except Exception as e:
        raise ClientFail(f"Could not reach PagerDuty's REST API: {e}")

    if resp.status_code == 429 and not _retried:
        wait = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
        try:
            await asyncio.sleep(min(float(wait), 5.0) if wait else 1.0)
        except (TypeError, ValueError):
            await asyncio.sleep(1.0)
        return await rest_request(
            ctx, method, path, api_key, from_email=from_email,
            params=params, json_body=json_body, _retried=True,
        )

    if resp.status_code == 204 or not getattr(resp, "content", resp.body if hasattr(resp, "body") else None):
        if resp.status_code >= 400:
            raise ClientFail(_map_rest_error(resp.status_code, {}), resp.status_code)
        return {}

    body = resp.body if isinstance(resp.body, (dict, list)) else {}

    if resp.status_code >= 400:
        raise ClientFail(_map_rest_error(resp.status_code, body), resp.status_code)

    return body if isinstance(body, dict) else {"items": body}


async def rest_get_all(
    ctx, path: str, api_key: str, list_key: str, *, params: dict[str, Any] | None = None,
    limit: int = 100, max_items: int = 1000,
) -> list[dict[str, Any]]:
    """Paginate a REST API v2 GET list endpoint (offset/limit/more shape,
    developer.pagerduty.com pagination docs, confirmed 2026-08-21)."""
    out: list[dict[str, Any]] = []
    offset = 0
    q = dict(params or {})
    q["limit"] = min(limit, 100)
    while len(out) < max_items:
        q["offset"] = offset
        body = await rest_request(ctx, "GET", path, api_key, params=q)
        items = body.get(list_key) or []
        out.extend(items)
        if not body.get("more") or not items:
            break
        offset += len(items)
    return out[:max_items]


# ──────────────────────────────────────────────────────────────────────────
# Events API v2 -- alert trigger/acknowledge/resolve
# ──────────────────────────────────────────────────────────────────────────


def _map_events_error(status: int, body: Any) -> str:
    detail = ""
    if isinstance(body, dict):
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            detail = "; ".join(str(e) for e in errors)
        elif body.get("message"):
            detail = str(body["message"])
    if status == 400:
        return f"PagerDuty rejected this event payload.{(' ' + detail) if detail else ''}"
    if status == 429:
        return "PagerDuty Events API rate-limited this integration key -- too many events too quickly."
    return f"PagerDuty Events API error ({status}).{(' ' + detail) if detail else ''}"


async def events_request(ctx, payload: dict[str, Any], *, _retried: bool = False) -> dict[str, Any]:
    """POST to Events API v2. `payload` must already include `routing_key`."""
    try:
        resp = await ctx.http.post(EVENTS_BASE, json=payload)
    except Exception as e:
        raise ClientFail(f"Could not reach PagerDuty's Events API: {e}")

    if resp.status_code == 429 and not _retried:
        await asyncio.sleep(1.0)
        return await events_request(ctx, payload, _retried=True)

    body = resp.body if isinstance(resp.body, dict) else {}

    if resp.status_code >= 400:
        raise ClientFail(_map_events_error(resp.status_code, body), resp.status_code)

    return body


async def change_events_request(ctx, payload: dict[str, Any], *, _retried: bool = False) -> dict[str, Any]:
    """POST to Change Events API. `payload` must already include `routing_key`."""
    try:
        resp = await ctx.http.post(CHANGE_EVENTS_BASE, json=payload)
    except Exception as e:
        raise ClientFail(f"Could not reach PagerDuty's Change Events API: {e}")

    if resp.status_code == 429 and not _retried:
        await asyncio.sleep(1.0)
        return await change_events_request(ctx, payload, _retried=True)

    body = resp.body if isinstance(resp.body, dict) else {}

    if resp.status_code >= 400:
        raise ClientFail(_map_events_error(resp.status_code, body), resp.status_code)

    return body


# ──────────────────────────────────────────────────────────────────────────
# Connection validation
# ──────────────────────────────────────────────────────────────────────────


async def validate_rest_key(ctx, api_key: str) -> dict[str, Any]:
    """Confirm a REST API key actually works by reading the account's own
    user list root (GET /users?limit=1) -- cheap, always-available call
    that also surfaces whether the key is read-only."""
    return await rest_request(ctx, "GET", "/users", api_key, params={"limit": 1})


async def validate_abilities(ctx, api_key: str) -> list[str]:
    """GET /abilities -- lists account-level feature entitlements (e.g.
    'teams', 'read_only_users', 'advanced_permissions'), confirmed via
    developer.pagerduty.com, 2026-08-21. Used to detect a read-only key
    (its abilities list omits write-gated features) and account tier."""
    body = await rest_request(ctx, "GET", "/abilities", api_key)
    return body.get("abilities") or []
