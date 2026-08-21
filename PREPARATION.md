# PagerDuty Connector — Preparation

**Статус:** Фаза 1-2 (Discovery + архитектурные решения) завершены. Влад
заявил объём разработки прямым поручением 2026-08-21 — «делай это
приложение в максимальной комплектации с максимальным функционалом» —
что закрывает Шаг 5 `CONNECTOR_DISCOVERY_STANDARD.md` (объём = Ярус 1+2+3,
без дополнительного запроса подтверждения).

**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-21, v0.1
**Vikunja task:** #2221 (BBW Imperal Apps), `[App Development] PagerDuty Connector`.

**Почему сейчас:** PagerDuty — рыночный лидер incident management /
on-call алертинга. Портфель Imperal уже покрывает iPaaS/automation
(MuleSoft, n8n, Make, Power Automate, Workato) и RPA (UiPath, Automation
Anywhere, Blue Prism), но не имеет вообще ни одного коннектора к
вертикали «инциденты и дежурства» — PagerDuty закрывает эту нишу первым.

---

## 1. Паспорт приложения

**Название в Marketplace (display_name): «PagerDuty»**. Внутренний
app_id/папка: `pagerduty-connector`.

**PagerDuty Connector** — коннектор к PagerDuty REST API v2 (конфигурация:
incidents, services, escalation policies, schedules, on-calls, users,
teams, business services, custom fields, tags, event orchestrations,
incident workflows, automation actions, webhooks, audit trail, analytics)
плюс Events API v2 и Change Events API (отправка алертов/деплоев в
PagerDuty из внешних систем). BYOK: пользователь подключает свой
собственный PagerDuty-аккаунт через собственный REST API key. Imperal
ничего не хостит и не проксирует помимо самого запроса.

---

## 2. Ключевые факты о PagerDuty API (см. `CONNECTOR_DISCOVERY.md`)

### 2.1 Четыре разные API-поверхности — не одна

REST API v2 (`api.pagerduty.com`), Events API v2
(`events.pagerduty.com/v2/enqueue`), Change Events API
(`events.pagerduty.com/v2/change/enqueue`), Webhooks v3
(`webhook_subscriptions` внутри REST API). Каждая со своей авторизацией
— REST API key для первой и четвёртой, `routing_key`/`integration_key`
per-service для второй и третьей. Смешивать их в одну учётную запись
нельзя — коннектор моделирует это явно (см. §3 ниже).

### 2.2 Нет открытой OpenAPI-схемы

В отличие от MuleSoft/Workato, у PagerDuty нет публичного
`/openapi.json` на `developer.pagerduty.com` (сайт построен на
Postman-подобном reference UI). Полная карта ресурсов (~40+ REST-доменов)
составлена вручную по официальным SDK (`go-pagerduty`, `pdpyras`) и
support-документации по каждому продуктовому модулю — зафиксировано в
`CONNECTOR_DISCOVERY.md` §1-2.

### 2.3 Incident Workflows / Automation Actions — тарифное ограничение PagerDuty, не коннектора

Эти два домена (Ярус 3) требуют Business/Enterprise-тарифа PagerDuty на
стороне пользователя. Коннектор реализует полный CRUD-набор функций для
них; если конкретный аккаунт не имеет доступа, PagerDuty сам вернёт
403/недоступность — это поведение внешнего сервиса, не баг коннектора.
Формулировка в описании функций должна честно предупреждать об этом.

---

## 3. Архитектурное решение — BYOK, ДВА типа credentials, не один

**WHY BYOK**, как и все connector-приложения портфеля
(Shopify/HubSpot/Salesforce/MuleSoft/Stripe и т.д.): PagerDuty-аккаунт —
собственность пользователя, Imperal не может и не должна централизованно
брокерить доступ к чужому инцидент-менеджменту.

**WHY ДВА РАЗНЫХ ТИПА CREDENTIALS, А НЕ ОДИН GENERIC API KEY.**

В отличие от Stripe (один Bearer secret key на всё) или Shopify (один
Admin API token), PagerDuty архитектурно требует:

1. **REST API key** (обязательный, вводится при `connect_pagerduty`) —
   20-символьная строка из Integrations → Developer Tools → API Access
   Keys, заголовок `Authorization: Token token=xxx`. Покрывает весь
   конфигурационный функционал (Ярус 1+2+3 кроме отправки событий).
2. **Routing/Integration keys** (опциональные, per-service) — НЕ
   вводятся при подключении аккаунта. Получаются программно через
   `create_service_integration` (создаёт Service Integration и
   возвращает его `integration_key`), затем используются в
   `send_event`/`send_change_event`. Хранить их нужно per-service, не
   как один общий секрет.

Это отражено в `schemas.py` явно: `ConnectPagerdutyParams` просит только
REST API key (+ опциональный label), а `SendEventParams`/
`SendChangeEventParams` явно требуют `routing_key`/`integration_key` как
отдельный параметр вызова — не путается с основным подключением.

**WHY A PLAIN TOKEN HEADER, NOT OAUTH2** (как Stripe, не как MuleSoft).
PagerDuty поддерживает scoped OAuth2 для многопользовательских
интеграций (marketplace apps), но для одного пользователя, управляющего
СВОИМ аккаунтом, простой REST API key — официально поддерживаемый и
более простой путь (`support.pagerduty.com/main/docs/api-access-keys`,
подтверждено 2026-08-21). `connect_pagerduty` поэтому просто проверяет
вставленный ключ вызовом `GET /users/me` (или `GET /abilities`) и
сохраняет его.

**WHY EVENTS API v2 IS A SEPARATE FUNCTION FAMILY, NOT MERGED INTO
INCIDENTS.** Отправка события (`send_event`) физически идёт на другой
хост (`events.pagerduty.com`) с другой авторизацией — реализована в
отдельном методе клиента, не переиспользует `_request()` REST-хелпера.

---

## 4. Объём релиза — Ярус 1+2+3 (максимум, по прямому поручению)

См. `CONNECTOR_DISCOVERY.md` §3 для полного постатейного списка.
Итого ориентировочно ~85-95 функций, разбитых по доменам:
connection, incidents, services + service integrations, escalation
policies, schedules + overrides, on-calls, users, teams, maintenance
windows, business services, priorities, incident types/custom fields,
tags, extensions/add-ons, rulesets (legacy), event orchestrations,
webhooks v3, events API (send), change events API (send), audit trail,
log entries, notifications, vendors, incident workflows, automation
actions, analytics, status dashboards + bulk operations и environment
audit (Ярус 3 value-add, по аналогии с MuleSoft's `audit_cloudhub_environment`).

---

## 5. Что НЕ делаем (явные границы, см. `CONNECTOR_DISCOVERY.md` §5)

- Не строим отдельный white-label/embedded API — у PagerDuty такой
  поверхности нет.
- Status Dashboards и Vendors — read-only справочники, без CRUD (у
  PagerDuty либо нет публичного write-эндпоинта, либо это специально не
  предоставляется через API).

---

## 6. UI (Фаза 3, см. `UI_INTERFACE_STANDARD.md`)

- Единая кнопка "App settings" в левом сайдбаре (последний элемент).
- Форма подключения (`connect_pagerduty`) — растянута на всю ширину
  сайдбара, поля с лейблами и контекстными placeholder'ами (REST API
  key, опциональный label) — без карточной обёртки, `ui.Stack` +
  `ui.Divider` между секциями.
- Инструкция по кнопке/форме — только в модалке-подсказке, не
  дублируется в сайдбаре.
