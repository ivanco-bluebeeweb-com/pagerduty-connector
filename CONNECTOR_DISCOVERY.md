# PagerDuty Connector — Connector Discovery

**Дата discovery:** 2026-08-21
**Статус:** Ярусы 1-3 пройдены (свежее чтение официальной документации developer.pagerduty.com / support.pagerduty.com / официальных SDK, 2026-08-21). Влад заранее заявил объём — «максимальная комплектация, максимальный функционал» (см. Vikunja #2221) — поэтому по `CONNECTOR_DISCOVERY_STANDARD.md` Шаг 5 (запрос подтверждения объёма) считается закрытым этим прямым поручением: делаем Ярус 1+2+3.

---

## 1. Целевой сервис и источники

PagerDuty — рыночный лидер incident management / on-call алертинга. В отличие от «одного REST-API» коннекторов (Shopify, HubSpot), у PagerDuty **минимум 4 разные API-поверхности** с разной аутентификацией, которые категорически нельзя смешивать в одну учётку:

| Поверхность | Базовый URL | Назначение | Аутентификация |
|---|---|---|---|
| **REST API v2** | `api.pagerduty.com` | Управление конфигурацией: incidents, services, escalation policies, schedules, users, teams и т.д. | REST API key (`Authorization: Token token=xxx`, 20-символьная строка) ИЛИ scoped OAuth2 |
| **Events API v2** | `events.pagerduty.com/v2/enqueue` | Приём алертов из внешних систем в PagerDuty (trigger/acknowledge/resolve) | `routing_key` (Integration Key), привязанный к конкретному Service Integration — НЕ REST API key |
| **Change Events API** | `events.pagerduty.com/v2/change/enqueue` | Трекинг деплоев/изменений вне инцидентного потока | Свой `integration_key`, отдельно от Events API v2 |
| **Webhooks v3** (`webhook_subscriptions`) | часть REST API | Исходящие уведомления от PagerDuty в наш endpoint при событиях | Управляется через REST API key, верифицируется через подпись вебхука |

Источники (прочитаны 2026-08-21): `developer.pagerduty.com/api-reference/`, `developer.pagerduty.com/docs/events-api-v2/trigger-events/`, `support.pagerduty.com/main/docs/api-access-keys`, `support.pagerduty.com/main/docs/webhooks`, `support.pagerduty.com/main/docs/event-orchestration`, `support.pagerduty.com/main/docs/incident-workflows`, `support.pagerduty.com/main/docs/automation-actions`, `support.pagerduty.com/main/docs/rulesets`, `support.pagerduty.com/main/docs/business-services`, `support.pagerduty.com/main/docs/custom-fields-on-incidents`, `support.pagerduty.com/main/docs/audit-trail-reporting`, `github.com/PagerDuty/go-pagerduty` (официальный Go SDK — источник полного списка REST-ресурсов), `github.com/PagerDuty/pdpyras` (официальный Python SDK).

**Важный вывод Discovery:** официального единого `/openapi.json` в открытом доступе на `developer.pagerduty.com` нет (сайт построен на Postman-подобном UI без прямой ссылки на схему). Карта ресурсов ниже составлена вручную по официальным SDK (go-pagerduty покрывает ~40+ REST-ресурсов) и support-документации по продуктовым модулям.

---

## 2. Карта возможностей (направление на каждую)

| Домен | Возможность | Ingress/Egress/Both | Комментарий |
|---|---|---|---|
| **Incidents** | list/get/create/update (ack, resolve, reassign, escalate, priority, merge) incidents | Both | Ядро сервиса |
| **Incidents** | incident notes, incident responders (request), incident status updates | Both | |
| **Incidents** | incident alerts (list/get/manage under an incident) | Both | Alert — единица события внутри incident |
| **Incidents** | incident related incidents (similarity), incident custom field values | Ingress/Both | |
| **Services** | list/get/create/update/delete services + service integrations (создание routing/integration key) | Both | Integration key нужен для Events API — критично для «полного функционала» |
| **Escalation Policies** | list/get/create/update/delete escalation policies + rules | Both | |
| **Schedules** | list/get/create/update/delete schedules, overrides, on-call previews | Both | |
| **On-Calls** | list who is on-call right now/at a time | Ingress | Read-only отчётный ресурс |
| **Users** | list/get/create/update/delete users, contact methods, notification rules | Both | |
| **Teams** | list/get/create/update/delete teams, team members | Both | |
| **Maintenance Windows** | list/get/create/update/delete (подавление алертов на плановые работы) | Both | |
| **Business Services** | list/get/create/update/delete business services + service dependencies (Service Graph) | Both | Карта влияния инцидента на бизнес-функции |
| **Priorities** | list account priority levels (P1-P5) | Ingress | Read-only справочник |
| **Incident Types / Custom Fields on Incidents** | list incident types; list/get/create/update/delete custom field definitions + field options | Both | |
| **Tags** | list/create/delete tags; assign/remove tags on entities | Both | |
| **Extensions / Add-ons** | list/get/create/update/delete (сторонние интеграции, встроенные ссылки) | Both | Легаси-механизм, но всё ещё в REST API |
| **Rulesets** (legacy Event Rules) | list/get/create/update/delete rulesets + rules | Both | Предшественник Event Orchestration — оставлен для обратной совместимости у старых аккаунтов |
| **Event Orchestrations** | list/get/create/update Global/Service Orchestrations + routing rules, catch-all rule, orchestration integrations (keys) | Both | Современный маршрутизатор алертов, до 10 integration keys на orchestration |
| **Incident Workflows** | list/get/create/update/delete workflows, triggers, actions; run workflow manually via API; list workflow executions | Both | Требует Business/Enterprise-тарифа (ограничение на стороне PagerDuty, не коннектора) |
| **Automation Actions** | list/get/create/update/delete automation actions (runbook actions), invocations | Both | Часть Incident Workflows / Event Orchestration экосистемы |
| **Webhooks v3** | list/get/create/update/delete webhook subscriptions | Both | Исходящие вебхуки PagerDuty → наш endpoint |
| **Events API v2** | send trigger/acknowledge/resolve alert event | Egress | Отдельная авторизация через `routing_key`, не REST API key |
| **Change Events API** | send a change event (деплой/изменение) | Egress | Отдельная авторизация через `integration_key` |
| **Audit Trail** | list audit records (кто что изменил и когда) | Ingress | Комплаенс/безопасность |
| **Analytics** | raw incident analytics, aggregated analytics (MTTA/MTTR и т.п.) | Ingress | Отчётность |
| **Status Dashboards** | list/get status dashboards (публичные/внутренние статус-страницы) | Ingress | Ниже приоритета — нишевая фича |
| **Log Entries** | list log entries (журнал событий по incident/по аккаунту) | Ingress | Полезно для аудита/дебага |
| **Notifications** | list notifications sent to a user | Ingress | |
| **Vendors** | list vendors (типы мониторинговых интеграций, справочник) | Ingress | Read-only справочник для UI подсказок при создании service integration |

---

## 3. Ярусы (объём релиза)

### Ярус 1 — критический костяк (must-have, ядро value proposition)
connect_pagerduty (REST API key), disconnect_pagerduty, list_connections; incidents (list/get/create/update/acknowledge/resolve/reassign/escalate/add note/list notes/list alerts); services (list/get/create/update/delete/list integrations/create integration — источник routing_key); escalation policies (list/get/create/update/delete); schedules (list/get/create/update/delete/list overrides/create override); on-calls (list); users (list/get/create/update/delete); teams (list/get/create/update/delete); send_event (Events API v2: trigger/acknowledge/resolve); maintenance windows (list/get/create/delete).

### Ярус 2 — расширенная полнота (то, что делает коннектор «максимальным»)
business services (CRUD + dependencies); priorities (list); incident types и custom fields (CRUD); tags (CRUD + assign); rulesets (list/get) — легаси, но за совместимость; event orchestrations (list/get/create/update routing rules + integration keys); webhooks v3 (CRUD); change events (send); audit trail (list); log entries (list); notifications (list); vendors (list) — справочник для UI.

### Ярус 3 — продвинутая автоматизация (полный максимум)
incident workflows (list/get/create/update/delete/run manually/list executions); automation actions (list/get/create/update/delete/invoke); analytics (raw + aggregated incident analytics); status dashboards (list/get).

**Итого:** ~85-95 функций — сопоставимо по масштабу с самым крупным коннектором в портфеле (Shopify ~90, WordPress Hub ~264 с учётом WooCommerce). Оправдано природой сервиса: PagerDuty — это конфигурационная платформа (services × escalation × schedules × orchestration), а не просто CRUD над одной сущностью.

---

## 4. Архитектурное решение по аутентификации

**BYOK, как и все connector-приложения портфеля (Shopify/HubSpot/Salesforce/MuleSoft и т.д.):** пользователь подключает СВОЙ PagerDuty-аккаунт.

Коннектор моделирует **два независимых типа credentials**, а не один:
1. **REST API key** (обязательный, основной) — 20-символьная строка из Integrations → Developer Tools → API Access Keys. Покрывает весь Ярус 1+2+3 конфигурационный функционал.
2. **Routing/Integration keys** (опциональные, per-service) — не вводятся при коннекте аккаунта, а получаются программно через `create_service_integration` (Ярус 1) и используются в `send_event`/`send_change_event`. Это отличает PagerDuty от типичного «один токен на всё» коннектора — критично отразить в `connect_pagerduty` и в схемах `send_event`.

Это ключевое архитектурное отличие зафиксировано в §3 задачи Vikunja #2221 п.1 и должно быть отражено в `app.py`/`schemas.py` явно (два разных описания полей, а не одно generic `api_key`).

---

## 5. Что НЕ делаем (явные границы)

- Не строим white-label/embedded API (у PagerDuty такой поверхности вообще нет, в отличие от Tray/Pipedream — не применимо).
- Status Dashboards — только list/get (read), т.к. это нишевая, редко используемая витрина; создание статус-страниц не покрываем в v1 максимума, если не найдётся отдельного явного write-эндпоинта в REST API (уточняется на этапе реализации).
- Vendors — только read-only справочник, не CRUD (PagerDuty сам не даёт создавать vendor-типы через публичный API).
