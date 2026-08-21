"""Services and Escalation Policies: list/get/create/update/delete services,
manage their integrations (for Events API routing keys), and the same CRUD
for escalation policies that services attach to. Async, full @chat.function
metadata, ActionResult.success()/.error() -- same shape as MuleSoft
Connector's handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListServicesParams, ServiceEntry, ServiceList,
    GetServiceParams, CreateServiceParams, UpdateServiceParams, DeleteServiceParams,
    ListServiceIntegrationsParams, ServiceIntegrationEntry, ServiceIntegrationList,
    CreateServiceIntegrationParams, DeleteServiceIntegrationParams,
    ListEscalationPoliciesParams, EscalationPolicyEntry, EscalationPolicyList,
    GetEscalationPolicyParams, CreateEscalationPolicyParams,
    UpdateEscalationPolicyParams, DeleteEscalationPolicyParams,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


def _service_from(raw: dict) -> ServiceEntry:
    ep = raw.get("escalation_policy") or {}
    return ServiceEntry(
        id=raw.get("id", ""), name=raw.get("name", ""), status=raw.get("status", ""),
        escalation_policy_id=ep.get("id", ""), escalation_policy_name=ep.get("summary", ""),
        description=raw.get("description") or "", html_url=raw.get("html_url", ""),
    )


@chat.function(
    "list_services",
    "List services (the things that receive alerts and generate incidents) in the connected PagerDuty account, optionally filtered by name.",
    action_type="read",
    chain_callable=True,
    data_model=ServiceList,
    event="pagerduty-connector.list_services",
)
async def list_services(ctx, params: ListServicesParams) -> ActionResult:
    """List services in the connected PagerDuty account."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q: dict = {"limit": params.limit, "offset": params.offset}
    if params.query:
        q["query"] = params.query
    try:
        body = await pc.rest_request(ctx, "GET", "/services", conn["api_key"], params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [_service_from(s) for s in body.get("services", [])]
    return ActionResult.success(ServiceList(items=items, total=len(items)), f"{len(items)} service(s).")


@chat.function(
    "get_service",
    "Read one PagerDuty service in full: its status, escalation policy, and description.",
    action_type="read",
    chain_callable=True,
    data_model=ServiceEntry,
    event="pagerduty-connector.get_service",
)
async def get_service(ctx, params: GetServiceParams) -> ActionResult:
    """Read one PagerDuty service in full."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/services/{params.service_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success(_service_from(body.get("service", {})), "Service loaded.")


@chat.function(
    "create_service",
    "Create a new PagerDuty service (a monitored system/component that generates incidents), attached to an escalation policy.",
    action_type="write",
    chain_callable=True,
    data_model=ServiceEntry,
    event="pagerduty-connector.create_service",
    effects=["pagerduty.service.created"],
)
async def create_service(ctx, params: CreateServiceParams) -> ActionResult:
    """Create a new PagerDuty service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.name or not params.escalation_policy_id:
        return ActionResult.error("Please provide a service name and an escalation policy id.")
    payload = {
        "service": {
            "name": params.name,
            "escalation_policy": {"id": params.escalation_policy_id, "type": "escalation_policy_reference"},
            "alert_creation": params.alert_creation,
        }
    }
    if params.description:
        payload["service"]["description"] = params.description
    try:
        body = await pc.rest_request(ctx, "POST", "/services", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    svc = body.get("service", {})
    return ActionResult.success(
        _service_from(svc), f"Service '{svc.get('name', params.name)}' created.",
        refresh_panels=["pd_services"],
    )


@chat.function(
    "update_service",
    "Update an existing service's name and/or escalation policy. Only given fields change.",
    action_type="write",
    chain_callable=True,
    data_model=ServiceEntry,
    event="pagerduty-connector.update_service",
    effects=["pagerduty.service.updated"],
)
async def update_service(ctx, params: UpdateServiceParams) -> ActionResult:
    """Update an existing service. Only given fields change."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload: dict = {"service": {}}
    if params.name:
        payload["service"]["name"] = params.name
    if params.escalation_policy_id:
        payload["service"]["escalation_policy"] = {"id": params.escalation_policy_id, "type": "escalation_policy_reference"}
    if not payload["service"]:
        return ActionResult.error("Nothing to update -- provide a new name or escalation policy.")
    try:
        body = await pc.rest_request(ctx, "PUT", f"/services/{params.service_id}", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success(_service_from(body.get("service", {})), "Service updated.", refresh_panels=["pd_services"])


@chat.function(
    "delete_service",
    "Permanently delete a PagerDuty service. Cannot be undone -- incidents tied to it remain but the service configuration is gone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_service",
    effects=["pagerduty.service.deleted"],
)
async def delete_service(ctx, params: DeleteServiceParams) -> ActionResult:
    """Permanently delete a PagerDuty service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/services/{params.service_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Service deleted.", refresh_panels=["pd_services"])


@chat.function(
    "list_service_integrations",
    "List the integrations (event sources / Integration Keys) configured on one service -- each one's own routing_key powers Events API v2 and Change Events API calls for that specific integration.",
    action_type="read",
    chain_callable=True,
    data_model=ServiceIntegrationList,
    event="pagerduty-connector.list_service_integrations",
)
async def list_service_integrations(ctx, params: ListServiceIntegrationsParams) -> ActionResult:
    """List the integrations configured on one service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/services/{params.service_id}", conn["api_key"], params={"include[]": "integrations"})
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    svc = body.get("service", {})
    items = [
        ServiceIntegrationEntry(
            id=i.get("id", ""), name=i.get("name", ""), integration_type=i.get("type", ""),
            integration_key=i.get("integration_key", ""), vendor_id=(i.get("vendor") or {}).get("id", ""),
        )
        for i in svc.get("integrations", []) or []
    ]
    return ActionResult.success(ServiceIntegrationList(items=items), f"{len(items)} integration(s).")


@chat.function(
    "create_service_integration",
    "Add a new integration to a service (e.g. a generic Events API integration, or a specific vendor like Datadog/Prometheus). Returns an Integration Key you can save via save_integration_key for Events API v2 / Change Events API calls.",
    action_type="write",
    chain_callable=True,
    data_model=ServiceIntegrationEntry,
    event="pagerduty-connector.create_service_integration",
    effects=["pagerduty.integration.created"],
)
async def create_service_integration(ctx, params: CreateServiceIntegrationParams) -> ActionResult:
    """Add a new integration to a service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload = {"integration": {"type": "generic_events_api_inbound_integration", "name": params.name or "Imperal Integration"}}
    if params.vendor_id:
        payload["integration"]["vendor"] = {"id": params.vendor_id, "type": "vendor_reference"}
    try:
        body = await pc.rest_request(ctx, "POST", f"/services/{params.service_id}/integrations", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    integ = body.get("integration", {})
    key = integ.get("integration_key", "")
    entity = ServiceIntegrationEntry(
        id=integ.get("id", ""), name=integ.get("name", ""), integration_type=integ.get("type", ""),
        integration_key=key, vendor_id=(integ.get("vendor") or {}).get("id", ""),
    )
    return ActionResult.success(
        entity,
        f"Integration '{integ.get('name', '')}' created. Integration key: {key} -- save it with save_integration_key to use it with events tools.",
        refresh_panels=["pd_services"],
    )


@chat.function(
    "delete_service_integration",
    "Permanently remove an integration from a service. Any external system still using its old integration key will stop being able to send alerts.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_service_integration",
    effects=["pagerduty.integration.deleted"],
)
async def delete_service_integration(ctx, params: DeleteServiceIntegrationParams) -> ActionResult:
    """Permanently remove an integration from a service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/services/{params.service_id}/integrations/{params.integration_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Integration removed.", refresh_panels=["pd_services"])


# ─────────────────────────────────────────────────────────────────────────
# Escalation policies
# ─────────────────────────────────────────────────────────────────────────


@chat.function(
    "list_escalation_policies",
    "List escalation policies (who gets notified, in what order, and how fast it escalates) in the connected PagerDuty account.",
    action_type="read",
    chain_callable=True,
    data_model=EscalationPolicyList,
    event="pagerduty-connector.list_escalation_policies",
)
async def list_escalation_policies(ctx, params: ListEscalationPoliciesParams) -> ActionResult:
    """List escalation policies in the connected PagerDuty account."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q = {"query": params.query} if params.query else {}
    try:
        body = await pc.rest_request(ctx, "GET", "/escalation_policies", conn["api_key"], params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        EscalationPolicyEntry(
            id=p.get("id", ""), name=p.get("name", ""), num_loops=p.get("num_loops", 0),
            on_call_handoff_notifications=p.get("on_call_handoff_notifications", ""),
            num_rules=len(p.get("escalation_rules", []) or []),
        )
        for p in body.get("escalation_policies", [])
    ]
    return ActionResult.success(EscalationPolicyList(items=items), f"{len(items)} escalation policy(-ies).")


@chat.function(
    "get_escalation_policy",
    "Read one escalation policy in full, including its rule count and loop/handoff settings.",
    action_type="read",
    chain_callable=True,
    data_model=EscalationPolicyEntry,
    event="pagerduty-connector.get_escalation_policy",
)
async def get_escalation_policy(ctx, params: GetEscalationPolicyParams) -> ActionResult:
    """Read one escalation policy in full."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/escalation_policies/{params.escalation_policy_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    p = body.get("escalation_policy", {})
    entity = EscalationPolicyEntry(
        id=p.get("id", ""), name=p.get("name", ""), num_loops=p.get("num_loops", 0),
        on_call_handoff_notifications=p.get("on_call_handoff_notifications", ""),
        num_rules=len(p.get("escalation_rules", []) or []),
    )
    return ActionResult.success(entity, "Escalation policy loaded.")


@chat.function(
    "create_escalation_policy",
    "Create a new escalation policy with a single rule targeting one or more users, with a configurable escalation delay and repeat count.",
    action_type="write",
    chain_callable=True,
    data_model=EscalationPolicyEntry,
    event="pagerduty-connector.create_escalation_policy",
    effects=["pagerduty.escalation_policy.created"],
)
async def create_escalation_policy(ctx, params: CreateEscalationPolicyParams) -> ActionResult:
    """Create a new escalation policy."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.name or not params.user_ids_level_1:
        return ActionResult.error("Please provide a policy name and at least one user id.")
    targets = [{"id": uid.strip(), "type": "user_reference"} for uid in params.user_ids_level_1.split(",") if uid.strip()]
    payload = {
        "escalation_policy": {
            "name": params.name,
            "num_loops": params.num_loops,
            "escalation_rules": [
                {"escalation_delay_in_minutes": params.escalation_delay_minutes, "targets": targets}
            ],
        }
    }
    try:
        body = await pc.rest_request(ctx, "POST", "/escalation_policies", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    ep = body.get("escalation_policy", {})
    entity = EscalationPolicyEntry(
        id=ep.get("id", ""), name=ep.get("name", ""), num_loops=ep.get("num_loops", 0),
        on_call_handoff_notifications=ep.get("on_call_handoff_notifications", ""),
        num_rules=len(ep.get("escalation_rules", []) or []),
    )
    return ActionResult.success(
        entity, f"Escalation policy '{ep.get('name', params.name)}' created.",
        refresh_panels=["pd_escalation"],
    )


@chat.function(
    "update_escalation_policy",
    "Update an escalation policy's name and/or repeat-loop count. Only given fields change.",
    action_type="write",
    chain_callable=True,
    data_model=EscalationPolicyEntry,
    event="pagerduty-connector.update_escalation_policy",
    effects=["pagerduty.escalation_policy.updated"],
)
async def update_escalation_policy(ctx, params: UpdateEscalationPolicyParams) -> ActionResult:
    """Update an escalation policy. Only given fields change."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload: dict = {"escalation_policy": {}}
    if params.name:
        payload["escalation_policy"]["name"] = params.name
    if params.num_loops is not None and params.num_loops > 0:
        payload["escalation_policy"]["num_loops"] = params.num_loops
    if not payload["escalation_policy"]:
        return ActionResult.error("Nothing to update -- provide a new name or loop count.")
    try:
        body = await pc.rest_request(ctx, "PUT", f"/escalation_policies/{params.escalation_policy_id}", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    p = body.get("escalation_policy", {})
    entity = EscalationPolicyEntry(
        id=p.get("id", ""), name=p.get("name", ""), num_loops=p.get("num_loops", 0),
        on_call_handoff_notifications=p.get("on_call_handoff_notifications", ""),
        num_rules=len(p.get("escalation_rules", []) or []),
    )
    return ActionResult.success(entity, "Escalation policy updated.", refresh_panels=["pd_escalation"])


@chat.function(
    "delete_escalation_policy",
    "Permanently delete an escalation policy. Fails if any service still references it -- reassign those services to another policy first.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_escalation_policy",
    effects=["pagerduty.escalation_policy.deleted"],
)
async def delete_escalation_policy(ctx, params: DeleteEscalationPolicyParams) -> ActionResult:
    """Permanently delete an escalation policy."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/escalation_policies/{params.escalation_policy_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Escalation policy deleted.", refresh_panels=["pd_escalation"])
