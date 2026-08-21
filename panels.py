"""Panel UI -- connections list/connect form + open incidents / services
quick view in the left sidebar.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule (same convention as MuleSoft
Connector's / Stripe Connector's panels.py).

Every section is a plain ui.Stack, content stacked vertically and
left-aligned, sections separated by ui.Divider() -- no Card
border/background/shadow anywhere in this slot. Disconnect and Integration
Key management live only in the "App settings" screen (panels_settings.py).
The one secondary "App settings" button is always the LAST element at the
bottom of the sidebar.

Form container is stretched full-width (align="stretch") and its Input/
Password fields use native `label=`/`placeholder=` per
UI_INTERFACE_STANDARD.md's Label+Field+gap-container rule -- no separate
ui.Text label lines, no duplicated setup instructions here (the full
walkthrough lives only in pagerduty_connect_help's modal).
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from handlers_connection import _load_connections
import pagerduty_client as pc


def _settings_button() -> ui.UINode:
    """The one required secondary entry point into the settings screen --
    always the last element at the bottom of the sidebar."""
    return ui.Button(
        "App settings", variant="secondary", size="sm", full_width=True,
        icon="settings", on_click=ui.Call("__panel__pagerduty_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or c.get("subdomain") or c.get("id", "")
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(label, variant="body"),
        ui.Text(c.get("subdomain", ""), variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No PagerDuty accounts connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _incident_row(raw: dict) -> ui.UINode:
    svc = (raw.get("service") or {}).get("summary", "")
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(f"#{raw.get('incident_number', '')} · {raw.get('title', '')}", variant="body"),
        ui.Text(f"{raw.get('status', '')} · {raw.get('urgency', '')} · {svc}", variant="caption"),
    ])


def _incidents_section(incidents: list[dict]) -> ui.UINode:
    if not incidents:
        return ui.Text("No open incidents. 🎉", variant="caption")
    children: list[ui.UINode] = []
    for i, inc in enumerate(incidents):
        if i > 0:
            children.append(ui.Divider())
        children.append(_incident_row(inc))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    """Plain content, no Card wrapper. Stretched full-width per
    UI_INTERFACE_STANDARD.md (2026-08-20). No intro heading/description
    text here -- the full walkthrough lives ONLY in
    pagerduty_connect_help's modal (button below opens it); repeating it
    here would duplicate that instruction."""
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__pagerduty_connect_help")),
        ui.Form(
            action="connect_pagerduty",
            submit_label="Verify and connect",
            children=[
                ui.Text("REST API key", variant="caption"),
                ui.Input(param_name="api_key",
                          placeholder="Paste your PagerDuty REST API key"),
                ui.Text("From email (optional)", variant="caption"),
                ui.Input(param_name="from_email",
                          placeholder="you@yourcompany.com"),
                ui.Text("Label (optional)", variant="caption"),
                ui.Input(param_name="label",
                          placeholder="e.g. Production account"),
            ],
        ),
    ])


@ext.panel("pagerduty_connect", slot="left", title="PagerDuty", icon="🚨",
           default_width=320, min_width=260, max_width=420)
async def pagerduty_connect_panel(ctx, **kwargs) -> object:
    connections = await _load_connections(ctx)
    connected = bool(connections)

    header = ui.Header(text="PagerDuty", level=2,
                        subtitle="Manage incidents, on-call and alerting from Imperal")

    if not connected:
        return ui.Stack(direction="v", gap=4, align="stretch", children=[
            header,
            _connect_section(),
            ui.Divider(),
            _settings_button(),
        ])

    first = connections[0]
    incidents: list[dict] = []
    try:
        body = await pc.rest_request(
            ctx, "GET", "/incidents", first["api_key"],
            params={"statuses[]": ["triggered", "acknowledged"], "limit": 10},
        )
        incidents = body.get("incidents", [])
    except pc.ClientFail:
        incidents = []

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        ui.Text("Connected accounts", variant="subtitle"),
        _connections_section(connections),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        ui.Text(f"Open incidents -- {first.get('label') or first.get('subdomain', '')}", variant="subtitle"),
        _incidents_section(incidents),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("pagerduty_connect_help", slot="center",
           title="How to connect PagerDuty", center_overlay=True)
async def pagerduty_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. In PagerDuty, go to Integrations > Developer Tools > API Access Keys."),
        ui.Text("2. Click \"Create New API Key\", give it a description, and choose read/write access."),
        ui.Text("3. Copy the generated key immediately -- PagerDuty only shows it once."),
        ui.Text("4. Paste it into the form here and click \"Verify and connect\"."),
        ui.Divider(),
        ui.Alert(
            title="Separate keys for sending alerts",
            message=(
                "This REST API key manages configuration (incidents, "
                "services, schedules, etc.). To SEND alerts or change "
                "events into a specific service (Events API v2 / Change "
                "Events API), you also need that service's own Integration "
                "Key -- add one from App settings after connecting."
            ),
            type="info",
        ),
        ui.Divider(),
        ui.Link(
            label="Open PagerDuty's official API Access Keys guide",
            href="https://support.pagerduty.com/main/docs/api-access-keys",
        ),
    ])
    return ui.Dialog(
        title="How to connect PagerDuty",
        content=content,
        confirm_label="",
        cancel_label="Close",
    )


@ext.panel("pagerduty_center", slot="center", title="PagerDuty", icon="🚨", center_overlay=True)
async def pagerduty_center_panel(ctx, **kwargs) -> object:
    """Base center panel -- per UI_INTERFACE_STANDARD.md (2026-08-20).
    This app has no list/detail content of its own to show in the center
    by default (everything lives in the sidebar). MUST carry
    center_overlay=True: per docs.imperal.io/en/concepts/panels, a plain
    slot="center" panel is registered but the Panel app never fetches it
    at session-init without that flag. Text is the shared canonical
    wording -- must stay identical across every app in this situation."""
    return ui.Empty(
        message="Nothing to show here -- this app is managed entirely from the sidebar.",
        icon="👈",
    )
