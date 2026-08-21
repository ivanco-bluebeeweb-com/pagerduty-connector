"""Pydantic params models + SDL entity contracts for PagerDuty Connector.

All params models are module-scope (V17 federal invariant, same rule as
MuleSoft Connector / Stripe Connector's schemas.py). Organized by domain to
match handlers_*.py split (connection, incidents, services, escalation,
schedules/oncalls, users/teams, business services, custom fields/tags,
event orchestration, incident workflows, automation actions, webhooks,
events/change-events, analytics/audit).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectPagerdutyParams(BaseModel):
    api_key: str = Field(
        "",
        description="Your PagerDuty REST API key (Integrations > Developer Tools > API Access Keys).",
    )
    from_email: str = Field(
        "",
        description="Email of a PagerDuty user this key acts as for write requests requiring a From header (required by some endpoints, e.g. creating incidents).",
    )
    label: str = Field("", description="Optional friendly name for this connection.")


class ProviderConnection(sdl.Entity):
    id: str = ""
    title: str = ""
    connected: bool = False
    detail: str = ""
    subdomain: str = ""


class ProviderConnectionList(sdl.Entity):
    items: list[ProviderConnection] = Field(default_factory=list)


class DisconnectPagerdutyParams(BaseModel):
    connection_id: str = Field("", description="Connection id to disconnect, from list_connections.")


class DeleteResult(sdl.Entity):
    ok: bool = False
    detail: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Integration keys (Events API v2 / Change Events routing keys per service)
# ──────────────────────────────────────────────────────────────────────────


class SaveIntegrationKeyParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="PagerDuty service id this integration key belongs to, from list_services.")
    kind: str = Field("events", description="Which surface this key routes to: 'events' (Events API v2 trigger/ack/resolve) or 'change' (Change Events API).")
    integration_key: str = Field("", description="The 32-character Integration Key (routing_key) shown on the service's integration page.")
    label: str = Field("", description="Optional friendly name, e.g. 'Production monitoring'.")


class IntegrationKeyEntry(sdl.Entity):
    id: str = ""
    service_id: str = ""
    kind: str = ""
    label: str = ""
    masked_key: str = ""


class IntegrationKeyList(sdl.Entity):
    items: list[IntegrationKeyEntry] = Field(default_factory=list)


class DeleteIntegrationKeyParams(BaseModel):
    key_id: str = Field("", description="Integration key id to remove, from list_integration_keys.")


# ──────────────────────────────────────────────────────────────────────────
# Incidents
# ──────────────────────────────────────────────────────────────────────────


class ListIncidentsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    statuses: str = Field("", description="Comma-separated statuses to filter by: triggered, acknowledged, resolved. Empty means all.")
    service_ids: str = Field("", description="Comma-separated service ids to filter by. Empty means all services.")
    urgency: str = Field("", description="Filter by urgency: 'high' or 'low'. Empty means both.")
    since: str = Field("", description="ISO8601 start of date range, e.g. 2026-08-01T00:00:00Z.")
    until: str = Field("", description="ISO8601 end of date range, e.g. 2026-08-21T00:00:00Z.")
    limit: int = Field(25, description="Max incidents to return (1-100).")
    offset: int = Field(0, description="Pagination offset.")


class Incident(sdl.Entity):
    id: str = ""
    incident_number: int = 0
    title: str = ""
    status: str = ""
    urgency: str = ""
    service_id: str = ""
    service_name: str = ""
    escalation_policy_name: str = ""
    created_at: str = ""
    html_url: str = ""
    assignees: str = ""


class IncidentList(sdl.Entity):
    items: list[Incident] = Field(default_factory=list)
    total: int = 0


class GetIncidentParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")


class CreateIncidentParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="Service this incident belongs to, from list_services.")
    title: str = Field("", description="Short incident title, e.g. 'Checkout API returning 500s'.")
    urgency: str = Field("high", description="Urgency: 'high' or 'low'.")
    body_details: str = Field("", description="Longer free-text details describing the incident.")
    escalation_policy_id: str = Field("", description="Optional escalation policy id to override the service default, from list_escalation_policies.")


class UpdateIncidentStatusParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")
    status: str = Field("", description="New status: 'acknowledged' or 'resolved'.")


class ReassignIncidentParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")
    user_ids: str = Field("", description="Comma-separated PagerDuty user ids to assign, from list_users.")


class UpdateIncidentPriorityParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")
    priority_id: str = Field("", description="Priority id to set, from list_priorities. Empty clears the priority.")


class MergeIncidentsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    target_incident_id: str = Field("", description="Incident id that survives the merge, from list_incidents.")
    source_incident_ids: str = Field("", description="Comma-separated incident ids to merge into the target.")


class SnoozeIncidentParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")
    duration_seconds: int = Field(3600, description="How long to snooze re-notification for, in seconds.")


class AddIncidentNoteParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")
    content: str = Field("", description="Note text to add to the incident.")


class IncidentNoteEntry(sdl.Entity):
    id: str = ""
    content: str = ""
    created_at: str = ""
    author: str = ""


class IncidentNoteList(sdl.Entity):
    items: list[IncidentNoteEntry] = Field(default_factory=list)


class ListIncidentNotesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")


class ListIncidentAlertsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")


class IncidentAlertEntry(sdl.Entity):
    id: str = ""
    status: str = ""
    summary: str = ""
    created_at: str = ""


class IncidentAlertList(sdl.Entity):
    items: list[IncidentAlertEntry] = Field(default_factory=list)


class ListIncidentLogEntriesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")


class IncidentLogEntryItem(sdl.Entity):
    id: str = ""
    type: str = ""
    summary: str = ""
    created_at: str = ""
    agent: str = ""


class IncidentLogEntryList(sdl.Entity):
    items: list[IncidentLogEntryItem] = Field(default_factory=list)


class RunResponsePlayParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")
    response_play_id: str = Field("", description="Response play id to run, from list_response_plays.")


class BulkIncidentActionParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_ids: str = Field("", description="Comma-separated incident ids to act on, from list_incidents.")
    status: str = Field("", description="New status to apply to all: 'acknowledged' or 'resolved'.")


class BulkIncidentResultItem(sdl.Entity):
    incident_id: str = ""
    ok: bool = False
    detail: str = ""


class BulkIncidentResult(sdl.Entity):
    items: list[BulkIncidentResultItem] = Field(default_factory=list)
    succeeded: int = 0
    failed: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Services
# ──────────────────────────────────────────────────────────────────────────


class ListServicesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    query: str = Field("", description="Filter services by name substring.")
    limit: int = Field(25, description="Max services to return (1-100).")
    offset: int = Field(0, description="Pagination offset.")


class ServiceEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    status: str = ""
    escalation_policy_id: str = ""
    escalation_policy_name: str = ""
    description: str = ""
    html_url: str = ""


class ServiceList(sdl.Entity):
    items: list[ServiceEntry] = Field(default_factory=list)
    total: int = 0


class GetServiceParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="Service id, from list_services.")


class CreateServiceParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Service name, e.g. 'Checkout API'.")
    escalation_policy_id: str = Field("", description="Escalation policy id this service uses, from list_escalation_policies.")
    description: str = Field("", description="Optional description of what this service represents.")
    alert_creation: str = Field("create_alerts_and_incidents", description="How alerts become incidents: 'create_alerts_and_incidents' or 'create_incidents'.")


class UpdateServiceParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="Service id, from list_services.")
    name: str = Field("", description="New service name. Leave empty to keep current.")
    description: str = Field("", description="New description. Leave empty to keep current.")
    escalation_policy_id: str = Field("", description="New escalation policy id. Leave empty to keep current.")


class DeleteServiceParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="Service id to permanently delete, from list_services.")


class ListServiceIntegrationsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="Service id, from list_services.")


class ServiceIntegrationEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    type: str = ""
    integration_key: str = ""


class ServiceIntegrationList(sdl.Entity):
    items: list[ServiceIntegrationEntry] = Field(default_factory=list)


class CreateServiceIntegrationParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="Service id, from list_services.")
    name: str = Field("", description="Integration name, e.g. 'Datadog' or 'Prometheus'.")
    vendor_id: str = Field("", description="Optional PagerDuty vendor id for a known integration type (e.g. Datadog's vendor id). Leave empty for a generic Events API v2 integration.")


class DeleteServiceIntegrationParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    service_id: str = Field("", description="Service id, from list_services.")
    integration_id: str = Field("", description="Integration id to remove, from list_service_integrations.")


# ──────────────────────────────────────────────────────────────────────────
# Escalation policies
# ──────────────────────────────────────────────────────────────────────────


class ListEscalationPoliciesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    query: str = Field("", description="Filter escalation policies by name substring.")


class EscalationPolicyEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    num_loops: int = 0
    on_call_handoff_notifications: str = ""
    num_rules: int = 0


class EscalationPolicyList(sdl.Entity):
    items: list[EscalationPolicyEntry] = Field(default_factory=list)


class GetEscalationPolicyParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    escalation_policy_id: str = Field("", description="Escalation policy id, from list_escalation_policies.")


class CreateEscalationPolicyParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Escalation policy name, e.g. 'Primary On-Call'.")
    user_ids_level_1: str = Field("", description="Comma-separated user ids for the first escalation level, from list_users.")
    escalation_delay_minutes: int = Field(30, description="Minutes to wait before escalating to the next level if unacknowledged.")
    num_loops: int = Field(1, description="How many times to repeat the escalation rules if nobody acknowledges.")


class UpdateEscalationPolicyParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    escalation_policy_id: str = Field("", description="Escalation policy id, from list_escalation_policies.")
    name: str = Field("", description="New name. Leave empty to keep current.")
    num_loops: int = Field(0, description="New loop count. 0 leaves current value unchanged.")


class DeleteEscalationPolicyParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    escalation_policy_id: str = Field("", description="Escalation policy id to permanently delete, from list_escalation_policies.")


# ──────────────────────────────────────────────────────────────────────────
# Schedules & on-calls
# ──────────────────────────────────────────────────────────────────────────


class ListSchedulesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    query: str = Field("", description="Filter schedules by name substring.")


class ScheduleEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    time_zone: str = ""
    description: str = ""
    html_url: str = ""


class ScheduleList(sdl.Entity):
    items: list[ScheduleEntry] = Field(default_factory=list)


class GetScheduleParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    schedule_id: str = Field("", description="Schedule id, from list_schedules.")
    since: str = Field("", description="ISO8601 start of the window to render, e.g. 2026-08-01T00:00:00Z.")
    until: str = Field("", description="ISO8601 end of the window to render, e.g. 2026-08-31T00:00:00Z.")


class CreateScheduleParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Schedule name, e.g. 'Primary On-Call Rotation'.")
    time_zone: str = Field("UTC", description="IANA time zone name, e.g. 'America/New_York'.")
    user_ids: str = Field("", description="Comma-separated user ids in rotation order, from list_users.")
    rotation_turn_length_seconds: int = Field(604800, description="Length of each rotation turn in seconds. Default 604800 = 1 week.")
    rotation_start: str = Field("", description="ISO8601 start of the first rotation turn, e.g. 2026-08-01T09:00:00Z.")


class DeleteScheduleParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    schedule_id: str = Field("", description="Schedule id to permanently delete, from list_schedules.")


class CreateScheduleOverrideParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    schedule_id: str = Field("", description="Schedule id, from list_schedules.")
    user_id: str = Field("", description="User id to cover this override slot, from list_users.")
    start: str = Field("", description="ISO8601 start of the override, e.g. 2026-08-22T00:00:00Z.")
    end: str = Field("", description="ISO8601 end of the override, e.g. 2026-08-23T00:00:00Z.")


class DeleteScheduleOverrideParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    schedule_id: str = Field("", description="Schedule id, from list_schedules.")
    override_id: str = Field("", description="Override id to remove.")


class ListOncallsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    schedule_ids: str = Field("", description="Comma-separated schedule ids to filter by. Empty means all.")
    escalation_policy_ids: str = Field("", description="Comma-separated escalation policy ids to filter by. Empty means all.")
    user_ids: str = Field("", description="Comma-separated user ids to filter by. Empty means all.")
    since: str = Field("", description="ISO8601 start of the window.")
    until: str = Field("", description="ISO8601 end of the window.")


class OncallEntry(sdl.Entity):
    user_id: str = ""
    user_name: str = ""
    schedule_id: str = ""
    schedule_name: str = ""
    escalation_policy_id: str = ""
    escalation_policy_name: str = ""
    escalation_level: int = 0
    start: str = ""
    end: str = ""


class OncallList(sdl.Entity):
    items: list[OncallEntry] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# Users & teams
# ──────────────────────────────────────────────────────────────────────────


class ListPdUsersParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    query: str = Field("", description="Filter users by name/email substring.")
    team_ids: str = Field("", description="Comma-separated team ids to filter by. Empty means all teams.")


class PdUserEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    email: str = ""
    role: str = ""
    time_zone: str = ""


class PdUserList(sdl.Entity):
    items: list[PdUserEntry] = Field(default_factory=list)


class GetPdUserParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    user_id: str = Field("", description="User id, from list_pd_users.")


class CreatePdUserParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Full name of the new user.")
    email: str = Field("", description="Email address of the new user -- PagerDuty sends them an invite.")
    role: str = Field("user", description="Role to assign: owner, admin, manager, responder, observer, stakeholder, limited_stakeholder, restricted_access, read_only_user, or user.")


class UpdatePdUserParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    user_id: str = Field("", description="User id, from list_pd_users.")
    name: str = Field("", description="New name. Leave empty to keep current.")
    role: str = Field("", description="New role. Leave empty to keep current.")


class DeletePdUserParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    user_id: str = Field("", description="User id to permanently remove, from list_pd_users.")


class ListTeamsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    query: str = Field("", description="Filter teams by name substring.")


class TeamEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    description: str = ""


class TeamList(sdl.Entity):
    items: list[TeamEntry] = Field(default_factory=list)


class CreateTeamParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Team name, e.g. 'Platform Reliability'.")
    description: str = Field("", description="Optional description of the team's purpose.")


class DeleteTeamParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    team_id: str = Field("", description="Team id to permanently delete, from list_teams.")


class AddUserToTeamParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    team_id: str = Field("", description="Team id, from list_teams.")
    user_id: str = Field("", description="User id to add, from list_pd_users.")
    role: str = Field("manager", description="Team role for this user: 'manager' or 'responder'.")


class RemoveUserFromTeamParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    team_id: str = Field("", description="Team id, from list_teams.")
    user_id: str = Field("", description="User id to remove, from list_pd_users.")


# ──────────────────────────────────────────────────────────────────────────
# Business services, priorities, tags
# ──────────────────────────────────────────────────────────────────────────


class ListBusinessServicesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    query: str = Field("", description="Filter business services by name substring.")


class BusinessServiceEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    description: str = ""
    point_of_contact: str = ""


class BusinessServiceList(sdl.Entity):
    items: list[BusinessServiceEntry] = Field(default_factory=list)


class CreateBusinessServiceParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Business service name, e.g. 'Online Checkout'.")
    description: str = Field("", description="What this business capability represents to non-technical stakeholders.")
    point_of_contact: str = Field("", description="Free-text name/contact for who owns this business service.")


class UpdateBusinessServiceParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    business_service_id: str = Field("", description="Business service id, from list_business_services.")
    name: str = Field("", description="New name. Leave empty to keep current.")
    description: str = Field("", description="New description. Leave empty to keep current.")


class DeleteBusinessServiceParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    business_service_id: str = Field("", description="Business service id to permanently delete, from list_business_services.")


class AddServiceDependencyParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    business_service_id: str = Field("", description="Business service id, from list_business_services.")
    technical_service_id: str = Field("", description="Technical (regular) service id that supports it, from list_services.")


class RemoveServiceDependencyParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    dependency_id: str = Field("", description="Dependency id to remove, from list_service_dependencies.")


class ListServiceDependenciesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    business_service_id: str = Field("", description="Business service id, from list_business_services.")


class ServiceDependencyEntry(sdl.Entity):
    id: str = ""
    business_service_id: str = ""
    technical_service_id: str = ""
    technical_service_name: str = ""


class ServiceDependencyList(sdl.Entity):
    items: list[ServiceDependencyEntry] = Field(default_factory=list)


class ListPrioritiesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class PriorityEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    description: str = ""


class PriorityList(sdl.Entity):
    items: list[PriorityEntry] = Field(default_factory=list)


class ListTagsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    query: str = Field("", description="Filter tags by label substring.")


class TagEntry(sdl.Entity):
    id: str = ""
    label: str = ""


class TagList(sdl.Entity):
    items: list[TagEntry] = Field(default_factory=list)


class CreateTagParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    label: str = Field("", description="Tag label, e.g. 'payments-team' or 'tier-1'.")


class DeleteTagParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    tag_id: str = Field("", description="Tag id to permanently delete, from list_tags.")


class AssignTagParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    tag_id: str = Field("", description="Tag id, from list_tags.")
    entity_type: str = Field("", description="Type of the entity to tag: 'users', 'teams', 'escalation_policies', or 'services'.")
    entity_id: str = Field("", description="Id of the entity to attach the tag to.")


class RemoveTagAssignmentParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    tag_id: str = Field("", description="Tag id, from list_tags.")
    entity_type: str = Field("", description="Type of the entity to untag: 'users', 'teams', 'escalation_policies', or 'services'.")
    entity_id: str = Field("", description="Id of the entity to remove the tag from.")


class ListCustomFieldsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class CustomFieldEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    display_name: str = ""
    data_type: str = ""
    field_type: str = ""


class CustomFieldList(sdl.Entity):
    items: list[CustomFieldEntry] = Field(default_factory=list)


class CreateCustomFieldParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Internal machine name for the field, e.g. 'affected_region'.")
    display_name: str = Field("", description="Human-readable label shown on incidents, e.g. 'Affected Region'.")
    data_type: str = Field("string", description="Field data type: string, integer, float, boolean, url, or datetime.")
    field_type: str = Field("single_value", description="single_value, single_value_fixed, multi_value, or multi_value_fixed.")


class DeleteCustomFieldParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    field_id: str = Field("", description="Custom field id to permanently delete, from list_custom_fields.")


class SetIncidentCustomFieldParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id, from list_incidents.")
    field_id: str = Field("", description="Custom field id, from list_custom_fields.")
    value: str = Field("", description="Value to set on this incident for the field.")


# ──────────────────────────────────────────────────────────────────────────
# Event orchestration
# ──────────────────────────────────────────────────────────────────────────


class ListEventOrchestrationsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class EventOrchestrationEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    routes: int = 0


class EventOrchestrationList(sdl.Entity):
    items: list[EventOrchestrationEntry] = Field(default_factory=list)


class CreateEventOrchestrationParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    name: str = Field("", description="Orchestration name, e.g. 'Production alert routing'.")
    team_id: str = Field("", description="Optional team id that owns this orchestration, from list_teams.")


class GetEventOrchestrationParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    orchestration_id: str = Field("", description="Orchestration id, from list_event_orchestrations.")


class DeleteEventOrchestrationParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    orchestration_id: str = Field("", description="Orchestration id to permanently delete, from list_event_orchestrations.")


class GetEventOrchestrationRouterParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    orchestration_id: str = Field("", description="Orchestration id, from list_event_orchestrations.")


class EventOrchestrationRouterInfo(sdl.Entity):
    orchestration_id: str = ""
    num_rules: int = 0
    catch_all_service_id: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Incident workflows
# ──────────────────────────────────────────────────────────────────────────


class ListIncidentWorkflowsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class IncidentWorkflowEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    description: str = ""
    num_steps: int = 0


class IncidentWorkflowList(sdl.Entity):
    items: list[IncidentWorkflowEntry] = Field(default_factory=list)


class GetIncidentWorkflowParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    workflow_id: str = Field("", description="Incident workflow id, from list_incident_workflows.")


class RunIncidentWorkflowParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    workflow_id: str = Field("", description="Incident workflow id to trigger manually, from list_incident_workflows.")
    incident_id: str = Field("", description="Incident id this workflow instance runs against, from list_incidents.")


class ListIncidentWorkflowTriggersParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class IncidentWorkflowTriggerEntry(sdl.Entity):
    id: str = ""
    workflow_id: str = ""
    type: str = ""
    service_id: str = ""


class IncidentWorkflowTriggerList(sdl.Entity):
    items: list[IncidentWorkflowTriggerEntry] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# Automation actions
# ──────────────────────────────────────────────────────────────────────────


class ListAutomationActionsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class AutomationActionEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    description: str = ""
    action_type: str = ""
    runner_id: str = ""


class AutomationActionList(sdl.Entity):
    items: list[AutomationActionEntry] = Field(default_factory=list)


class GetAutomationActionParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    action_id: str = Field("", description="Automation action id, from list_automation_actions.")


class InvokeAutomationActionOnIncidentParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    incident_id: str = Field("", description="Incident id to run the action against, from list_incidents.")
    action_id: str = Field("", description="Automation action id to invoke, from list_automation_actions.")


class ListAutomationRunnersParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class AutomationRunnerEntry(sdl.Entity):
    id: str = ""
    name: str = ""
    runner_type: str = ""
    last_seen: str = ""


class AutomationRunnerList(sdl.Entity):
    items: list[AutomationRunnerEntry] = Field(default_factory=list)


class TriggerIncidentWorkflowParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    workflow_id: str = Field("", description="Incident workflow id, from list_incident_workflows.")
    incident_id: str = Field("", description="Incident id to run the workflow against, from list_incidents.")


class ListIncidentWorkflowInstancesParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    workflow_id: str = Field("", description="Optional workflow id to filter by, from list_incident_workflows.")


class IncidentWorkflowInstanceEntry(sdl.Entity):
    id: str = ""
    workflow_id: str = ""
    incident_id: str = ""
    status: str = ""
    created_at: str = ""


class IncidentWorkflowInstanceList(sdl.Entity):
    items: list[IncidentWorkflowInstanceEntry] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# Webhooks
# ──────────────────────────────────────────────────────────────────────────


class ListWebhookSubscriptionsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class WebhookSubscriptionEntry(sdl.Entity):
    id: str = ""
    description: str = ""
    delivery_url: str = ""
    events: str = ""
    active: bool = False
    filter_type: str = ""
    filter_id: str = ""


class WebhookSubscriptionList(sdl.Entity):
    items: list[WebhookSubscriptionEntry] = Field(default_factory=list)


class CreateWebhookSubscriptionParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    delivery_url: str = Field("", description="Your own HTTPS endpoint PagerDuty will POST events to.")
    description: str = Field("", description="Short description of what this webhook is for.")
    events: str = Field(
        "incident.triggered,incident.acknowledged,incident.resolved",
        description="Comma-separated event types to subscribe to, e.g. incident.triggered, incident.acknowledged, incident.resolved, incident.escalated, incident.reassigned.",
    )
    filter_type: str = Field("account_reference", description="Scope of the subscription: 'account_reference' (whole account) or 'service_reference' (one service).")
    filter_id: str = Field("", description="Service id to scope to, required only when filter_type is 'service_reference'.")


class GetWebhookSubscriptionParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    webhook_id: str = Field("", description="Webhook subscription id, from list_webhook_subscriptions.")


class UpdateWebhookSubscriptionParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    webhook_id: str = Field("", description="Webhook subscription id, from list_webhook_subscriptions.")
    delivery_url: str = Field("", description="New delivery URL. Leave empty to keep current.")
    active: bool = Field(True, description="Whether the webhook subscription is active.")


class DeleteWebhookSubscriptionParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    webhook_id: str = Field("", description="Webhook subscription id to permanently delete, from list_webhook_subscriptions.")


class PingWebhookSubscriptionParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    webhook_id: str = Field("", description="Webhook subscription id to send a test ping to, from list_webhook_subscriptions.")


# ──────────────────────────────────────────────────────────────────────────
# Events API v2 (send alerts) & Change Events API
# ──────────────────────────────────────────────────────────────────────────


class TriggerEventParams(BaseModel):
    integration_key_id: str = Field("", description="Saved integration key id, from list_integration_keys. Leave empty if passing routing_key directly.")
    routing_key: str = Field("", description="The Service Integration's Events API v2 routing/integration key (used only if integration_key_id is empty).")
    summary: str = Field("", description="Short human-readable alert summary, e.g. 'Disk usage above 90% on prod-db-1'.")
    source: str = Field("", description="What system detected this, e.g. 'monitoring-service' or a hostname.")
    severity: str = Field("critical", description="Alert severity: critical, error, warning, or info.")
    dedup_key: str = Field("", description="Optional key to group related events into one alert. Leave empty to auto-generate.")
    component: str = Field("", description="Optional component affected, e.g. 'postgres'.")
    group: str = Field("", description="Optional logical grouping, e.g. 'production-db-cluster'.")
    custom_details: str = Field("", description="Optional JSON string of extra key/value context to attach to the alert.")


class AckOrResolveEventParams(BaseModel):
    integration_key_id: str = Field("", description="Saved integration key id, from list_integration_keys. Leave empty if passing routing_key directly.")
    routing_key: str = Field("", description="The Service Integration's Events API v2 routing/integration key (used only if integration_key_id is empty).")
    dedup_key: str = Field("", description="The dedup_key of the alert to acknowledge or resolve, from the original trigger response.")
    event_action: str = Field("resolve", description="'acknowledge' or 'resolve'.")


class EventResult(sdl.Entity):
    ok: bool = False
    dedup_key: str = ""
    detail: str = ""


class SendChangeEventParams(BaseModel):
    integration_key_id: str = Field("", description="Saved integration key id, from list_integration_keys. Leave empty if passing routing_key directly.")
    routing_key: str = Field("", description="The Service Integration's Change Events API routing/integration key (used only if integration_key_id is empty).")
    summary: str = Field("", description="Short description of the change, e.g. 'Deployed checkout-service v2.14.0'.")
    source: str = Field("", description="What system triggered this change, e.g. 'ci-cd-pipeline'.")
    custom_details: str = Field("", description="Optional JSON string of extra key/value context (commit sha, PR link, etc.).")
    link_url: str = Field("", description="Optional URL linking to more details (e.g. the deploy pipeline run).")
    link_text: str = Field("", description="Label for link_url. Defaults to 'Details' if left empty.")


class ChangeEventResult(sdl.Entity):
    ok: bool = False
    id: str = ""
    detail: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Analytics & audit
# ──────────────────────────────────────────────────────────────────────────


class GetIncidentAnalyticsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    since: str = Field("", description="ISO8601 start of the analytics window, e.g. 2026-07-21T00:00:00Z.")
    until: str = Field("", description="ISO8601 end of the analytics window, e.g. 2026-08-21T00:00:00Z.")
    service_ids: str = Field("", description="Comma-separated service ids to filter by. Empty means all services.")


class IncidentAnalyticsRow(sdl.Entity):
    service_id: str = ""
    service_name: str = ""
    incident_count: int = 0
    mean_seconds_to_ack: float = 0.0
    mean_seconds_to_resolve: float = 0.0
    mean_engaged_seconds: float = 0.0
    mean_engaged_user_count: float = 0.0


class IncidentAnalyticsReport(sdl.Entity):
    rows: list[IncidentAnalyticsRow] = Field(default_factory=list)


class ListAuditRecordsParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")
    since: str = Field("", description="ISO8601 start of the audit window, e.g. 2026-08-14T00:00:00Z.")
    until: str = Field("", description="ISO8601 end of the audit window, e.g. 2026-08-21T00:00:00Z.")
    actions: str = Field("", description="Comma-separated action types to filter by, e.g. 'create,update,delete'. Empty means all.")


class AuditRecordEntry(sdl.Entity):
    id: str = ""
    action: str = ""
    actor_name: str = ""
    execution_time: str = ""
    root_resource_type: str = ""
    root_resource_id: str = ""


class AuditRecordList(sdl.Entity):
    items: list[AuditRecordEntry] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# Value-add: account health audit (Tier 3)
# ──────────────────────────────────────────────────────────────────────────


class AuditAccountParams(BaseModel):
    connection_id: str = Field("", description="Connection id, from list_connections.")


class AccountAuditRow(sdl.Entity):
    service_id: str = ""
    service_name: str = ""
    open_incidents: int = 0
    escalation_policy_name: str = ""
    has_no_integrations: bool = False
    status: str = ""


class AccountAuditReport(sdl.Entity):
    rows: list[AccountAuditRow] = Field(default_factory=list)
    total_services: int = 0
    total_open_incidents: int = 0
    services_without_integrations: int = 0
    services_disabled: int = 0
