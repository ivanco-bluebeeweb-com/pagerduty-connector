"""Analytics (incident metrics) and Audit Trail, plus a Tier-3 value-add
account health audit report. Async, full @chat.function metadata,
ActionResult.success()/.error() -- same shape as MuleSoft Connector's
handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    GetIncidentAnalyticsParams, IncidentAnalyticsRow, IncidentAnalyticsReport,
    ListAuditRecordsParams, AuditRecordEntry, AuditRecordList,
    AuditAccountParams, AccountAuditRow, AccountAuditReport,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


@chat.function(
    "get_incident_analytics",
    "Read aggregated incident analytics (mean time to acknowledge/resolve, engagement) grouped by service over a date range.",
    action_type="read",
    chain_callable=True,
    data_model=IncidentAnalyticsReport,
    event="pagerduty-connector.get_incident_analytics",
)
async def get_incident_analytics(ctx, params: GetIncidentAnalyticsParams) -> ActionResult:
    """Read incident analytics."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    body_filters: dict = {}
    if params.since:
        body_filters["created_at_start"] = params.since
    if params.until:
        body_filters["created_at_end"] = params.until
    if params.service_ids:
        body_filters["service_ids"] = [s.strip() for s in params.service_ids.split(",") if s.strip()]
    try:
        body = await pc.rest_request(
            ctx, "POST", "/analytics/metrics/incidents/services", conn["api_key"],
            json_body={"filters": body_filters},
        )
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    rows = [
        IncidentAnalyticsRow(
            service_id=r.get("service_id", ""), service_name=r.get("service_name", ""),
            incident_count=r.get("total_incident_count", 0),
            mean_seconds_to_ack=r.get("mean_seconds_to_first_ack", 0.0) or 0.0,
            mean_seconds_to_resolve=r.get("mean_seconds_to_resolve", 0.0) or 0.0,
            mean_engaged_seconds=r.get("mean_engaged_seconds", 0.0) or 0.0,
            mean_engaged_user_count=r.get("mean_engaged_user_count", 0.0) or 0.0,
        )
        for r in (body.get("data") or [])
    ]
    return ActionResult.success(IncidentAnalyticsReport(rows=rows), f"{len(rows)} service(s) analyzed.")


@chat.function(
    "list_audit_records",
    "List audit trail records -- PagerDuty's own log of who changed what configuration and when, optionally filtered by date range and action type.",
    action_type="read",
    chain_callable=True,
    data_model=AuditRecordList,
    event="pagerduty-connector.list_audit_records",
)
async def list_audit_records(ctx, params: ListAuditRecordsParams) -> ActionResult:
    """List audit trail records."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q: dict = {}
    if params.since:
        q["since"] = params.since
    if params.until:
        q["until"] = params.until
    if params.actions:
        q["actions[]"] = [a.strip() for a in params.actions.split(",") if a.strip()]
    try:
        rows = await pc.rest_get_all(ctx, "/audit/records", conn["api_key"], "records", params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = []
    for r in rows:
        actor = r.get("actor") or {}
        root = r.get("root_resource") or {}
        items.append(AuditRecordEntry(
            id=r.get("id", ""), action=r.get("action", ""),
            actor_name=actor.get("name") or actor.get("type", ""),
            execution_time=r.get("execution_time", ""),
            root_resource_type=root.get("type", ""), root_resource_id=root.get("id", ""),
        ))
    return ActionResult.success(AuditRecordList(items=items), f"{len(items)} audit record(s).")


@chat.function(
    "audit_account",
    "Value-add report: build one aggregated health snapshot across every service in the connected PagerDuty account -- open incident counts, escalation policy coverage, services with no integrations configured (silent services that can never receive alerts), and disabled services.",
    action_type="read",
    chain_callable=True,
    data_model=AccountAuditReport,
    event="pagerduty-connector.audit_account",
)
async def audit_account(ctx, params: AuditAccountParams) -> ActionResult:
    """Build an aggregated account health audit."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        services = await pc.rest_get_all(ctx, "/services", conn["api_key"], "services", params={"include[]": ["integrations"]})
    except pc.ClientFail as e:
        return ActionResult.error(str(e))

    try:
        open_incidents = await pc.rest_get_all(
            ctx, "/incidents", conn["api_key"], "incidents",
            params={"statuses[]": ["triggered", "acknowledged"]}, limit=100,
        )
    except pc.ClientFail:
        open_incidents = []
    open_by_service: dict[str, int] = {}
    for inc in open_incidents:
        sid = (inc.get("service") or {}).get("id", "")
        if sid:
            open_by_service[sid] = open_by_service.get(sid, 0) + 1

    rows = []
    no_integrations = 0
    disabled = 0
    total_open = 0
    for s in services:
        sid = s.get("id", "")
        ep = s.get("escalation_policy") or {}
        integrations = s.get("integrations") or []
        has_no_ints = len(integrations) == 0
        status = s.get("status", "")
        opened = open_by_service.get(sid, 0)
        total_open += opened
        if has_no_ints:
            no_integrations += 1
        if status == "disabled":
            disabled += 1
        rows.append(AccountAuditRow(
            service_id=sid, service_name=s.get("name", ""),
            open_incidents=opened, escalation_policy_name=ep.get("summary", ""),
            has_no_integrations=has_no_ints, status=status,
        ))

    report = AccountAuditReport(
        rows=rows, total_services=len(services), total_open_incidents=total_open,
        services_without_integrations=no_integrations, services_disabled=disabled,
    )
    return ActionResult.success(
        report,
        f"{len(services)} service(s), {total_open} open incident(s), "
        f"{no_integrations} without integrations, {disabled} disabled.",
    )
