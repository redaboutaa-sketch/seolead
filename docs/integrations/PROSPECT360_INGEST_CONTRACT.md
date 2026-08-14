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

---

# Phase 4 addendum — the boundary as implemented

**Nothing above changed. The contract is still PROPOSED and still unimplemented.**
This section records what Phase 4 actually built on this side of the boundary, so
whoever implements the adapter knows exactly what will call them.

## What exists now

`app/site/lead_capture.py` defines a `LeadDestination` port and exactly one
implementation:

```python
class LocalLeadDestination:
    code = "local"
    async def deliver(self, lead: CapturedLead) -> LeadState:
        return LeadState.PENDING_EXPORT      # stores, and stops
```

It returns `PENDING_EXPORT`, not `EXPORTED`, because that is the truth: the lead is
captured and nothing downstream has seen it. A destination that reported success
while nothing received the lead would be the worst failure mode in this file — the
lead would be marked handled and never followed up.

Enforced by tests in `tests/test_lead_capture.py::TestProspect360Boundary`:

- the default destination writes nowhere and never returns `EXPORTED`,
- no symbol containing "prospect" exists in the module,
- the module source contains no `acquisition_platform`, no `prospect360`, no
  `postgresql://`, no `INSERT INTO`.

Verified at runtime during the Phase 4 staging E2E: the `seolead_app` role connects
to database `seolead` and sees **zero** Prospect 360 tables.

## What the adapter will receive

The Phase 4 schema, which is a superset of the `attribution` block proposed above:

```
CapturedLead      id, created_at, conversion_type, language, postcode,
                  first_name, last_name, email, phone, qualification{},
                  consent_marketing, consent_version, consent_timestamp,
                  consent_source, state, export_destination, export_attempts

LeadAttribution   vertical_code, site_id, published_content_id,
                  landing_path, page_path, search_intent, keyword_cluster,
                  channel, source, referrer,
                  utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                  cta, conversion_type, session_id, correlation_id
```

Note for the platform side: `ProspectCreate` still accepts no UTM fields (finding 3
above). Every one of those columns exists here and would be discarded on arrival.

## State machine this side implements

```
NEW ──► PENDING_EXPORT ──► EXPORTING ──► EXPORTED
                              │
                              └────────► EXPORT_FAILED ──► PENDING_EXPORT
```

`EXPORTING` exists so a retry cannot double-export. The adapter must be idempotent
on `lead.id` regardless.

## Additional owner decisions surfaced by Phase 4

1. Deduplication: is a known email an update or a new prospect?
2. Does marketing consent map to an existing Prospect 360 field? It travels with
   the lead, and a destination that markets to someone who declined would make
   this system the cause of that.
3. How long a lead stays in this database after a successful export.


---

# Phase 5A addendum — measured against the deployed platform

**Status: still NOT IMPLEMENTED.** Phase 5A stopped at the platform gate (§50).
What follows replaces inference with facts read from the deployed revision
`79666ba912cb` and the live `acquisition_platform` database on 2026-08-13.

Everything above this line was written from Phase 1 discovery. Where the two
disagree, this section is newer.

## Deployment, verified

```
repository   github.com/redaboutaa-sketch/techformanord   (private)
revision     79666ba912cb9a92ac342654036c1729c552e952     (= default branch tip)
image        ghcr.io/redaboutaa-sketch/techformanord/api@sha256:e2b695c2a40b…
database     acquisition_platform @ platform_postgres
tenant       64edc9e3-0b91-442a-9d02-7964f2001a55 | solar-belgium | Solar Belgium
```

`/opt/techformanord` is **not** the deployed source — it is a stale checkout on
`claude/beaver-ui-redesign` with uncommitted changes. Use the GHCR image revision.

## What changed since Phase 1

**`tenant_service_accounts` is now implemented**, not just migrated. Create,
rotate and revoke exist in `services/tenant_membership_service.py`, exposed via
`routes/tenant_admin.py` behind `tenant.service_accounts.manage`. The schema is
tenant-scoped, hashes the secret, versions the credential, and arms a kill switch
by default. **Reuse it.**

The gap is narrower than Phase 1 implied: accounts can be minted but **nothing
verifies a credential on an inbound request**. A verifier must be built.

**`prospects` already carries** `utm_source`, `utm_medium`, `utm_campaign`,
`utm_content`, `source`, `source_detail`. It does **not** carry `utm_term`,
`landing_page`, `content_id`, `locale`, `search_intent`, `keyword_cluster`, `cta`,
`conversion_type`, or any external correlation identifier.

**Consent is an SSOT**, not two booleans. `consent_records.type` ∈
`{data_processing, email_marketing, sms_marketing, phone_marketing, cookies,
profiling}` with `status`, `text_version`, `purpose`, `proof`, `evidence`,
`granted_at`, `revoked_at`, `actor_type`, `actor_id`.

Mapping: `consent_processing → data_processing` is clean. `consent_marketing` is
**channel-unspecified on our side** and Prospect 360 requires a channel — an
unresolved decision, not a mapping.

## Constraints any implementation must respect

Read from that repository's `CLAUDE.md`, and non-negotiable there:

- No ORM and no Alembic. `asyncpg` with hand-written SQL; migrations are numbered
  `database/migrations/NNN_*.sql` files, additive and idempotent, inventoried in
  `MANIFEST.tsv`, each ending in a `DO $$ … RAISE EXCEPTION` block that refuses to
  declare success without proof.
- Every read and write inside `tenant_transaction(tenant_id, pool=pool)`. Tenant
  from verified identity only. Another tenant's object → **404**, never 403.
- **No external effect from an HTTP request.** Outbound work is written to
  `event_outbox` in the same transaction as the business write.
- A new external capability is disabled by default. "Un drapeau neuf vaut `False`.
  Toujours."

## Blocking finding

There is **no canonical prospect-creation service**. The logic is inline in
`routes/prospects.py::create_prospect`, and two other `INSERT INTO prospects` sites
exist (`prospect_import_runner.py`, `calendly_webhook_service.py`). A thin ingest
route cannot call a service that does not exist, and duplicating the INSERT is
forbidden. Extracting one is the correct fix and is an owner decision, because it
refactors a live production write path.

## Still required before implementation

1. Approval to extract a prospect-creation domain service.
2. The marketing-consent channel decision.
3. Attribution model: dedicated table (recommended) vs widening `prospects`.
4. Whether the audit/event vocabulary may be extended without a separate
   architecture amendment.


---

# Phase 5A-P2 — the authentication design, fully resolved

**Status: designed and verified against the deployed code; NOT implemented.**
Everything below was read from revision `9931c5f` / branch `phase-5a-lead-ingest`
at `142146d`. There are no remaining unknowns and no architecture gate — what is
left is writing it.

## SERVICE_ACCOUNT_WIRE_FORMAT

Reuses the existing issuance in `services/tenant_membership_service.py`; no second
credential system.

```
public_identifier   "sa_" + secrets.token_hex(8)     → 19 chars, circulates, logged
secret              secrets.token_urlsafe(32)        → 256 bits, crosses once
credential_hash     hashlib.sha256(secret).hexdigest()
```

Proposed presentation:

```
Authorization: Bearer <public_identifier>.<secret>
```

One header, split on the first `.`. The left half is the lookup key, the right
half is verified. Malformed input (no dot, wrong prefix, wrong length) is rejected
before any database work.

## PRE_TENANT_LOOKUP_PATH — the bootstrap problem, already solved

The platform already answers this and it must not be reinvented:
`services/platform_context.find_owning_tenant(sql, *args, purpose=...)`.

It asks each **active** tenant in turn, inside that tenant's own context, and:

- needs no privilege — `platform_app` stays NOSUPERUSER / NOBYPASSRLS;
- never weakens `FORCE ROW LEVEL SECURITY`;
- each probe sees exactly one tenant's rows;
- **refuses ambiguity** — two matches return `(None, None)` rather than picking.

So the credential is resolved by probing for `public_identifier`, and the tenant
falls out of the row that matched. `tenant_id` is never read from the body, the
Host header or a query parameter.

`RLS_BOOTSTRAP_MODEL`: discovery is not access. Cost is N scoped queries per
authentication, N = active tenants.

## SECRET_VERIFICATION_PRIMITIVE

`_empreinte()` — SHA-256 hex — compared to the stored `credential_hash`.

SHA-256 rather than a slow KDF is correct **here**: the secret is a 256-bit random
token, not a human password, so there is nothing to brute-force. The comparison
must still use `hmac.compare_digest`.

The verifier must reject: missing, malformed, unknown identifier, wrong secret,
`credential_version` mismatch (rotated), `status` revoked/disabled, and
`kill_switch_engaged = TRUE` — which is the default on creation, so a new account
is inert until someone deliberately disarms it.

## CAPABILITY — `prospects.ingest`

The platform has a real RBAC catalogue; no parallel system is needed:

```
rbac_permissions(code, category, description, enforced, humans_only, created_at)
rbac_role_permissions(role_code, permission_code)
tenant_service_account_permissions(tenant_id, service_account_id, role_code,
                                   permission_code, granted_by, granted_at)
```

Naming follows the existing convention, which is **plural**: `prospects.delete`,
`campaigns.activate`, `reports.export`. So the capability is **`prospects.ingest`**,
not `prospect.ingest`.

Registered with `humans_only = FALSE` (machine-assignable) and `enforced = TRUE`.
It must **not** appear in migration 069's forbidden-for-machine list — that block
already raises if a machine role holds `prospects.delete`, `consents.override`,
`tenant.service_accounts.manage` and the rest, and it is the existing guarantee
that an ingest account cannot quietly acquire dangerous rights.

## TRANSACTION BOUNDARY

The extraction already made this possible: `creer_prospect` takes a connection and
opens no transaction of its own.

```
BEGIN tenant_transaction(tenant_id)          ← tenant from the verified credential
    creer_prospect(conn, …, provenance="service_account",
                   actor=<public_identifier>, correlation_id=<external id>)
      └─ INSERT prospects
      └─ domain_events.emit("prospect.created")   (already catalogued)
      └─ score_and_persist_prospect
    INSERT consent_records (type='data_processing')
    INSERT lead_acquisition_attributions (… payload_fingerprint)
COMMIT
──────────────────────────────────────────────
AFTER COMMIT: trigger_qualification            ← never inside the transaction
```

One boundary. A prospect cannot commit without its attribution, and an attribution
cannot commit without its prospect.

## IDEMPOTENCY

Identity: `(tenant_id, source_system, external_correlation_id)`, enforced by
`uq_lead_acq_attr_identite` — the constraint is the source of truth, a fast-path
SELECT is only an optimisation.

Concurrency: both racers may observe "absent". One commits; the loser takes the
unique violation, **rolls back entirely including the prospect it attempted**, then
re-reads the committed row in a fresh transaction. Same fingerprint → replay;
different → 409. The loser must not leak its rolled-back prospect id and must not
trigger qualification.

## FINGERPRINT v1

Over the **validated semantic request**, never raw bytes:

- included: `fingerprint_version`, `source_system`, `external_correlation_id`,
  all persisted contact fields, all persisted project fields, processing-consent
  fields (granted / version / timestamp / source), all persisted attribution
  fields;
- excluded: the credential and Authorization header, `tenant_id` (already part of
  the unique identity), server-generated ids and `created_at`, retry timestamps,
  tracing ids, any non-persisted transport metadata.

Canonicalisation: `json.dumps(..., sort_keys=True, separators=(",", ":"),
ensure_ascii=False)` over the validated model with explicit `None` for absent
optionals, then SHA-256, stored lowercase hex — the format migration 091's CHECK
already enforces.

## AUDIT — no new vocabulary

- success → `prospect.created`, already in `domain_events.CATALOGUE`, carrying
  provenance, actor and correlation id;
- authentication failure → `PLATFORM_AUTH_FAILURE` via `platform_audit.record`;
- cross-tenant probe → `CROSS_TENANT_ACCESS_DENIED`.

## What remains

Verifier, capability migration (092), DTO, fingerprint module, ingest application
service, the thin route, and the security matrix.
