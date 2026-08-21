"""Users and Teams management. Async, full @chat.function metadata,
ActionResult.success()/.error() -- same shape as MuleSoft Connector's
handlers.py.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import pagerduty_client as pc
from app import chat
from handlers_connection import resolve_connection
from schemas import (
    ListPdUsersParams, PdUserEntry, PdUserList,
    GetPdUserParams, CreatePdUserParams, UpdatePdUserParams, DeletePdUserParams,
    ListTeamsParams, TeamEntry, TeamList,
    CreateTeamParams, DeleteTeamParams,
    AddUserToTeamParams, RemoveUserFromTeamParams,
    DeleteResult,
)

_NO_CONN = "Connect a PagerDuty account first (connect_pagerduty)."


def _user_from(raw: dict) -> PdUserEntry:
    return PdUserEntry(
        id=raw.get("id", ""), name=raw.get("name", ""), email=raw.get("email", ""),
        role=raw.get("role", ""), time_zone=raw.get("time_zone", ""),
    )


@chat.function(
    "list_pd_users",
    "List users registered in the connected PagerDuty account, optionally filtered by name/email substring or team ids.",
    action_type="read",
    chain_callable=True,
    data_model=PdUserList,
    event="pagerduty-connector.list_pd_users",
)
async def list_pd_users(ctx, params: ListPdUsersParams) -> ActionResult:
    """List PagerDuty users."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q: dict = {}
    if params.query:
        q["query"] = params.query
    if params.team_ids:
        q["team_ids[]"] = [t.strip() for t in params.team_ids.split(",") if t.strip()]
    try:
        rows = await pc.rest_get_all(ctx, "/users", conn["api_key"], "users", params=q, limit=100)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [_user_from(u) for u in rows]
    return ActionResult.success(PdUserList(items=items), f"{len(items)} user(s).")


@chat.function(
    "get_pd_user",
    "Read one PagerDuty user's profile in full.",
    action_type="read",
    chain_callable=True,
    data_model=PdUserEntry,
    event="pagerduty-connector.get_pd_user",
)
async def get_pd_user(ctx, params: GetPdUserParams) -> ActionResult:
    """Read one PagerDuty user."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        body = await pc.rest_request(ctx, "GET", f"/users/{params.user_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    u = _user_from(body.get("user", {}))
    return ActionResult.success(u, f"User '{u.name}'.")


@chat.function(
    "create_pd_user",
    "Create a new user in the connected PagerDuty account and send them an invite email.",
    action_type="write",
    chain_callable=True,
    data_model=PdUserEntry,
    event="pagerduty-connector.create_pd_user",
    effects=["create:pagerduty_user"],
)
async def create_pd_user(ctx, params: CreatePdUserParams) -> ActionResult:
    """Create a new PagerDuty user."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.name or not params.email:
        return ActionResult.error("Please provide a name and email address.")
    payload = {"user": {"name": params.name, "email": params.email, "role": params.role or "user"}}
    try:
        body = await pc.rest_request(ctx, "POST", "/users", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    u = _user_from(body.get("user", {}))
    return ActionResult.success(u, f"User '{u.name or params.name}' created and invited.", refresh_panels=["pd_users"])


@chat.function(
    "update_pd_user",
    "Update an existing PagerDuty user's name and/or role. Only given fields change.",
    action_type="write",
    chain_callable=True,
    data_model=PdUserEntry,
    event="pagerduty-connector.update_pd_user",
    effects=["pagerduty.user.updated"],
)
async def update_pd_user(ctx, params: UpdatePdUserParams) -> ActionResult:
    """Update a PagerDuty user."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload: dict = {"user": {}}
    if params.name:
        payload["user"]["name"] = params.name
    if params.role:
        payload["user"]["role"] = params.role
    if not payload["user"]:
        return ActionResult.error("Nothing to update -- provide a new name or role.")
    try:
        body = await pc.rest_request(ctx, "PUT", f"/users/{params.user_id}", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    u = _user_from(body.get("user", {}))
    return ActionResult.success(u, "User updated.", refresh_panels=["pd_users"])


@chat.function(
    "delete_pd_user",
    "Permanently remove a user from the connected PagerDuty account. They are also removed from any schedules/escalation policies referencing them.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_pd_user",
    effects=["delete:pagerduty_user"],
)
async def delete_pd_user(ctx, params: DeletePdUserParams) -> ActionResult:
    """Delete a PagerDuty user."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/users/{params.user_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "User removed.", refresh_panels=["pd_users"])


def _team_from(raw: dict) -> TeamEntry:
    return TeamEntry(id=raw.get("id", ""), name=raw.get("name", ""), description=raw.get("description") or "")


@chat.function(
    "list_teams",
    "List teams defined in the connected PagerDuty account, optionally filtered by name substring.",
    action_type="read",
    chain_callable=True,
    data_model=TeamList,
    event="pagerduty-connector.list_teams",
)
async def list_teams(ctx, params: ListTeamsParams) -> ActionResult:
    """List PagerDuty teams."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    q: dict = {}
    if params.query:
        q["query"] = params.query
    try:
        body = await pc.rest_request(ctx, "GET", "/teams", conn["api_key"], params=q)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    items = [_team_from(t) for t in body.get("teams", [])]
    return ActionResult.success(TeamList(items=items), f"{len(items)} team(s).")


@chat.function(
    "create_team",
    "Create a new team to group users, services, and escalation policies.",
    action_type="write",
    chain_callable=True,
    data_model=TeamEntry,
    event="pagerduty-connector.create_team",
    effects=["create:pagerduty_team"],
)
async def create_team(ctx, params: CreateTeamParams) -> ActionResult:
    """Create a PagerDuty team."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    if not params.name:
        return ActionResult.error("Please provide a team name.")
    payload = {"team": {"name": params.name}}
    if params.description:
        payload["team"]["description"] = params.description
    try:
        body = await pc.rest_request(ctx, "POST", "/teams", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    t = _team_from(body.get("team", {}))
    return ActionResult.success(t, f"Team '{t.name or params.name}' created.", refresh_panels=["pd_teams"])


@chat.function(
    "delete_team",
    "Permanently delete a team. Members, services, and policies keep existing -- they simply lose this team association.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.delete_team",
    effects=["delete:pagerduty_team"],
)
async def delete_team(ctx, params: DeleteTeamParams) -> ActionResult:
    """Delete a PagerDuty team."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/teams/{params.team_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "Team deleted.", refresh_panels=["pd_teams"])


@chat.function(
    "add_user_to_team",
    "Add a user to a team with a given role (manager or member).",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.add_user_to_team",
    effects=["pagerduty.team.member_added"],
)
async def add_user_to_team(ctx, params: AddUserToTeamParams) -> ActionResult:
    """Add a user to a team."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    payload = {"role": params.role or "manager"}
    try:
        await pc.rest_request(ctx, "PUT", f"/teams/{params.team_id}/users/{params.user_id}", conn["api_key"], json_body=payload)
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "User added to team.", refresh_panels=["pd_teams"])


@chat.function(
    "remove_user_from_team",
    "Remove a user from a team.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="pagerduty-connector.remove_user_from_team",
    effects=["pagerduty.team.member_removed"],
)
async def remove_user_from_team(ctx, params: RemoveUserFromTeamParams) -> ActionResult:
    """Remove a user from a team."""
    conn = await resolve_connection(ctx, params.connection_id)
    if not conn:
        return ActionResult.error(_NO_CONN)
    try:
        await pc.rest_request(ctx, "DELETE", f"/teams/{params.team_id}/users/{params.user_id}", conn["api_key"])
    except pc.ClientFail as e:
        return ActionResult.error(str(e))
    return ActionResult.success({}, "User removed from team.", refresh_panels=["pd_teams"])
