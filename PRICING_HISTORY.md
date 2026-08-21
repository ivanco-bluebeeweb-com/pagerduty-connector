## 2026-08-21 (same day, later) — Live platform application confirmed via `developer.update_pricing`

Deployed the app (`deploy_app` → 20/21, only the advisory "no files >300
lines" warning remains — same class of warning MuleSoft/Stripe also
carry), created the GitHub repo (public, `ivanco-bluebeeweb-com/pagerduty-connector`),
registered the app on the platform (`developer.create_app`, category
`automation`), then called `developer.update_pricing` **with the explicit
`revenue_split_dev=95` parameter** (partner tier, per `create_app`'s own
returned `revenue_split_dev: 95`) — not just inside `pricing_config`. This
follows PRICING_POLICY.md §3 to the letter: an earlier `update_pricing`
call in this same session omitted the top-level `revenue_split_dev`
parameter and would have silently echoed success without the price
actually reflecting in the panel (the exact MuleSoft/n8n-session bug the
policy document exists to prevent) — caught and corrected before
`submit_for_review`, not after.

Sequence executed, in order: `deploy_app` → `update_pricing` (with
`revenue_split_dev=95`) → `deploy_app` again (manifest re-sync) →
`submit_for_review` (all 4 platform checks passed: git_url_https,
display_name_set, description_set, last_deploy_succeeded) → app now
`pending_review`.

Per the platform's own known limitation (Imperal Cloud task #2113, still
open as of this policy's writing): neither `update_pricing` nor any
read-back tool (`marketplace.get_app_details`) actually echoes the saved
`tool_prices` back — so this cannot be verified purely programmatically.
The call included the required `revenue_split_dev` this time, which is
documented as the confirmed-working method (n8n Connector, 2026-08-19).
Final human visual confirmation in Developer → My Apps → PagerDuty →
Pricing is still recommended before considering this fully closed.

---

# PagerDuty Connector — Pricing History

Canonical scale and process: `/Users/vladivanco/Documents/Imperal OS/PRICING_POLICY.md`.
Fixed scale `{0, 8, 16, 20, 40, 60}` tokens per call, `per_action` model,
`monthly_price: 0`. No Google Cloud/Workspace markup applies — PagerDuty is
not a Google-backed API.

---

## 2026-08-21 — Initial pricing, set after clean post-audit (0 errors, `imperal validate`)

Priced all 92 chat functions before `submit_for_review`, per policy §1
(pricing before submission, never after — the MuleSoft Connector mistake
this policy exists to prevent).

**0 tokens — connection & integration-key management (local secret store,
no external API billing event):**
- `connect_pagerduty`, `disconnect_pagerduty`, `list_connections` — same
  reasoning as every other BYOK connector on this platform: setting up or
  removing your own saved credential, or listing what's already stored
  locally, isn't a paid action.
- `save_integration_key`, `list_integration_keys`, `delete_integration_key`
  — these manage a *locally stored* JSON array of routing keys (Events
  API v2 / Change Events API credentials scoped per-service). No call to
  PagerDuty's API is made to save/list/delete them — same "local inventory,
  free" reasoning as WordPress Hub's `list_sites`.

**8 tokens — plain reads (`list_*`, `get_*`):** every read-only call that
hits PagerDuty's REST API costs 8 — `list_incidents`, `get_incident`,
`list_services`, `get_service`, `list_schedules`, `get_schedule`,
`list_oncalls`, `list_pd_users`, `get_pd_user`, `list_teams`,
`list_escalation_policies`, `get_escalation_policy`,
`list_service_integrations`, `list_service_dependencies`,
`list_business_services`, `list_priorities`, `list_tags`,
`list_custom_fields`, `list_event_orchestrations`, `get_event_orchestration`,
`get_event_orchestration_router`, `list_incident_workflows`,
`get_incident_workflow`, `list_incident_workflow_triggers`,
`list_automation_actions`, `get_automation_action`,
`list_automation_runners`, `list_webhook_subscriptions`,
`get_webhook_subscription`, `get_incident_analytics`, `list_audit_records`,
`list_incident_notes`, `list_incident_alerts`, `list_incident_log_entries`
— reading an external API is real work, never free just because it's a
read (policy §2).

**16 tokens — standard single-entity write/delete:** ordinary
create/update/delete on one object — `create_incident`,
`update_incident_status` (ack/resolve/reopen), `reassign_incident`,
`update_incident_priority`, `snooze_incident`, `add_incident_note`,
`create_service`, `update_service`, `delete_service`,
`create_service_integration`, `delete_service_integration`,
`create_escalation_policy`, `update_escalation_policy`,
`delete_escalation_policy`, `create_schedule`, `delete_schedule`,
`create_schedule_override`, `delete_schedule_override`, `create_pd_user`,
`update_pd_user`, `delete_pd_user`, `create_team`, `delete_team`,
`add_user_to_team`, `remove_user_from_team`, `create_business_service`,
`update_business_service`, `delete_business_service`,
`add_service_dependency`, `remove_service_dependency`, `create_tag`,
`delete_tag`, `assign_tag`, `remove_tag_assignment`, `create_custom_field`,
`delete_custom_field`, `set_incident_custom_field`,
`create_event_orchestration`, `delete_event_orchestration`,
`create_webhook_subscription`, `update_webhook_subscription`,
`delete_webhook_subscription`, `ping_webhook_subscription`.

**20 tokens — real-time production actions, heavier than a standard
write:** these either push a live signal into the user's actual incident
response right now, or combine multiple entities in one call:
- `trigger_event`, `ack_or_resolve_event` (Events API v2 — creates/updates
  a real alert on the user's live PagerDuty account from an external
  source), `send_change_event` (Change Events API) — these are the
  connector's whole reason for existing for monitoring-integration use
  cases, heavier than a routine CRUD write.
- `merge_incidents` — touches two or more incidents at once, not one.
- `run_response_play`, `run_incident_workflow`,
  `invoke_automation_action_on_incident` — these *execute* a pre-configured
  automation sequence/action right now (multi-step, real production
  consequence), not just change one field on one record.

**40 tokens — heavy aggregated report across many objects in one call:**
- `audit_account` — the Tier-3 value-add account health audit: pulls
  incidents + services + escalation policies + schedules etc. into one
  aggregated report, same tier as WordPress Hub's `check_database_repair`.

**60 tokens — bulk/batch:**
- `bulk_incident_action` — the same incident action (ack/resolve/reassign/
  snooze) repeated across many incidents in one call — same tier as every
  other `bulk_*` on this platform.

**Files touched:** `tool-prices.json` (flat map, 92 entries, one per
manifest function), `imperal.json["pricing"]` (mirrored `tool_prices` +
`free_tools` + `notes`), this file.

**Next required step per policy §3:** run `developer.update_pricing` with
explicit `revenue_split_dev` once the app is deployed, then re-run
`deploy_app` to sync the mirrored copy into the platform's stored
manifest, then visually confirm in the panel (Developer → My Apps →
PagerDuty Connector → Pricing) before `submit_for_review`.
