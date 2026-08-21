"""Business Services, Service Dependencies, Priorities, Tags, Custom Fields.
Async, full @chat.function metadata, ActionResult.success()/.error() --
same shape as MuleSoft Connector's handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListBusinessServicesParams, BusinessServiceEntry, BusinessServiceList,
    CreateBusinessServiceParams, UpdateBusinessServiceParams, DeleteBusinessServiceParams,
    AddServiceDependencyParams, RemoveServiceDependencyParams,
    ListServiceDependenciesParams, ServiceDependencyEntry, ServiceDependencyList,
    ListPrioritiesParams, PriorityEntry, PriorityList,
    ListTagsParams, TagEntry, TagList, CreateTagParams, DeleteTagParams,
    AssignTagParams, RemoveTagAssignmentParams,
    ListCustomFieldsParams, CustomFieldEntry, CustomFieldList,
    CreateCustomFieldParams, DeleteCustomFieldParams, SetIncidentCustomFieldParams,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."
_BAD_ENTITY_TYPE = "entity_type must be one of: users, teams, escalation_policies, services."


# ── Business services ──────────────────────────────────────────────────

@chat.function(
    "list_business_services",
    "List business services -- the non-technical capabilities (e.g. 'Online Checkout') that group technical services for stakeholder-facing status.",
    action_type="read",
    chain_callable=True,
    data_model=BusinessServiceList,
    event="pagerduty-connector.list_business_services",
)
async def list_business_services(ctx, params: ListBusinessServicesParams) -> ActionResult:
    """List business services."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q = {"query": params.query} if params.query else {}
    try:
        rows = await pc.rest_get_all(ctx, "/business_services", conn["api_key"], "business_services", params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        BusinessServiceEntry(id=b.get("id", ""), name=b.get("name", ""),
                              description=b.get("description") or "",
                              point_of_contact=b.get("point_of_contact") or "")
        for b in rows
    ]
    return ActionResult.success(BusinessServiceList(items=items), f"{len(items)} business service(s).")


@chat.function(
    "create_business_service",
    "Create a new business service -- a non-technical capability stakeholders can watch, made up of one or more technical services underneath it.",
    action_type="write",
    chain_callable=True,
    data_model=BusinessServiceEntry,
    event="pagerduty-connector.create_business_service",
    effects=["pagerduty.business_service.created"],
)
async def create_business_service(ctx, params: CreateBusinessServiceParams) -> ActionResult:
    """Create a business service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.name:
        return ActionResult.error("Please provide a business service name.")
    payload = {"business_service": {"name": params.name, "description": params.description,
                                     "point_of_contact": params.point_of_contact}}
    try:
        body = await pc.rest_request(ctx, "POST", "/business_services", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    bs = body.get("business_service", {})
    entity = BusinessServiceEntry(id=bs.get("id", ""), name=bs.get("name", params.name),
                                   description=bs.get("description") or "",
                                   point_of_contact=bs.get("point_of_contact") or "")
    return ActionResult.success(entity, f"Business service '{entity.name}' created.",
                                 refresh_panels=["pd_business_services"])


@chat.function(
    "update_business_service",
    "Update an existing business service's name and/or description.",
    action_type="write",
    chain_callable=True,
    data_model=BusinessServiceEntry,
    event="pagerduty-connector.update_business_service",
    effects=["pagerduty.business_service.updated"],
)
async def update_business_service(ctx, params: UpdateBusinessServiceParams) -> ActionResult:
    """Update a business service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload: dict = {"business_service": {}}
    if params.name:
        payload["business_service"]["name"] = params.name
    if params.description:
        payload["business_service"]["description"] = params.description
    if not payload["business_service"]:
        return ActionResult.error("Nothing to update -- provide a new name or description.")
    try:
        await pc.rest_request(ctx, "PUT", f"/business_services/{params.business_service_id}", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Business service updated.", refresh_panels=["pd_business_services"])


@chat.function(
    "delete_business_service",
    "Permanently delete a business service. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_business_service",
    effects=["pagerduty.business_service.deleted"],
)
async def delete_business_service(ctx, params: DeleteBusinessServiceParams) -> ActionResult:
    """Delete a business service."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/business_services/{params.business_service_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Business service deleted.", refresh_panels=["pd_business_services"])


# ── Service dependencies ───────────────────────────────────────────────

@chat.function(
    "list_service_dependencies",
    "List the technical-service dependencies mapped to one business service -- which underlying services feed its status.",
    action_type="read",
    chain_callable=True,
    data_model=ServiceDependencyList,
    event="pagerduty-connector.list_service_dependencies",
)
async def list_service_dependencies(ctx, params: ListServiceDependenciesParams) -> ActionResult:
    """List service dependencies."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(
            ctx, "GET", "/service_dependencies/business_services/" + params.business_service_id, conn["api_key"],
        )
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = []
    for rel in body.get("relationships", []):
        dep = rel.get("dependent_service", {})
        sup = rel.get("supporting_service", {})
        items.append(ServiceDependencyEntry(
            id=rel.get("id", ""), dependent_service_id=dep.get("id", ""),
            dependent_service_name=dep.get("summary", ""),
            supporting_service_id=sup.get("id", ""), supporting_service_name=sup.get("summary", ""),
        ))
    return ActionResult.success(ServiceDependencyList(items=items), f"{len(items)} dependency mapping(s).")


@chat.function(
    "add_service_dependency",
    "Map a technical service as a dependency of a business service, so the business service's health reflects that underlying service's incidents.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.add_service_dependency",
    effects=["pagerduty.service_dependency.added"],
)
async def add_service_dependency(ctx, params: AddServiceDependencyParams) -> ActionResult:
    """Add a service dependency."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload = {
        "relationships": [{
            "dependent_service": {"id": params.business_service_id, "type": "business_service"},
            "supporting_service": {"id": params.service_id, "type": "service"},
        }]
    }
    try:
        await pc.rest_request(ctx, "POST", "/service_dependencies/associate", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Service dependency added.", refresh_panels=["pd_business_services"])


@chat.function(
    "remove_service_dependency",
    "Remove a technical service's dependency mapping from a business service.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.remove_service_dependency",
    effects=["pagerduty.service_dependency.removed"],
)
async def remove_service_dependency(ctx, params: RemoveServiceDependencyParams) -> ActionResult:
    """Remove a service dependency."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload = {
        "relationships": [{
            "dependent_service": {"id": params.business_service_id, "type": "business_service"},
            "supporting_service": {"id": params.service_id, "type": "service"},
        }]
    }
    try:
        await pc.rest_request(ctx, "POST", "/service_dependencies/disassociate", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Service dependency removed.", refresh_panels=["pd_business_services"])


# ── Priorities (read-only, account-configured) ─────────────────────────

@chat.function(
    "list_priorities",
    "List the priority levels (P1-P5 style) configured on the connected PagerDuty account -- used to set/change an incident's priority.",
    action_type="read",
    chain_callable=True,
    data_model=PriorityList,
    event="pagerduty-connector.list_priorities",
)
async def list_priorities(ctx, params: ListPrioritiesParams) -> ActionResult:
    """List priorities."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/priorities", conn["api_key"], "priorities")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        PriorityEntry(id=p.get("id", ""), name=p.get("name", ""), description=p.get("description") or "")
        for p in rows
    ]
    return ActionResult.success(PriorityList(items=items), f"{len(items)} priority level(s).")


# ── Tags ────────────────────────────────────────────────────────────────

@chat.function(
    "list_tags",
    "List tags defined in the connected PagerDuty account -- labels attachable to users, teams, escalation policies, or services.",
    action_type="read",
    chain_callable=True,
    data_model=TagList,
    event="pagerduty-connector.list_tags",
)
async def list_tags(ctx, params: ListTagsParams) -> ActionResult:
    """List tags."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q = {"query": params.query} if params.query else {}
    try:
        rows = await pc.rest_get_all(ctx, "/tags", conn["api_key"], "tags", params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [TagEntry(id=t.get("id", ""), label=t.get("label", "")) for t in rows]
    return ActionResult.success(TagList(items=items), f"{len(items)} tag(s).")


@chat.function(
    "create_tag",
    "Create a new tag on the connected PagerDuty account.",
    action_type="write",
    chain_callable=True,
    data_model=TagEntry,
    event="pagerduty-connector.create_tag",
    effects=["pagerduty.tag.created"],
)
async def create_tag(ctx, params: CreateTagParams) -> ActionResult:
    """Create a tag."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.label:
        return ActionResult.error("Please provide a tag label.")
    try:
        body = await pc.rest_request(ctx, "POST", "/tags", conn["api_key"], json_body={"tag": {"label": params.label}})
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    t = body.get("tag", {})
    entity = TagEntry(id=t.get("id", ""), label=t.get("label", params.label))
    return ActionResult.success(entity, f"Tag '{entity.label}' created.", refresh_panels=["pd_tags"])


@chat.function(
    "delete_tag",
    "Permanently delete a tag from the account -- removes it from every resource it was attached to.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_tag",
    effects=["pagerduty.tag.deleted"],
)
async def delete_tag(ctx, params: DeleteTagParams) -> ActionResult:
    """Delete a tag."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/tags/{params.tag_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Tag deleted.", refresh_panels=["pd_tags"])


@chat.function(
    "assign_tag",
    "Attach an existing tag to a user, team, escalation policy, or service.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.assign_tag",
    effects=["pagerduty.tag.assigned"],
)
async def assign_tag(ctx, params: AssignTagParams) -> ActionResult:
    """Attach a tag."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    entity_type = (params.entity_type or "").strip()
    if entity_type not in ("users", "teams", "escalation_policies", "services"):
        return ActionResult.error(_BAD_ENTITY_TYPE)
    payload = {"add": [{"type": "tag_reference", "id": params.tag_id}]}
    try:
        await pc.rest_request(ctx, "POST", f"/{entity_type}/{params.entity_id}/tags", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Tag attached.", refresh_panels=["pd_tags"])


@chat.function(
    "remove_tag_assignment",
    "Detach a tag from a user, team, escalation policy, or service.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.remove_tag_assignment",
    effects=["pagerduty.tag.unassigned"],
)
async def remove_tag_assignment(ctx, params: RemoveTagAssignmentParams) -> ActionResult:
    """Detach a tag."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    entity_type = (params.entity_type or "").strip()
    if entity_type not in ("users", "teams", "escalation_policies", "services"):
        return ActionResult.error(_BAD_ENTITY_TYPE)
    payload = {"remove": [{"type": "tag_reference", "id": params.tag_id}]}
    try:
        await pc.rest_request(ctx, "POST", f"/{entity_type}/{params.entity_id}/tags", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Tag detached.", refresh_panels=["pd_tags"])


# ── Custom fields ───────────────────────────────────────────────────────

@chat.function(
    "list_custom_fields",
    "List custom incident fields configured on the connected PagerDuty account -- structured metadata attachable to incidents.",
    action_type="read",
    chain_callable=True,
    data_model=CustomFieldList,
    event="pagerduty-connector.list_custom_fields",
)
async def list_custom_fields(ctx, params: ListCustomFieldsParams) -> ActionResult:
    """List custom fields."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        rows = await pc.rest_get_all(ctx, "/incidents/custom_fields", conn["api_key"], "fields")
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [
        CustomFieldEntry(id=f.get("id", ""), name=f.get("name", ""),
                          display_name=f.get("display_name", ""), data_type=f.get("data_type", ""),
                          field_type=f.get("field_type", ""))
        for f in rows
    ]
    return ActionResult.success(CustomFieldList(items=items), f"{len(items)} custom field(s).")


@chat.function(
    "create_custom_field",
    "Create a new custom incident field on the connected PagerDuty account.",
    action_type="write",
    chain_callable=True,
    data_model=CustomFieldEntry,
    event="pagerduty-connector.create_custom_field",
    effects=["pagerduty.custom_field.created"],
)
async def create_custom_field(ctx, params: CreateCustomFieldParams) -> ActionResult:
    """Create a custom field."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.name or not params.display_name:
        return ActionResult.error("Please provide both a machine name and a display name.")
    payload = {"field": {
        "name": params.name, "display_name": params.display_name,
        "data_type": params.data_type, "field_type": params.field_type,
    }}
    try:
        body = await pc.rest_request(ctx, "POST", "/incidents/custom_fields", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    f = body.get("field", {})
    entity = CustomFieldEntry(id=f.get("id", ""), name=f.get("name", params.name),
                               display_name=f.get("display_name", params.display_name),
                               data_type=f.get("data_type", params.data_type),
                               field_type=f.get("field_type", params.field_type))
    return ActionResult.success(entity, f"Custom field '{entity.display_name}' created.",
                                 refresh_panels=["pd_custom_fields"])


@chat.function(
    "delete_custom_field",
    "Permanently delete a custom incident field. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_custom_field",
    effects=["pagerduty.custom_field.deleted"],
)
async def delete_custom_field(ctx, params: DeleteCustomFieldParams) -> ActionResult:
    """Delete a custom field."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/incidents/custom_fields/{params.field_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Custom field deleted.", refresh_panels=["pd_custom_fields"])


@chat.function(
    "set_incident_custom_field",
    "Set a custom field's value on one specific incident.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.set_incident_custom_field",
    effects=["pagerduty.incident.custom_field_set"],
)
async def set_incident_custom_field(ctx, params: SetIncidentCustomFieldParams) -> ActionResult:
    """Set a custom field's value on an incident."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload = {"field_values": [{"field_id": params.field_id, "value": params.value}]}
    try:
        await pc.rest_request(
            ctx, "PUT", f"/incidents/{params.incident_id}/field_values", conn["api_key"], json_body=payload,
        )
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Custom field value set on incident.", refresh_panels=["pd_incidents"])
