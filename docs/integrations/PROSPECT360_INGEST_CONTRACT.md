# SEO Lead Factory → Prospect 360 — proposed ingest contract

**Status: PROPOSED. Nothing in this document is implemented, on either side.**

Phase 2 writes nothing to Prospect 360, reads nothing from it at runtime, and
holds no credential for it. This document exists so Phase 6 starts from an agreed
contract rather than a design session, and so the platform-side work can be
scheduled early — it is the longest-lead item in the roadmap.

## Why a new endpoint is needed

Phase 1 verified (evidence in `SEO_LEAD_FACTORY_DISCOVERY_REPORT.md` §4):

1. Every prospect-writing route sits behind cookie-JWT auth with host↔tenant
   binding (`backend/deps.py: enforce_host_binding`), which **fails closed on an
   unknown host**. A server on a new domain cannot authenticate.
2. `tenant_service_accounts` exists in the live database with **0 rows and no
   backend code referencing it**. The machine credential is designed and migrated
   (migration `069_invitations_and_service_accounts.sql`) but has no verifier.
3. `ProspectCreate` accepts **no UTM fields**, and 0 of 7 existing prospects carry
   `utm_source`. It also accepts `company_name`, `sector` and `city` and silently
   discards all three.
4. `POST /webhooks/n8n/{slug}` is an unauthenticated stub that logs and returns.
   It is not an integration point.

So there is no usable door today. Two pieces of **platform-side** work are
required, and neither can be delivered from `/opt/seolead`.

## Direction 1 — lead ingestion (SEO Lead Factory → Prospect 360)

```http
POST /api/v1/tenant-leads          # path is a proposal, not a requirement
Authorization: <service-account credential>
Idempotency-Key: <conversion_event_id, a UUID we generate>
Content-Type: application/json
```

```jsonc
{
  "tenant_id": "64edc9e3-0b91-442a-9d02-7964f2001a55",   // verified: Solar Belgium

  "identity": {
    "first_name": "...", "last_name": "...",
    "email": "...", "phone": "..."
  },

  "consent": {
    "email": true, "sms": false, "phone": true,
    "text_version": "solar-be-quote-v1",
    "captured_at": "2026-08-12T09:00:00Z",
    "ip_address": "...", "user_agent": "..."
  },

  "attribution": {
    "vertical": "SOLAR_BE",
    "brand": "...", "site": "...", "locale": "fr-BE",
    "landing_page": "/prix-panneaux-solaires",
    "content_id": "<uuid>",
    "keyword_cluster": "<uuid>",
    "search_intent": "COMMERCIAL",
    "channel": "organic",
    "campaign": "...",
    "utm_source": "google", "utm_medium": "organic",
    "utm_campaign": "...", "utm_content": "...", "utm_term": "...",
    "cta": "quote_request",
    "conversion_type": "form_submit"
  },

  "payload": { /* simulator inputs, qualification answers */ },

  "external_correlation_id": "<our correlation id, for cross-system tracing>"
}
```

**Response**

```jsonc
// 201 — created
{ "lead_id": "<uuid>", "tenant_id": "<uuid>", "dedup": false, "score": 42 }
// 200 — idempotent replay or matched an existing prospect
{ "lead_id": "<uuid>", "tenant_id": "<uuid>", "dedup": true, "score": 42 }
```

| Status | Meaning | Our behaviour |
|---|---|---|
| 201 / 200 | accepted | record `lead_reference.p360_lead_id` |
| 401 / 403 | credential rejected | stop, alert — do not retry blindly |
| 409 | idempotency conflict | treat as accepted, reconcile |
| 422 | payload rejected | do not retry; the lead needs a human |
| 5xx | platform fault | retry with backoff, then queue |

### Idempotency

`Idempotency-Key` is the `conversion_event` UUID we generate before the call, so a
retry after a timeout cannot create a second prospect. The key must be honoured
for at least 24 hours. Prospect 360 already has `webhook_replay_keys` and
`webhook_inbox` tables to build on.

### Mapping onto existing columns

| Contract field | `prospects` column | Note |
|---|---|---|
| `identity.*` | `first_name`, `last_name`, `email`, `phone` | exists |
| `attribution.utm_source` / `utm_medium` / `utm_campaign` / `utm_content` | same names | **exist, currently unwritable via the API** |
| `attribution.utm_term` | — | **does not exist**; needs a migration or `extra` jsonb |
| `attribution.channel` | `source` | constant `seo_lead_factory` |
| `attribution.site` / `locale` / `content_id` | `source_detail` | composite string, or `extra` |
| the rest of `attribution` | `extra` (jsonb) | until columns exist |
| `research_job_id`, `seo_opportunity_id`, `research_package_id`, `serp_snapshot_id` | `extra` (jsonb) | Phase 3 additions — see below |
| `consent.*` | `consent_records` | must flow through the platform's consent path, not set as bare booleans |
| `payload` | `extra` | |

`extra` is an escape hatch, not a design. Attribution that matters for reporting
should become columns before Phase 7 tries to learn from it.

## Direction 2 — outcome callbacks (Prospect 360 → SEO Lead Factory)

**This is the half that closes the revenue loop, and nothing like it exists.**

```http
POST https://<seolead-host>/hooks/p360/lead-outcome
X-Signature: HMAC-SHA256(raw_body, shared_secret)
X-Idempotency-Key: <event id>
```

```jsonc
{
  "lead_id": "<uuid>",
  "status": "QUALIFIED",
  "stage": "...",
  "amount_cents": 1250000,
  "currency": "EUR",
  "occurred_at": "2026-09-01T10:00:00Z"
}
```

Statuses to cover the full funnel: `QUALIFIED`, `DISQUALIFIED`, `APPOINTMENT_SET`,
`APPOINTMENT_HELD`, `NO_SHOW`, `QUOTE_SENT`, `WON`, `LOST`.

`event_outbox` already exists in the platform database and is the natural
foundation.

## Direction 3 — read-only enrichment (optional)

`GET /api/v1/copilot/prospects/{id}/360` is verified to exist and returns the full
read model. Useful for closed-loop analysis in Phase 7. It is an authenticated
surface; whether a service account may call it is part of the same permission
question as direction 1.

## What SEO Lead Factory stores

`lead_reference` holds `p360_tenant_id`, `p360_lead_id` and the acquisition
context. **It holds no personal data** — no name, no email, no phone.

This is a security control, not a modelling preference. The public-facing system
then has no PII database to breach, RGPD erasure has exactly one owner, and the
factory stays out of scope for most of the consent machinery. Attribution needs
the lead's *id* and its acquisition context, not the lead's identity.

## Phase 3 additions to attribution

Phase 3 produces four identifiers that were not available when this contract was
first written, and each answers a question the closed loop needs:

| Field | Answers |
|---|---|
| `research_job_id` | which research run produced the page this lead came from |
| `seo_opportunity_id` | what the opportunity score predicted, so Phase 7 can compare prediction against revenue |
| `research_package_id` | which evidence set the content was written from |
| `serp_snapshot_id` | what the SERP looked like when the decision was made |

The second is the one that matters strategically. Without it, the opportunity
score can never be calibrated — there is no way to ask "did the keywords we scored
highly actually produce profitable customers", which is the question Phase 7
exists to answer.

All four fit in `extra` today. They should become columns before Phase 7 tries to
learn from them.

## Non-negotiables

- **No direct writes to `acquisition_platform`.** Prospect 360 enforces tenant
  isolation, consent SSOT, scoring-on-write and RGPD purge scheduling in
  application code. A direct INSERT bypasses all four and silently creates
  unscored, unconsented, never-purged rows. Verified: `seolead_app` holds zero
  privileges on every table in that database (`scripts/verify_db_privileges.sh`).
- **No use of the n8n webhook stub** as production ingestion.
- **No cookie-JWT reuse.** Borrowing a human's session for a machine defeats the
  host-binding control that Phase 1 found was added deliberately.

## Fallback if service accounts cannot be built in time

A signature-authenticated webhook following the existing HubSpot pattern
(`webhooks_hubspot.py`, signature-authed, not RBAC). Strictly worse — it bypasses
the RBAC permission matrix that migration 069 designed — but it is an
already-implemented pattern on the platform and would unblock Phase 6 without new
auth infrastructure. Treat it as a documented compromise with an owner decision,
not a default.

## Owner decision required before Phase 6

The platform-side work (service-account authentication + an ingest endpoint +
outbound callbacks) must be scheduled with whoever owns the TechFormaNord
repository. It cannot be delivered by this project.
