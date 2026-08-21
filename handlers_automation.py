"""Automation Actions (runbook automation invoked from incidents) and
Automation Runners (the process/action orchestration/runner registry).
Async, full @chat.function metadata, ActionResult.success()/.error() --
same shape as MuleSoft Connector's handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListAutomationActionsParams, AutomationActionEntry, AutomationActionList,
    GetAutomationActionParams, InvokeAutomationActionOnIncidentParams,
    ListAutomationRunnersParams, AutomationRunnerEntry, AutomationRunnerList,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


@chat.function(
    "list_automation_actions",
    "List automation actions (runbook automation) configured in the connected PagerDuty account -- scripts/actions that can be invoked directly from an incident.",
    action_type="read",
    chain_callable=True,
    data_model=AutomationActionList,
    event="pagerduty-connector.list_automation_actions",
)
async def list_automation_actions(ctx, params: ListAutomationActionsParams) -> ActionResult:
    """List automation actions."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/automation_actions/actions", conn["api_key"], "actions")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        AutomationActionEntry(
            id=a.get("id", ""), name=a.get("name", ""), description=a.get("description") or "",
            action_type=a.get("action_type", ""),
            runner_id=(a.get("runner") or {}).get("id", ""),
        )
        for a in rows
    ]
    return ActionResult.success(AutomationActionList(items=items), f"{len(items)} automation action(s).")


@chat.function(
    "get_automation_action",
    "Read one automation action in full.",
    action_type="read",
    chain_callable=True,
    data_model=AutomationActionEntry,
    event="pagerduty-connector.get_automation_action",
)
async def get_automation_action(ctx, params: GetAutomationActionParams) -> ActionResult:
    """Read one automation action."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/automation_actions/actions/{params.action_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    a = body.get("action", {})
    entity = AutomationActionEntry(
        id=a.get("id", ""), name=a.get("name", ""), description=a.get("description") or "",
        action_type=a.get("action_type", ""), runner_id=(a.get("runner") or {}).get("id", ""),
    )
    return ActionResult.success(entity, f"Automation action '{entity.name}'.")


@chat.function(
    "invoke_automation_action_on_incident",
    "Invoke a runbook automation action directly against a specific incident.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.invoke_automation_action_on_incident",
    effects=["pagerduty.automation_action.invoked"],
)
async def invoke_automation_action_on_incident(ctx, params: InvokeAutomationActionOnIncidentParams) -> ActionResult:
    """Invoke an automation action on an incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(
            ctx, "POST", f"/incidents/{params.incident_id}/automation_actions/{params.action_id}/invocations",
            conn["api_key"],
        )
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Automation action invoked on incident.", refresh_panels=["pd_incidents"])


@chat.function(
    "list_automation_runners",
    "List automation runners -- the registered execution environments (Runbook Automation Runner / Process Automation) that carry out automation actions.",
    action_type="read",
    chain_callable=True,
    data_model=AutomationRunnerList,
    event="pagerduty-connector.list_automation_runners",
)
async def list_automation_runners(ctx, params: ListAutomationRunnersParams) -> ActionResult:
    """List automation runners."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/automation_actions/runners", conn["api_key"], "runners")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        AutomationRunnerEntry(id=r.get("id", ""), name=r.get("name", ""),
                               runner_type=r.get("runner_type", ""), last_seen=r.get("last_seen_at") or "")
        for r in rows
    ]
    return ActionResult.success(AutomationRunnerList(items=items), f"{len(items)} automation runner(s).")
