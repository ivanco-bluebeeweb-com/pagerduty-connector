"""Incident management: list/get/create incidents, change status (ack/resolve/
reopen), reassign, change priority, merge, snooze, notes, alerts, log entries,
run response plays, bulk actions. Built on pagerduty_client.py / schemas.py,
same shape as MuleSoft Connector's handlers.py -- async, full @chat.function
metadata, ActionResult.success()/.error().
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListIncidentsParams, Incident, IncidentList,
    GetIncidentParams, CreateIncidentParams, UpdateIncidentStatusParams,
    ReassignIncidentParams, UpdateIncidentPriorityParams, MergeIncidentsParams,
    SnoozeIncidentParams, AddIncidentNoteParams, IncidentNoteEntry, IncidentNoteList,
    ListIncidentNotesParams, ListIncidentAlertsParams, IncidentAlertEntry, IncidentAlertList,
    ListIncidentLogEntriesParams, IncidentLogEntryItem, IncidentLogEntryList,
    RunResponsePlayParams, BulkIncidentActionParams, BulkIncidentResultItem, BulkIncidentResult,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


def _incident_from(raw: dict) -> Incident:
    svc = raw.get("service") or {}
    ep = raw.get("escalation_policy") or {}
    assignees = ", ".join(a.get("assignee", {}).get("summary", "") for a in raw.get("assignments", []) or [])
    return Incident(
        id=raw.get("id", ""), incident_number=raw.get("incident_number", 0),
        title=raw.get("title", ""), status=raw.get("status", ""),
        urgency=raw.get("urgency", ""), service_id=svc.get("id", ""),
        service_name=svc.get("summary", ""), escalation_policy_name=ep.get("summary", ""),
        created_at=raw.get("created_at", ""), html_url=raw.get("html_url", ""),
        assignees=assignees,
    )


@chat.function(
    "list_incidents",
    "List incidents in the connected PagerDuty account, optionally filtered by status, service, urgency, and date range.",
    action_type="read",
    chain_callable=True,
    data_model=IncidentList,
    event="pagerduty-connector.list_incidents",
)
async def list_incidents(ctx, params: ListIncidentsParams) -> ActionResult:
    """List incidents in the connected PagerDuty account."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q: dict = {"limit": max(1, min(params.limit, 100)), "offset": max(0, params.offset)}
    if params.statuses:
        q["statuses[]"] = [s.strip() for s in params.statuses.split(",") if s.strip()]
    if params.service_ids:
        q["service_ids[]"] = [s.strip() for s in params.service_ids.split(",") if s.strip()]
    if params.urgency:
        q["urgencies[]"] = [params.urgency]
    if params.since:
        q["since"] = params.since
    if params.until:
        q["until"] = params.until
    try:
        body = await pc.rest_request(ctx, "GET", "/incidents", conn["api_key"], params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [_incident_from(i) for i in body.get("incidents", [])]
    return ActionResult.success(IncidentList(items=items, total=len(items)), f"{len(items)} incident(s).")


@chat.function(
    "get_incident",
    "Read one incident in full: status, urgency, service, escalation policy, assignees, and its PagerDuty web URL.",
    action_type="read",
    chain_callable=True,
    data_model=Incident,
    event="pagerduty-connector.get_incident",
)
async def get_incident(ctx, params: GetIncidentParams) -> ActionResult:
    """Read one incident in full."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/incidents/{params.incident_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    inc = _incident_from(body.get("incident", {}))
    return ActionResult.success(inc, f"Incident #{inc.incident_number}: {inc.title}")


@chat.function(
    "create_incident",
    "Create a new incident manually on a service (e.g. reporting a problem noticed outside of automated monitoring). Requires a From-email user on the connection.",
    action_type="write",
    chain_callable=True,
    data_model=Incident,
    event="pagerduty-connector.create_incident",
    effects=["pagerduty.incident.created"],
)
async def create_incident(ctx, params: CreateIncidentParams) -> ActionResult:
    """Create a new incident manually on a service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    from_email = conn.get("from_email", "")
    if not from_email:
        return ActionResult.error("This connection has no From-email set -- reconnect with a from_email to create incidents.")
    body = {
        "incident": {
            "type": "incident",
            "title": params.title,
            "service": {"id": params.service_id, "type": "service_reference"},
            "urgency": params.urgency or "high",
        }
    }
    if params.details:
        body["incident"]["body"] = {"type": "incident_body", "details": params.details}
    if params.priority_id:
        body["incident"]["priority"] = {"id": params.priority_id, "type": "priority_reference"}
    try:
        resp = await pc.rest_request(ctx, "POST", "/incidents", conn["api_key"], from_email=from_email, json_body=body)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    inc = _incident_from(resp.get("incident", {}))
    return ActionResult.success(inc, f"Created incident #{inc.incident_number}: {inc.title}", refresh_panels=["pd_incidents"])


@chat.function(
    "update_incident_status",
    "Change an incident's status: acknowledge, resolve, or reopen (set back to triggered).",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.update_incident_status",
    effects=["pagerduty.incident.status_changed"],
)
async def update_incident_status(ctx, params: UpdateIncidentStatusParams) -> ActionResult:
    """Change an incident's status."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    from_email = conn.get("from_email", "")
    body = {"incident": {"type": "incident_reference", "status": params.status}}
    try:
        await pc.rest_request(ctx, "PUT", f"/incidents/{params.incident_id}", conn["api_key"], from_email=from_email, json_body=body)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, f"Incident set to '{params.status}'.", refresh_panels=["pd_incidents"])


@chat.function(
    "reassign_incident",
    "Reassign an incident to different users.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.reassign_incident",
    effects=["pagerduty.incident.reassigned"],
)
async def reassign_incident(ctx, params: ReassignIncidentParams) -> ActionResult:
    """Reassign an incident to different users."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    user_ids = [u.strip() for u in params.user_ids.split(",") if u.strip()]
    body = {"incident": {"type": "incident_reference", "assignments": [
        {"assignee": {"id": uid, "type": "user_reference"}} for uid in user_ids
    ]}}
    try:
        await pc.rest_request(ctx, "PUT", f"/incidents/{params.incident_id}", conn["api_key"], from_email=conn.get("from_email", ""), json_body=body)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Incident reassigned.", refresh_panels=["pd_incidents"])


@chat.function(
    "update_incident_priority",
    "Set or clear an incident's priority level.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.update_incident_priority",
    effects=["pagerduty.incident.priority_changed"],
)
async def update_incident_priority(ctx, params: UpdateIncidentPriorityParams) -> ActionResult:
    """Set or clear an incident's priority level."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    priority = {"id": params.priority_id, "type": "priority_reference"} if params.priority_id else None
    body = {"incident": {"type": "incident_reference", "priority": priority}}
    try:
        await pc.rest_request(ctx, "PUT", f"/incidents/{params.incident_id}", conn["api_key"], from_email=conn.get("from_email", ""), json_body=body)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Incident priority updated.", refresh_panels=["pd_incidents"])


@chat.function(
    "merge_incidents",
    "Merge one or more source incidents into a target incident. Source incidents are closed and their alerts move to the target.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.merge_incidents",
    effects=["pagerduty.incident.merged"],
)
async def merge_incidents(ctx, params: MergeIncidentsParams) -> ActionResult:
    """Merge one or more source incidents into a target incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    source_ids = [s.strip() for s in params.source_incident_ids.split(",") if s.strip()]
    body = {"source_incidents": [{"id": sid, "type": "incident_reference"} for sid in source_ids]}
    try:
        await pc.rest_request(ctx, "PUT", f"/incidents/{params.target_incident_id}/merge", conn["api_key"], from_email=conn.get("from_email", ""), json_body=body)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, f"Merged {len(source_ids)} incident(s) into target.", refresh_panels=["pd_incidents"])


@chat.function(
    "snooze_incident",
    "Snooze an incident for N seconds -- it stops notifying and reopens automatically if not resolved by then.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.snooze_incident",
    effects=["pagerduty.incident.snoozed"],
)
async def snooze_incident(ctx, params: SnoozeIncidentParams) -> ActionResult:
    """Snooze an incident for N seconds."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    body = {"duration": params.duration_seconds}
    try:
        await pc.rest_request(ctx, "POST", f"/incidents/{params.incident_id}/snooze", conn["api_key"], from_email=conn.get("from_email", ""), json_body=body)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, f"Incident snoozed for {params.duration_seconds}s.", refresh_panels=["pd_incidents"])


@chat.function(
    "add_incident_note",
    "Add a note to an incident -- visible to everyone with access to it.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.add_incident_note",
    effects=["pagerduty.incident.note_added"],
)
async def add_incident_note(ctx, params: AddIncidentNoteParams) -> ActionResult:
    """Add a note to an incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    body = {"note": {"content": params.content}}
    try:
        await pc.rest_request(ctx, "POST", f"/incidents/{params.incident_id}/notes", conn["api_key"], from_email=conn.get("from_email", ""), json_body=body)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Note added.", refresh_panels=["pd_incidents"])


@chat.function(
    "list_incident_notes",
    "Read the notes left on an incident.",
    action_type="read",
    chain_callable=True,
    data_model=IncidentNoteList,
    event="pagerduty-connector.list_incident_notes",
)
async def list_incident_notes(ctx, params: ListIncidentNotesParams) -> ActionResult:
    """Read the notes left on an incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/incidents/{params.incident_id}/notes", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        IncidentNoteEntry(id=n.get("id", ""), content=n.get("content", ""),
                           created_at=n.get("created_at", ""),
                           user_name=(n.get("user") or {}).get("summary", ""))
        for n in body.get("notes", [])
    ]
    return ActionResult.success(IncidentNoteList(items=items), f"{len(items)} note(s).")


@chat.function(
    "list_incident_alerts",
    "List the individual alerts grouped into one incident.",
    action_type="read",
    chain_callable=True,
    data_model=IncidentAlertList,
    event="pagerduty-connector.list_incident_alerts",
)
async def list_incident_alerts(ctx, params: ListIncidentAlertsParams) -> ActionResult:
    """List the individual alerts grouped into one incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/incidents/{params.incident_id}/alerts", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        IncidentAlertEntry(id=a.get("id", ""), summary=a.get("summary", ""),
                            status=a.get("status", ""), severity=(a.get("severity") or ""),
                            created_at=a.get("created_at", ""))
        for a in body.get("alerts", [])
    ]
    return ActionResult.success(IncidentAlertList(items=items), f"{len(items)} alert(s).")


@chat.function(
    "list_incident_log_entries",
    "Read the full activity timeline of an incident -- every trigger, acknowledge, escalate, reassign, resolve and note event, in order.",
    action_type="read",
    chain_callable=True,
    data_model=IncidentLogEntryList,
    event="pagerduty-connector.list_incident_log_entries",
)
async def list_incident_log_entries(ctx, params: ListIncidentLogEntriesParams) -> ActionResult:
    """Read the full activity timeline of an incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/incidents/{params.incident_id}/log_entries", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        IncidentLogEntryItem(id=e.get("id", ""), type=e.get("type", ""),
                              summary=e.get("summary", ""), created_at=e.get("created_at", ""),
                              agent=(e.get("agent") or {}).get("summary", ""))
        for e in body.get("log_entries", [])
    ]
    return ActionResult.success(IncidentLogEntryList(items=items), f"{len(items)} log entries.")


@chat.function(
    "run_response_play",
    "Run a saved Response Play against an incident -- executes its predefined set of actions (notify responders, run status update, etc.).",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.run_response_play",
    effects=["pagerduty.response_play.run"],
)
async def run_response_play(ctx, params: RunResponsePlayParams) -> ActionResult:
    """Run a saved Response Play against an incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    body = {"incident": {"id": params.incident_id, "type": "incident_reference"}}
    try:
        await pc.rest_request(
            ctx, "POST", f"/response_plays/{params.response_play_id}/run",
            conn["api_key"], from_email=conn.get("from_email", ""), json_body=body,
        )
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Response play executed.", refresh_panels=["pd_incidents"])


@chat.function(
    "bulk_incident_action",
    "Acknowledge or resolve several incidents in one call, by explicit incident ids. Continues past per-item failures and reports each result.",
    action_type="write",
    chain_callable=True,
    data_model=BulkIncidentResult,
    event="pagerduty-connector.bulk_incident_action",
    effects=["pagerduty.incident.bulk_updated"],
)
async def bulk_incident_action(ctx, params: BulkIncidentActionParams) -> ActionResult:
    """Acknowledge or resolve several incidents in one call."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    ids = [i.strip() for i in params.incident_ids.split(",") if i.strip()]
    results = []
    ok_count = 0
    for iid in ids:
        try:
            await pc.rest_request(
                ctx, "PUT", f"/incidents/{iid}", conn["api_key"],
                from_email=conn.get("from_email", ""),
                json_body={"incident": {"type": "incident_reference", "status": params.status}},
            )
            results.append(BulkIncidentResultItem(incident_id=iid, ok=True, detail="Updated"))
            ok_count += 1
        except pc.ClientFail as e:
            results.append(BulkIncidentResultItem(incident_id=iid, ok=False, detail=str(e)))
    result = BulkIncidentResult(items=results, succeeded=ok_count, failed=len(ids) - ok_count)
    return ActionResult.success(result, f"{ok_count}/{len(ids)} incident(s) updated.", refresh_panels=["pd_incidents"])
