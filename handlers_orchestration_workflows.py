"""Event Orchestration (global router + per-service orchestrations) and
Incident Workflows (multi-step automated response sequences). Async, full
@chat.function metadata, ActionResult.success()/.error() -- same shape as
MuleSoft Connector's handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListEventOrchestrationsParams, EventOrchestrationEntry, EventOrchestrationList,
    CreateEventOrchestrationParams, GetEventOrchestrationParams, DeleteEventOrchestrationParams,
    GetEventOrchestrationRouterParams, EventOrchestrationRouterInfo,
    ListIncidentWorkflowsParams, IncidentWorkflowEntry, IncidentWorkflowList,
    GetIncidentWorkflowParams, RunIncidentWorkflowParams,
    ListIncidentWorkflowTriggersParams, IncidentWorkflowTriggerEntry, IncidentWorkflowTriggerList,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


# ── Event orchestration ────────────────────────────────────────────────

@chat.function(
    "list_event_orchestrations",
    "List event orchestrations -- the rule sets that decide which service (and with what enrichment) an incoming event turns into an incident.",
    action_type="read",
    chain_callable=True,
    data_model=EventOrchestrationList,
    event="pagerduty-connector.list_event_orchestrations",
)
async def list_event_orchestrations(ctx, params: ListEventOrchestrationsParams) -> ActionResult:
    """List event orchestrations."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/event_orchestrations", conn["api_key"], "orchestrations")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        EventOrchestrationEntry(id=o.get("id", ""), name=o.get("name", ""),
                                 routes=len((o.get("integrations") or [])))
        for o in rows
    ]
    return ActionResult.success(EventOrchestrationList(items=items), f"{len(items)} event orchestration(s).")


@chat.function(
    "create_event_orchestration",
    "Create a new event orchestration -- a rule-based router that decides which service an incoming event becomes an incident on.",
    action_type="write",
    chain_callable=True,
    data_model=EventOrchestrationEntry,
    event="pagerduty-connector.create_event_orchestration",
    effects=["pagerduty.event_orchestration.created"],
)
async def create_event_orchestration(ctx, params: CreateEventOrchestrationParams) -> ActionResult:
    """Create an event orchestration."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.name:
        return ActionResult.error("Please provide an orchestration name.")
    payload: dict = {"orchestration": {"name": params.name}}
    if params.team_id:
        payload["orchestration"]["team"] = {"id": params.team_id, "type": "team_reference"}
    try:
        body = await pc.rest_request(ctx, "POST", "/event_orchestrations", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    o = body.get("orchestration", {})
    entity = EventOrchestrationEntry(id=o.get("id", ""), name=o.get("name", params.name),
                                      routes=len(o.get("integrations") or []))
    return ActionResult.success(entity, f"Event orchestration '{entity.name}' created.",
                                 refresh_panels=["pd_orchestrations"])


@chat.function(
    "get_event_orchestration",
    "Read one event orchestration in full.",
    action_type="read",
    chain_callable=True,
    data_model=EventOrchestrationEntry,
    event="pagerduty-connector.get_event_orchestration",
)
async def get_event_orchestration(ctx, params: GetEventOrchestrationParams) -> ActionResult:
    """Read one event orchestration."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/event_orchestrations/{params.orchestration_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    o = body.get("orchestration", {})
    entity = EventOrchestrationEntry(id=o.get("id", ""), name=o.get("name", ""),
                                      routes=len(o.get("integrations") or []))
    return ActionResult.success(entity, f"Event orchestration '{entity.name}'.")


@chat.function(
    "delete_event_orchestration",
    "Permanently delete an event orchestration. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_event_orchestration",
    effects=["pagerduty.event_orchestration.deleted"],
)
async def delete_event_orchestration(ctx, params: DeleteEventOrchestrationParams) -> ActionResult:
    """Delete an event orchestration."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/event_orchestrations/{params.orchestration_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Event orchestration deleted.", refresh_panels=["pd_orchestrations"])


@chat.function(
    "get_event_orchestration_router",
    "Read one event orchestration's router rules -- the conditions that decide which service an event is routed to.",
    action_type="read",
    chain_callable=True,
    data_model=EventOrchestrationRouterInfo,
    event="pagerduty-connector.get_event_orchestration_router",
)
async def get_event_orchestration_router(ctx, params: GetEventOrchestrationRouterParams) -> ActionResult:
    """Read an event orchestration's router rules."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(
            ctx, "GET", f"/event_orchestrations/{params.orchestration_id}/router", conn["api_key"],
        )
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    orch = body.get("orchestration_path", {})
    rules = orch.get("sets", [{}])[0].get("rules", []) if orch.get("sets") else []
    entity = EventOrchestrationRouterInfo(
        orchestration_id=params.orchestration_id,
        num_rules=len(rules),
        catch_all_service_id=(orch.get("catch_all") or {}).get("actions", {}).get("route_to", ""),
    )
    return ActionResult.success(entity, f"{entity.num_rules} router rule(s).")


# ── Incident workflows ─────────────────────────────────────────────────

@chat.function(
    "list_incident_workflows",
    "List incident workflows -- reusable multi-step automated response sequences (e.g. notify + create Slack channel + run a script).",
    action_type="read",
    chain_callable=True,
    data_model=IncidentWorkflowList,
    event="pagerduty-connector.list_incident_workflows",
)
async def list_incident_workflows(ctx, params: ListIncidentWorkflowsParams) -> ActionResult:
    """List incident workflows."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/incident_workflows", conn["api_key"], "incident_workflows")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        IncidentWorkflowEntry(id=w.get("id", ""), name=w.get("name", ""),
                               description=w.get("description") or "")
        for w in rows
    ]
    return ActionResult.success(IncidentWorkflowList(items=items), f"{len(items)} incident workflow(s).")


@chat.function(
    "get_incident_workflow",
    "Read one incident workflow in full.",
    action_type="read",
    chain_callable=True,
    data_model=IncidentWorkflowEntry,
    event="pagerduty-connector.get_incident_workflow",
)
async def get_incident_workflow(ctx, params: GetIncidentWorkflowParams) -> ActionResult:
    """Read one incident workflow."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/incident_workflows/{params.workflow_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    w = body.get("incident_workflow", {})
    entity = IncidentWorkflowEntry(id=w.get("id", ""), name=w.get("name", ""),
                                    description=w.get("description") or "")
    return ActionResult.success(entity, f"Incident workflow '{entity.name}'.")


@chat.function(
    "run_incident_workflow",
    "Manually trigger an incident workflow to run against a specific incident right now.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.run_incident_workflow",
    effects=["pagerduty.incident_workflow.run"],
)
async def run_incident_workflow(ctx, params: RunIncidentWorkflowParams) -> ActionResult:
    """Trigger an incident workflow manually."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload = {"incident_workflow_trigger": {
        "type": "manual_trigger",
        "workflow": {"id": params.workflow_id, "type": "incident_workflow_reference"},
        "incident": {"id": params.incident_id, "type": "incident_reference"},
    }}
    try:
        await pc.rest_request(
            ctx, "POST", f"/incident_workflows/{params.workflow_id}/instances", conn["api_key"], json_body=payload,
        )
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Incident workflow triggered.", refresh_panels=["pd_incident_workflows"])


@chat.function(
    "list_incident_workflow_triggers",
    "List incident workflow triggers -- what automatically starts a workflow (e.g. incident created on a given service).",
    action_type="read",
    chain_callable=True,
    data_model=IncidentWorkflowTriggerList,
    event="pagerduty-connector.list_incident_workflow_triggers",
)
async def list_incident_workflow_triggers(ctx, params: ListIncidentWorkflowTriggersParams) -> ActionResult:
    """List incident workflow triggers."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/incident_workflows/triggers", conn["api_key"], "triggers")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        IncidentWorkflowTriggerEntry(
            id=t.get("id", ""), workflow_id=(t.get("workflow") or {}).get("id", ""),
            type=t.get("type", ""), service_id=(t.get("services") or [{}])[0].get("id", "") if t.get("services") else "",
        )
        for t in rows
    ]
    return ActionResult.success(IncidentWorkflowTriggerList(items=items), f"{len(items)} trigger(s).")
