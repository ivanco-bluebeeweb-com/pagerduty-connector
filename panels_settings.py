"""The single 'App settings' screen (center slot) -- connection management
(disconnect per account) and Integration Key management (save/list/delete,
for Events API v2 / Change Events API) for PagerDuty Connector. Split out
of panels.py per the same convention as MuleSoft Connector's / Stripe
Connector's panels_settings.py.

Per ~/UI_INTERFACE_STANDARD.md: the left sidebar never wraps the connect
form in a Card, and disconnect / secondary secret management (never
exposed in the sidebar itself) live here. The one secondary "App settings"
button sits LAST at the bottom of the sidebar. All setup instructions for
adding an Integration Key live only here (in this screen's own inline
copy) -- not duplicated in the sidebar.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from handlers_connection import _load_connections, _load_keys


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or c.get("subdomain") or c.get("id", "")
    return ui.Stack(direction="v", gap=1, align="start", children=[
        ui.Text(label, variant="body"),
        ui.Text(c.get("subdomain", ""), variant="caption"),
        ui.Button(
            "Disconnect", variant="danger", size="sm",
            on_click=ui.Call("disconnect_pagerduty", {"connection_id": c.get("id")}),
        ),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Stack(direction="v", gap=1, children=[
            ui.Text("Connections", variant="heading"),
            ui.Text("No PagerDuty accounts connected yet.", variant="caption"),
        ])
    children: list[ui.UINode] = [ui.Text("Connections", variant="heading")]
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, align="start", children=children)


def _key_row(k: dict) -> ui.UINode:
    return ui.Stack(direction="v", gap=1, align="start", children=[
        ui.Text(k.get("label") or k.get("id", ""), variant="body"),
        ui.Text(f"type: {k.get('kind', 'events')} · service: {k.get('service_id', '')}", variant="caption"),
        ui.Button(
            "Remove key", variant="danger", size="sm",
            on_click=ui.Call("delete_integration_key", {"key_id": k.get("id")}),
        ),
    ])


def _keys_section(keys: list[dict]) -> ui.UINode:
    if not keys:
        return ui.Stack(direction="v", gap=1, children=[
            ui.Text("Integration Keys (Events / Change Events)", variant="heading"),
            ui.Text("No integration keys saved yet.", variant="caption"),
        ])
    children: list[ui.UINode] = [ui.Text("Integration Keys (Events / Change Events)", variant="heading")]
    for i, k in enumerate(keys):
        if i > 0:
            children.append(ui.Divider())
        children.append(_key_row(k))
    return ui.Stack(direction="v", gap=2, align="start", children=children)


def _add_key_form() -> ui.UINode:
    return ui.Stack(direction="v", gap=2, align="stretch", children=[
        ui.Text(
            "Add a per-service Integration Key to send alerts (Events API "
            "v2) or change events (Change Events API) into that service. "
            "Find it on the service's Integrations tab in PagerDuty.",
            variant="caption",
        ),
        ui.Form(
            action="save_integration_key",
            submit_label="Save key",
            children=[
                ui.Text("PagerDuty service ID", variant="caption"),
                ui.Input(param_name="service_id",
                          placeholder="Service ID from list_services (e.g. PXXXXXX)"),
                ui.Text("Integration key (routing key)", variant="caption"),
                ui.Input(param_name="integration_key",
                          placeholder="32-character key from the service's Integrations tab"),
                ui.Text("Label", variant="caption"),
                ui.Input(param_name="label",
                          placeholder="e.g. Checkout API -- Events"),
                ui.Text("Key type", variant="caption"),
                ui.Select(param_name="kind",
                          options=[
                              {"label": "Events API v2 (alerts)", "value": "events"},
                              {"label": "Change Events API (deploys)", "value": "change"},
                          ]),
            ],
        ),
    ])


@ext.panel("pagerduty_settings", slot="center")
async def pagerduty_settings_panel(ctx) -> ui.UINode:
    connections = await _load_connections(ctx)
    keys = await _load_keys(ctx)
    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        ui.Header(text="PagerDuty -- App settings", level=2),
        _connections_section(connections),
        ui.Divider(),
        _keys_section(keys),
        ui.Divider(),
        _add_key_form(),
    ])
