"""Schedules, schedule overrides, and on-call queries. Async, full
@chat.function metadata, ActionResult.success()/.error() -- same shape as
MuleSoft Connector's handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListSchedulesParams, ScheduleEntry, ScheduleList,
    GetScheduleParams, CreateScheduleParams, DeleteScheduleParams,
    CreateScheduleOverrideParams, DeleteScheduleOverrideParams,
    ListOncallsParams, OncallEntry, OncallList,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


def _schedule_from(raw: dict) -> ScheduleEntry:
    users = raw.get("users") or []
    return ScheduleEntry(
        id=raw.get("id", ""), name=raw.get("name", ""), time_zone=raw.get("time_zone", ""),
        html_url=raw.get("html_url", ""), num_users=len(users),
    )


@chat.function(
    "list_schedules",
    "List on-call schedules (rotations) configured in the connected PagerDuty account, optionally filtered by name.",
    action_type="read",
    chain_callable=True,
    data_model=ScheduleList,
    event="pagerduty-connector.list_schedules",
)
async def list_schedules(ctx, params: ListSchedulesParams) -> ActionResult:
    """List on-call schedules."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q: dict = {}
    if params.query:
        q["query"] = params.query
    try:
        body = await pc.rest_request(ctx, "GET", "/schedules", conn["api_key"], params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [_schedule_from(s) for s in body.get("schedules", [])]
    return ActionResult.success(ScheduleList(items=items), f"{len(items)} schedule(s).")


@chat.function(
    "get_schedule",
    "Read one on-call schedule in full, including its current rotation users and time zone.",
    action_type="read",
    chain_callable=True,
    data_model=ScheduleEntry,
    event="pagerduty-connector.get_schedule",
)
async def get_schedule(ctx, params: GetScheduleParams) -> ActionResult:
    """Read one on-call schedule in full."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/schedules/{params.schedule_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success(_schedule_from(body.get("schedule", {})), "Schedule loaded.")


@chat.function(
    "create_schedule",
    "Create a new on-call rotation schedule with one layer of users rotating on a fixed interval (daily or weekly).",
    action_type="write",
    chain_callable=True,
    data_model=ScheduleEntry,
    event="pagerduty-connector.create_schedule",
    effects=["pagerduty.schedule.created"],
)
async def create_schedule(ctx, params: CreateScheduleParams) -> ActionResult:
    """Create a new on-call rotation schedule."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    user_ids = [u.strip() for u in (params.user_ids or "").split(",") if u.strip()]
    if not params.name or not user_ids or not params.start:
        return ActionResult.error("Please provide a schedule name, at least one user id, and a start time.")
    rotation_seconds = 604800 if params.rotation_turn_length_days >= 7 else max(86400, params.rotation_turn_length_days * 86400)
    payload = {
        "schedule": {
            "name": params.name,
            "time_zone": params.time_zone or "Etc/UTC",
            "schedule_layers": [{
                "start": params.start,
                "rotation_virtual_start": params.start,
                "rotation_turn_length_seconds": rotation_seconds,
                "users": [{"user": {"id": uid, "type": "user_reference"}} for uid in user_ids],
            }],
        }
    }
    try:
        body = await pc.rest_request(ctx, "POST", "/schedules", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    sc = body.get("schedule", {})
    return ActionResult.success(_schedule_from(sc), f"Schedule '{sc.get('name', params.name)}' created.", refresh_panels=["pd_schedules"])


@chat.function(
    "delete_schedule",
    "Permanently delete an on-call schedule. Fails if an escalation policy still references it.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_schedule",
    effects=["pagerduty.schedule.deleted"],
)
async def delete_schedule(ctx, params: DeleteScheduleParams) -> ActionResult:
    """Permanently delete an on-call schedule."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/schedules/{params.schedule_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Schedule deleted.", refresh_panels=["pd_schedules"])


@chat.function(
    "create_schedule_override",
    "Create a one-off override on a schedule -- e.g. swap who's on call for vacation coverage, without changing the underlying rotation.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.create_schedule_override",
    effects=["pagerduty.schedule_override.created"],
)
async def create_schedule_override(ctx, params: CreateScheduleOverrideParams) -> ActionResult:
    """Create a one-off schedule override."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.user_id or not params.start or not params.end:
        return ActionResult.error("Please provide the covering user id, start time, and end time.")
    payload = {"override": {
        "start": params.start, "end": params.end,
        "user": {"id": params.user_id, "type": "user_reference"},
    }}
    try:
        await pc.rest_request(ctx, "POST", f"/schedules/{params.schedule_id}/overrides", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Schedule override created.", refresh_panels=["pd_schedules"])


@chat.function(
    "delete_schedule_override",
    "Remove a schedule override, reverting to the underlying rotation for that time window.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_schedule_override",
    effects=["pagerduty.schedule_override.deleted"],
)
async def delete_schedule_override(ctx, params: DeleteScheduleOverrideParams) -> ActionResult:
    """Remove a schedule override."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/schedules/{params.schedule_id}/overrides/{params.override_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Schedule override removed.", refresh_panels=["pd_schedules"])


@chat.function(
    "list_oncalls",
    "List who is currently on call (or will be), optionally filtered by schedule ids or escalation policy ids, within a time window.",
    action_type="read",
    chain_callable=True,
    data_model=OncallList,
    event="pagerduty-connector.list_oncalls",
)
async def list_oncalls(ctx, params: ListOncallsParams) -> ActionResult:
    """List who is currently (or will be) on call."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q: dict = {}
    if params.schedule_ids:
        q["schedule_ids[]"] = [s.strip() for s in params.schedule_ids.split(",") if s.strip()]
    if params.escalation_policy_ids:
        q["escalation_policy_ids[]"] = [s.strip() for s in params.escalation_policy_ids.split(",") if s.strip()]
    if params.since:
        q["since"] = params.since
    if params.until:
        q["until"] = params.until
    try:
        rows = await pc.rest_get_all(ctx, "/oncalls", conn["api_key"], "oncalls", params=q, limit=100)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = []
    for r in rows:
        u = r.get("user") or {}
        sc = r.get("schedule") or {}
        ep = r.get("escalation_policy") or {}
        items.append(OncallEntry(
            user_id=u.get("id", ""), user_name=u.get("summary", ""),
            schedule_id=sc.get("id", ""), schedule_name=sc.get("summary", ""),
            escalation_policy_id=ep.get("id", ""), escalation_policy_name=ep.get("summary", ""),
            escalation_level=r.get("escalation_level", 0),
            start=r.get("start") or "", end=r.get("end") or "",
        ))
    return ActionResult.success(OncallList(items=items), f"{len(items)} on-call entry/entries.")
