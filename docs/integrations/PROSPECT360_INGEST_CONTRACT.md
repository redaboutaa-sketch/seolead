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

**Response** — ~~SUPERSEDED by DEC-P5A-TRANSPORT-02, §Phase 5A-P7~~

```jsonc
// ~~201 — created~~
{ "lead_id": "<uuid>", "tenant_id": "<uuid>", "dedup": false, "score": 42 }
// ~~200 — idempotent replay or matched an existing prospect~~
{ "lead_id": "<uuid>", "tenant_id": "<uuid>", "dedup": true, "score": 42 }
```

> **Kept, struck out, not deleted.** Anyone who built against this shape needs to
> see that it changed and why, not find it quietly absent. Four things went:
> `lead_id` became `prospect_id` (the platform calls it a prospect); `tenant_id`
> left because the producer already holds it in its own configuration and echoing
> it publishes tenant internals for no gain; `dedup` became the explicit
> three-valued `outcome`, since a boolean cannot express the difference between a
> replay and a refused conflict; and `score` left because it is a server-side
> qualification value that changes after ingest — returning it here would invite
> the producer to store it as though it were stable. The canonical shape is in
> §Phase 5A-P7.

| Status | Meaning | Our behaviour |
|---|---|---|
| 201 / 200 | accepted | record `lead_reference.p360_lead_id` |
| 401 / 403 | credential rejected | stop, alert — do not retry blindly |
| ~~409~~ | ~~idempotency conflict~~ | ~~treat as accepted, reconcile~~ **WRONG — corrected by DEC-P5A-INGEST-01, §Phase 5A-P6** |
| 422 | payload rejected | do not retry; the lead needs a human |
| 5xx | platform fault | retry with backoff, then queue |

> **The 409 row above is struck out deliberately rather than edited away.** It was
> written in Phase 1 and is the exact error migration 094 exists to prevent:
> *« un envoi DIFFÉRENT réutilisant la même clé … sans l'empreinte, le second cas
> passerait pour un rejeu et la modification serait perdue en silence »*. Treating
> a 409 as accepted moves that silent loss from the platform to the producer
> instead of removing it. The normative matrix is in §Phase 5A-P6.

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
optionals, then SHA-256, stored lowercase hex — the format migration 094's CHECK
already enforces.

## AUDIT — no new vocabulary

- success → `prospect.created`, already in `domain_events.CATALOGUE`, carrying
  provenance, actor and correlation id;
- authentication failure → `PLATFORM_AUTH_FAILURE` via `platform_audit.record`;
- cross-tenant probe → `CROSS_TENANT_ACCESS_DENIED`.

## What remains

Verifier, capability migration (095), DTO, fingerprint module, ingest application
service, the thin route, and the security matrix.


---

# Phase 5A-P3 — Machine Ingest DTO v1 and Fingerprint v1

**Status: implemented on `phase-5a-lead-ingest`, not merged, not deployed, not
reachable.** There is no route and no database orchestration yet. This section is
normative: it defines the wire contract and the fingerprint rule that the ingest
application service and the HTTP route must both honour.

Implementation: `backend/services/lead_ingest_dto.py` and
`backend/services/lead_ingest_fingerprint.py` in the platform repository.

## Request shape

> **Superseded by §Phase 5A-P5.** The block below is what the code declares
> **today**. `job_title` has since moved to `contact` and `project` has become
> exclusively Solar qualification (DEC-P5A-QUAL-07). The normative target shape
> is in Phase 5A-P5; this one is kept because it is what a reader of the current
> module will actually find.

```jsonc
{
  "external_correlation_id": "conv-…",   // required, 1–128
  "source_system":           "seo_lead_factory",  // required, 1–64

  "contact":     { "first_name", "last_name", "email", "phone" },
  "project":     { "job_title" },        // ← moves to contact, see P5
  "consent":     { "processing", "version", "timestamp", "source" },  // required
  "attribution": { "source", "source_detail", "landing_page", "content_id",
                   "locale", "search_intent", "keyword_cluster",
                   "utm_source", "utm_medium", "utm_campaign",
                   "utm_content", "utm_term", "cta", "conversion_type" }
}
```

`contact`, `project` and `attribution` may be omitted entirely; `consent` may not.

Models: `LeadIngestRequest`, `ContactIngest`, `ProjectIngest`, `ConsentIngest`,
`AttributionIngest`.

## Forbidden input

`extra: "forbid"` on **every** model. Unknown fields are a 422, never a silent
drop — a producer that misspells a field must learn it from a refusal, not from a
report three weeks later.

Specifically rejected rather than ignored: `tenant_id`, `service_account_id`,
`prospect_id`, `destination_tenant`, `role`, `permission`, `permissions`,
`score`, `status`, `created_at`, `ip_address`, `user_agent`, `session_id`,
`request_id`, `trace_id`, `host`, `retry_count`, and every channel-marketing
consent field.

**The tenant is never an input.** It falls out of the presented secret via
`service_account_auth.authentifier` → `platform_context.find_owning_tenant`. No
model in the module declares a tenant field, and a test parses the AST to keep it
that way.

## Why `project` originally carried only `job_title` — **resolved**

`creer_prospect` persists exactly seven caller-supplied fields: `first_name`,
`last_name`, `email`, `phone`, `mobile`, `job_title`, `source`. Four are identity,
`source` is derived from `source_system` by the ingest service, `mobile` is
outside the published contract. `job_title` was what was left — so it landed in
`project` for want of anywhere better, not because it belonged there.

What a solar form calls a project — postcode, roof area, consumption, simulator
answers — had **no canonical column in Prospect 360**. Inventing columns would
have made the DTO accept data the database discards; a free-form blob would have
broken minimisation. Both were refused, and that refusal still stands.

**Both halves are now decided.** Solar qualification gets a vertical profile
entity (DEC-P5A-QUAL-01…06, §Phase 5A-P4), and `job_title` moves to `contact`
where it always belonged (DEC-P5A-QUAL-07, §Phase 5A-P5).

## Consent — processing only

`consent.processing` is typed `Literal[True]`. There is no value a producer can
send that means "no": the documented transaction boundary writes a
`consent_records` row of type `data_processing` with no conditional branch, so a
refusal has no row to write and no place in this contract.

`version`, `timestamp` and `source` are **required and never manufactured**. They
are the proof. A platform that filled them itself would be attesting to a consent
it did not collect, at an instant it did not observe, on a text it did not show.

**No marketing consent exists in v1 and none is inferred.** `email_marketing`,
`sms_marketing` and `phone_marketing` are unreachable — not declared, and rejected
by `extra: "forbid"`. Two independent tests hold this: one walks the whole model
tree for a marketing-shaped field name, one parses the AST. A mutation test proves
both would fail if such a field were introduced.

## Bounds

Application bounds are **≤** the database constraint, always. A validator laxer
than its CHECK is a deferred outage.

| Field | Max | Enforced by |
|---|---|---|
| `external_correlation_id` | 128 | 094 `lead_acq_attr_correlation_borne` |
| `source_system` | 64 | 094 `lead_acq_attr_source_system_borne` |
| `contact.first_name` / `last_name` | 100 | `prospects` VARCHAR(100) |
| `contact.email` | 255 | `prospects` VARCHAR(255) |
| `contact.phone` | 20 | `prospects` VARCHAR(20) |
| `contact.job_title` (was `project.job_title`, P5) | 200 | `prospects` VARCHAR(200) |
| `consent.version` | 64 | application only (`text_version` is TEXT) |
| `consent.source` | 100 | `consent_records.source` VARCHAR(100) |
| `attribution.source` | 128 | 094 |
| `attribution.source_detail` | 256 | 094 |
| `attribution.landing_page` | 512 | 094 |
| `attribution.content_id` | 128 | 094 |
| `attribution.locale` | 16 | 094 |
| `attribution.search_intent` | 32 | 094 |
| `attribution.keyword_cluster` | 255 | 094 |
| `attribution.utm_*` (5) | 255 | 094 |
| `attribution.cta` | 128 | 094 |
| `attribution.conversion_type` | 64 | 094 |

`TestBornesContreLaBase` re-reads `091_lead_acquisition_attributions.sql` and
`schema.sql` and compares every bound. Drift is a red suite, not an incident.

UTM values are bounded by 094 (255) rather than by `prospects.utm_*` (100)
because the ingest writes attribution to `lead_acquisition_attributions`, which is
the entire reason that table exists. **An ingest service that also wrote UTMs onto
`prospects` would violate this table and must not.**

## Fingerprint v1

`fingerprint_version = 1`. Computed over the **validated semantic model**, never
over raw request bytes.

**Included** — everything the producer controls that the database persists. The
list below is the **as-implemented** v1; §Phase 5A-P5 carries the amended field
set that supersedes it.

```
fingerprint_version
external_correlation_id, source_system
contact.{first_name, last_name, email, phone}
project.{job_title}                          ← becomes contact.job_title (P5)
consent.{processing, version, timestamp, source}
attribution.{source, source_detail, landing_page, content_id, locale,
             search_intent, keyword_cluster, utm_source, utm_medium,
             utm_campaign, utm_content, utm_term, cta, conversion_type}
```

**Excluded:**

- `tenant_id` — already in `uq_lead_acq_attr_identite (tenant_id, source_system,
  external_correlation_id)`. Counting it twice distinguishes nothing.
- the credential: `Authorization`, public identifier, secret, `credential_hash`,
  `credential_version`, `service_account_id`. A secret rotation must not turn a
  legitimate replay into a 409.
- transport: headers, `Host`, client IP, trace id, request id, retry count.
- server-decided values: `prospect_id`, `created_at`, database defaults,
  qualification result, score.

The exclusion is **structural**, not a maintained deny-list: none of those values
has a field in the DTO, so none can reach the calculation.

### Canonicalisation

`backend/utils/json_hash.canonical_json` — the repository's single implementation:

```python
json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
```

then UTF-8 encoded, then SHA-256, lowercase hex, 64 characters — the format
`lead_acq_attr_fingerprint_format` already enforces. No salt, no HMAC: this is
request identity, not a secret. A salt would stop two application instances from
recognising each other's replays.

The canonical payload has a **fixed key set**: every key is always present, and an
absent optional is explicitly `null`.

### Null / absence semantics

**Absent ≡ `null` ≡ `""`** for every optional string, normalised to `None` during
validation. Three spellings of "the producer does not have this" must not produce
three fingerprints. Whitespace-only strings are *preserved* — only the
unambiguous case is normalised.

### String normalisation

Deliberately minimal. Nothing is lowercased, trimmed, accent-folded or
semantically rewritten except where a canonical platform normaliser already
exists. `Google` and `google` are different UTM values and fingerprint
differently. **A fingerprint is the identity of the persisted request, not a fuzzy
duplicate detector — idempotency is not contact deduplication.**

- **Email** — `prospect_import_service.normalize_email` (trim + lowercase) then
  `is_valid_email`. The same rule as the browser route and the CSV import; a third
  variant would let one person exist in two forms depending on the door used.
- **Phone** — `prospect_import_service.normalize_phone_e164` (default region FR).
  Unreadable input is **refused, never invented**. `0612345678`, `+33 6 12 34 56 78`
  and `0033612345678` all canonicalise to `+33612345678` and fingerprint
  identically.
- **Timestamp** — `datetime_utils.normalize_dt` → timezone-aware UTC, serialised
  with `.isoformat()`. `09:00:00Z`, `11:00:00+02:00` and `09:00:00.000000Z` are the
  same instant and produce the same fingerprint. Naive input is read as UTC, the
  platform rule since Phase 4.

### Versioning

`fingerprint_version` is *inside* the payload, so a v2 can never accidentally
collide with a v1 and rows already written stay interpretable.

**`canonical_ingest_payload_v1` is never edited.** A new rule is a `_v2` function
beside it. `TestGoldenV1` pins the digest *and* the exact canonical bytes of a
frozen synthetic request, so any silent change to v1 turns the suite red.

### PII

The digest derives from personal data. It is one-way, over the whole structure.
**The serialised canonical payload must never be logged in production** to debug a
fingerprint — it contains the contact in clear text. Logs may carry a fingerprint
prefix and the correlation id. The module contains no logger, and a test enforces
that. Tests inspect canonical payloads using synthetic data only.

## Still not built

The ingest application service, `POST /api/v1/lead-ingest`, and the security
matrix. `prospects.ingest` remains `enforced = FALSE`: it is raised only when a
real route enforces it, never against a placeholder.


---

# Phase 5A-P4 — Solar project qualification

**Status: SPECIFIED, not implemented.** No code, no migration, no DTO change, no
form change. This section is normative and settles what the previous slice left
open: `project` carried only `job_title` because nothing else had a canonical
home.

Platform-side tracer: **T13** in `doc/plan.md`. Product story: **US-18** in
`doc/prd.md`.

## Owner decisions — final, not reopenable

| id | decision |
|---|---|
| **DEC-P5A-QUAL-01** | `seolead/config/sites/solar_be.yaml` is the **authoritative** Solar questionnaire. The platform's `DEFINITION_PV` is not, and must eventually be retired or reconciled. **No permanent bidirectional mapping** between the two vocabularies. |
| **DEC-P5A-QUAL-02** | Persisted questionnaire definitions are **not funded** in ingest v1. v1 uses a bounded, explicit Solar vocabulary. Tenant/versioned definition persistence stays with T1. Temporary by design, with a written retirement condition. |
| **DEC-P5A-QUAL-03** | Exactly seven fields travel. Required: `owner_status`, `property_type`, `postcode`, `project_timeframe`. Included: `roof_type`, `roof_orientation`, `annual_consumption_kwh`. Excluded: `monthly_bill_eur`, `battery_interest`, free text, IA Tech Forma Nord fields. |
| **DEC-P5A-QUAL-04** | Filterable/reportable: `postcode` and `project_timeframe` **only**. The other five need to be readable on the record and available to qualification/scoring. No premature projections or indexes. |
| **DEC-P5A-QUAL-05** | Qualification data follows the prospect lifecycle — 730 days, `purge_at`, cascade. No longer analytics retention path in this phase. |
| **DEC-P5A-QUAL-06** | `monthly_bill_eur` is removed **entirely** — contract, form, persistence, fingerprint, qualification payload. Not collected and later discarded: not collected. |

## Solar Qualification Vocabulary v1

Identifier: **`solar_qualification_v1`**. Every value below is read from
`config/sites/solar_be.yaml`. Nothing is invented.

| field | req | canonical values |
|---|---|---|
| `owner_status` | ● | `OWNER` · `OWNER_TO_BE` · `TENANT` |
| `property_type` | ● | `HOUSE` · `APARTMENT` · `BUSINESS` |
| `postcode` | ● | `^[1-9][0-9]{3}$` — Belgian, 4 digits, no leading zero |
| `project_timeframe` | ● | `ASAP` · `LT_6M` · `LT_12M` · `EXPLORING` |
| `roof_type` | ○ | `PITCHED` · `FLAT` · `MIXED` · `UNKNOWN` |
| `roof_orientation` | ○ | `SOUTH` · `EAST_WEST` · `NORTH` · `UNKNOWN` |
| `annual_consumption_kwh` | ○ | integer, unit **kWh/year**, `0 ≤ v ≤ 100000` |

`UNKNOWN` is an **answer**, not an absence — the form offers it explicitly. An
absent answer stays absent and must never be coerced to `UNKNOWN`; the two mean
different things and would fingerprint differently.

**Postcode contract.** Validated against the pattern above. The producer already
applies `normalize_postcode` (strip non-word characters, uppercase, truncate 16)
before the pattern is checked; the platform receives the normalised form and
re-validates rather than trusting it. Belgium-only in v1 — a second market makes
this a per-market rule, not a wider regex.

**Consumption contract.** Integer kWh per year. The unit is part of the contract,
not a convention: a value in kWh/month would be silently plausible and wrong.
`0` is a legitimate answer (a new build with no history); absent is not `0`.

**Retirement condition.** When T1 delivers persisted, per-tenant, versioned
questionnaire definitions, `solar_qualification_v1` **migrates onto that
definition**. It does not coexist — a third questionnaire system would be worse
than today's two. Trigger: T1 ships a persisted definition for tenant
`solar-belgium`.

## Differences found against current code

| | finding |
|---|---|
| DTO | `ProjectIngest` currently declares **`job_title` only**. None of the seven exist yet. |
| `job_title` | Appears in **no** Solar form field. **Resolved by DEC-P5A-QUAL-07** (§Phase 5A-P5): it moves to `contact` as a cross-vertical person attribute. |
| `monthly_bill_eur` | Present in `solar_be.yaml` at lines 99 and 156. **No code references it** — removal is a two-line config deletion. |
| `battery_interest` | Present in the form, deliberately **not** ingested (DEC-03). The form keeps it; the contract does not carry it. |
| `DEFINITION_PV` | Uses `south/south_east/south_west/east/west/north` where the form uses `SOUTH/EAST_WEST/NORTH/UNKNOWN`, and `dwelling` where the form uses `property_type`. Confirms DEC-01: reconcile, never map both ways forever. |

## Persistence characteristics required

No SQL here, and no table or index names — those are implementation.

**Authority:** a dedicated Solar vertical profile entity, per **ADR-005**
(*"les données métier (solaire, énergie, formation) vont dans des profils
séparés"*). **Projection:** none by default; `postcode` and `project_timeframe`
may be projected only if measurement shows filtering requires it.

Required properties:

- typed, bounded values with a **closed allowlist per field** — precedent:
  `contact_classification_records` (028), which mirrors its allowlist in a CHECK;
- **tenant ownership** — `tenant_id`, composite FK `(tenant_id, prospect_id)`,
  RLS enabled *and* forced, one policy per command (precedent: 094);
- **prospect ownership** — cascade delete with the prospect;
- **provenance** — the answer is *declared by the producer*, never verified; the
  source is recorded alongside it, as 028 does;
- **write semantics** — an acquisition answer is a dated fact about an arrival,
  not a mutable attribute of the person; append-safe, not freely updatable;
- **retention** — the prospect's: 730 days, `purge_at`, cascade;
- the **vocabulary version** is stored with each answer set.

Forbidden: Solar columns on `prospects`; a JSON blob; free text.

## Read model

`prospect_360_service` exposes a **"Projet solaire"** section, following the
existing **"Financement"** section, which is already a vertical block (CPF / FAF /
OPCO). The sales user reads the seven values on the prospect record. **Raw SQL is
never a proof path.**

## Machine-ingest DTO impact

`ProjectIngest` gains the seven fields, each as a bounded typed value —
`Literal` unions for the five enumerations, a pattern-constrained string for
`postcode`, a bounded integer for `annual_consumption_kwh`. `extra: "forbid"`
already refuses everything else, so no deny-list grows.

`monthly_bill_eur` is never added.

## Fingerprint impact — decided

**These fields MUST participate in the fingerprint.** They are producer-controlled
and persisted: two requests differing only in `postcode` are different requests,
and a fingerprint that ignored them would let a corrected roof type replay as
identical and be lost in silence — the exact failure `payload_fingerprint` exists
to prevent.

**Decision: amend v1 in place. Do not bump to v2.**

The versioning rule says `canonical_ingest_payload_v1` is never edited, and its
stated reason is *"les lignes déjà en base ont été calculées avec la v1"*. That
reason is **not yet engaged**:

- migration 094 is **absent from production**; `lead_acquisition_attributions`
  has zero rows anywhere;
- there is **no route**, so no producer has ever computed a v1 fingerprint;
- `prospects.ingest` is `enforced = FALSE` and the contract is unpublished.

Burning v2 on a v1 that never existed in the wild would leave two canonicalisers
to maintain from the first day and a version number that identifies nothing.

Two obligations come with that choice:

1. `TestGoldenV1` — both the pinned digest and the pinned canonical bytes — is
   updated **deliberately, in the same commit** as the field-set change, never
   as a follow-up fix to a red suite.
2. **v1 becomes immutable** at the earlier of: the ingest route being enabled in
   any environment a producer can reach, or the first
   `lead_acquisition_attributions` row being written. After that instant, any
   change to the field set is a v2 written beside v1, never over it.

`fingerprint_version` stays `1` and stays inside the payload.

## SEO Lead Factory form impact

**Remove:** `monthly_bill_eur` — from the `consumption` step field list (line 99)
and its definition (line 156). No code references it.

**Keep and verify:** `owner_status`, `property_type`, `postcode`,
`project_timeframe`, `roof_type`, `roof_orientation`, `annual_consumption_kwh`.

**Keep, do not ingest:** `battery_interest`.

**`DESIGN_REFERENCE_REQUIRED = NO.`** The `consumption` step keeps two fields
(`annual_consumption_kwh`, `battery_interest`), its title and its description. No
step becomes empty, no step count changes, no new component, state or copy is
required. This is a field deletion inside an existing multi-step layout.

## Contradiction retirement

```
AUTHORITATIVE      seolead/config/sites/solar_be.yaml
NON-AUTHORITATIVE  backend/hermes_skills/… DEFINITION_PV
                   (test fixture in tests/hermes_solar_bench.py; installed only
                   by that bench; no production caller)
```

`DEFINITION_PV` is **not deleted here** — no approved cleanup tracer exists, and
it is live test scaffolding for the qualification engine. It must stop being
readable as a second canonical Solar questionnaire. Retirement is owned by **T1**,
which consolidates qualification onto one definition.

Until then, the first implementation task that touches `tests/hermes_solar_bench.py`
must add a comment there pointing at this section, so the fixture cannot be
mistaken for a specification. That note is **not yet written** — no code was
modified in this specification pass.

`REMOVAL_TRIGGER` = T1 delivers a persisted definition for `solar-belgium`.


---

# Phase 5A-P5 — `job_title` ownership, and the amended v1 field set

**Status: SPECIFIED, not implemented.** No code, no DTO, no fingerprint, no
migration, no route. This section is **normative** and supersedes the shape and
fingerprint field set recorded in Phase 5A-P2/P3.

| id | decision |
|---|---|
| **DEC-P5A-QUAL-07** | `job_title` is a **person attribute**, not project qualification. It moves from `project` to `contact` and stays a generic cross-vertical contact attribute. It is **not** dropped from the machine-ingest contract, and it does **not** remain inside `project`. `ProjectIngest` becomes exclusively Solar project qualification. |

`job_title` was in `project` for want of anywhere better — it is what remained
after identity, consent and attribution were accounted for. It describes the
person, and the block that holds the person is `contact`. Leaving it in `project`
would have meant a Solar qualification block containing one field no Solar form
asks and seven it does.

## Normative contract shape

```jsonc
{
  "external_correlation_id": "…",   // required, 1–128
  "source_system":           "…",   // required, 1–64

  "contact": {
    "first_name", "last_name", "email", "phone",
    "job_title"                     // ← moved here (DEC-P5A-QUAL-07)
  },

  "project": {                      // ← exclusively Solar qualification
    "owner_status", "property_type", "postcode", "project_timeframe",
    "roof_type", "roof_orientation", "annual_consumption_kwh"
  },

  "consent":     { "processing", "version", "timestamp", "source" },
  "attribution": { …14 fields, unchanged… }
}
```

Values, bounds and the `UNKNOWN`-is-an-answer rule for the seven project fields
are in §Phase 5A-P4 and are unchanged by this amendment.

**Absent, and not by omission:** `tenant_id`, `service_account_id`,
`prospect_id`, every channel-marketing consent field, `monthly_bill_eur`,
`battery_interest`, and any arbitrary metadata or blob. `extra: "forbid"` on
every model makes each of these a 422 rather than a silent drop.

## Amended fingerprint v1 field set

```
fingerprint_version
external_correlation_id, source_system

contact.{first_name, last_name, email, phone, job_title}

project.{owner_status, property_type, postcode, project_timeframe,
         roof_type, roof_orientation, annual_consumption_kwh}

consent.{processing, version, timestamp, source}

attribution.{source, source_detail, landing_page, content_id, locale,
             search_intent, keyword_cluster, utm_source, utm_medium,
             utm_campaign, utm_content, utm_term, cta, conversion_type}
```

`job_title` **remains material and remains included** — it is producer-controlled
and persisted by `creer_prospect`. Only its position changes, from the `project`
sub-object to the `contact` sub-object.

That relocation is **not** cosmetic for the digest: the canonical payload nests
by block, so moving a key between blocks changes the canonical bytes and
therefore the fingerprint of an otherwise identical request. This is one more
reason the amendment must land before the immutability trigger, not after.

The seven Solar project fields are material and **must** participate: two
requests differing only in `postcode` are different requests, and a fingerprint
blind to them would let a corrected roof type replay as identical and be lost in
silence.

Exclusions are unchanged and remain **structural** — the credential, transport
metadata and server-decided values have no field to arrive in.

## Immutability trigger — restated

**Fingerprint v1 may still be amended in place.** No v2 is created.

The justification holds because none of its preconditions has changed:

- no production route exists;
- migration 094 is not deployed;
- no `lead_acquisition_attributions` row exists anywhere;
- no producer has ever generated a production v1 fingerprint.

```
v1 becomes IMMUTABLE at the earlier of:
  1. the ingest route becoming producer-reachable in any environment
  2. the first lead_acquisition_attributions row being persisted
```

After that instant, any change to the field set — including moving a key between
blocks — is a **v2 written beside v1, never over it**. `fingerprint_version`
stays `1` and stays inside the payload.

Standing obligation while v1 is still mutable: `TestGoldenV1` — both the pinned
digest and the pinned canonical bytes — is updated **deliberately, in the same
commit** as the field-set change, never as a follow-up fix to a red suite.

## Consequences for the implementation

Two amendments now travel together and must land in **one** commit, because each
alone changes the digest and two sequential edits would burn two golden updates:

1. `job_title` moves `ProjectIngest` → `ContactIngest` (bound 200, unchanged);
2. `ProjectIngest` gains the seven Solar fields.

`creer_prospect` still receives `job_title`; only the DTO block it is read from
changes. No canonical prospect-creation behaviour is affected.


---

# Phase 5A-P6 — Reliable ingestion: delivery, idempotency, durability

**Status: SPECIFIED, not implemented.** No service, no route, no migration, no
DTO or fingerprint change, `prospects.ingest.enforced` untouched. This section is
normative and **supersedes the Phase 1 status table above** where they disagree.

Platform tracer: **T14** in `doc/plan.md`. Product story: **US-19** in
`doc/prd.md`.

## Owner decisions — final, not reopenable

| id | decision |
|---|---|
| **DEC-P5A-INGEST-01** | A same-key / different-payload conflict is **not accepted**. Domain outcome `IDEMPOTENCY_CONFLICT`, future HTTP 409. Zero prospect, zero consent, zero attribution, zero `prospect.created`, zero qualification work. The producer **must not** mark the lead exported, **must not** auto-mint a new `external_correlation_id`, and parks it for explicit reconciliation. |
| **DEC-P5A-INGEST-02** | Machine ingest **must not** copy the browser's post-COMMIT fire-and-forget HTTP call. Qualification is a **durable outbox work item** written inside the business transaction; a consumer performs the external trigger. Failure must never lose the intent. Browser alignment is recorded as debt, not done here. |
| **DEC-P5A-INGEST-03** | An idempotency conflict requires **durable platform audit evidence**, via the existing `platform_audit_logs` architecture and one new allowlisted event type. **No separate business conflict table.** PII-safe fields only. |

## The atomic unit

```
BEGIN tenant_transaction(tenant_id)     ← tenant from the VERIFIED identity only
    prospect                            (creer_prospect, provenance service_account)
    data_processing consent             (same connection — see refactor below)
    lead_acquisition_attributions       (… payload_fingerprint)
    prospect.created                    (event_outbox, same connection)
    qualification work item             (event_outbox, same connection)
COMMIT
──────────────────────────────────────────────────────────────────────────────
AFTER COMMIT: nothing. The outbox worker performs the external trigger.
```

**No outbound HTTP inside the transaction, and none from the request path after
COMMIT.** A prospect cannot commit without its idempotency key, and the intent to
qualify it cannot be lost while the prospect survives.

## Required consent refactor

Measured, not assumed: `consent_service.record_consent` and
`consent_capture_service.capture_consent` are both **channel-keyed**
(`email → email_marketing`, `sms → sms_marketing`, `whatsapp → sms_marketing`,
`phone → phone_marketing`) and both open **their own** `tenant_transaction`.

**No code path can write `type = 'data_processing'` at all**, and none accepts a
caller's connection. This is the same defect Phase 5A-P2 found for prospect
creation, one layer down.

```
REQUIRED   the canonical consent writer gains a data_processing path that
           accepts the caller's connection/transaction
FORBIDDEN  a bare INSERT into consent_records from the ingest service —
           consent is an SSOT, not a column
INVARIANT  browser marketing-consent behaviour is unchanged: same channels,
           same own transaction, same prospects.consent_<channel> projection
```

## Idempotency — algorithm A

Identity fixed by 094: `(tenant_id, source_system, external_correlation_id)`.

```
1. optional fast-path read of the attribution by its identity
2. if absent: attempt the COMPLETE business transaction
3. uq_lead_acq_attr_identite decides the concurrent winner
4. the loser takes an EXPECTED unique violation
   (recognised by constraint name, not by exception type)
5. its transaction rolls back ENTIRELY — prospect, consent, attribution,
   events: nothing survives
6. it opens a FRESH tenant transaction
7. it re-reads the committed winner
8. same fingerprint      → IDEMPOTENT_REPLAY
9. different fingerprint → IDEMPOTENCY_CONFLICT
```

**No advisory lock by default.** The repository uses them (`appointment_service`,
`twilio_canary_guard`) exactly where no constraint can express the invariant —
overlapping time ranges. Here one can, and 094 says so: *« L'idempotence est une
contrainte, pas une vérification applicative »*. A lock would not remove the
exception path, which must be written and tested regardless.

**No second idempotency mechanism.** `webhook_replay_keys` is provider-scoped and
serves provider callbacks; 094 supersedes it here.

## Domain results — transport-free

```
CREATED               prospect_id · external_correlation_id
IDEMPOTENT_REPLAY     original prospect_id · external_correlation_id
IDEMPOTENCY_CONFLICT  external_correlation_id
                      NO identifier from the rolled-back work
```

No HTTP status code inside the application service. The transport tracer maps
them, as `_TIMELINE_ERRORS` already does for the timeline.

## Write counts per outcome

| | prospect | consent | attribution | `prospect.created` | qualification |
|---|---|---|---|---|---|
| `CREATED` | 1 | 1 | 1 | 1 | 1 |
| `IDEMPOTENT_REPLAY` | 0 | 0 | 0 | 0 | 0 |
| `IDEMPOTENCY_CONFLICT` | 0 | 0 | 0 | 0 | 0 |
| concurrent loser | 0 | 0 | 0 | 0 | 0 (rolled back) |

A replay writes no consent, and that is semantics rather than optimisation: a
second row would fabricate a second granting instant for one signature.
`consent_records` is evidence, not a counter.

## Qualification as durable work

Two properties come free from what exists:

- `event_outbox` carries `uq_outbox_idempotency (tenant_id, idempotency_key)`,
  so a doubled emit is absorbed by `ON CONFLICT DO NOTHING`. The key derives from
  the prospect identity;
- the worker claims with `FOR UPDATE SKIP LOCKED` **and** honours
  `next_attempt_at`, so two workers never process the same item and backoff is
  real rather than notional.

**One catalogue entry must be added.** `domain_events.CATALOGUE` has
`prospect.created` and `prospect.qualified` — the fact and the outcome — but
nothing expressing the *request*. Reusing `prospect.created` would make the
browser path qualify too, and it already triggers by its own route: the same
person would be qualified twice. The catalogue states the rule itself: *« l'ajouter
est une décision, pas un effet de bord »*.

### Failure of the external trigger

```
destination unavailable
  → the prospect STAYS accepted
  → the work item stays PENDING with next_attempt_at (exponential backoff)
  → event_retry_service classifies the error: retry or abandon
  → abandoning writes event_dead_letters (category, first AND last error,
    attempt count, replayable or not) and marks the event FAILED
  → FAILED is terminal, countable and visible
NEVER
  → the call fails, the intent disappears, and the prospect stays
    unqualified forever with nobody informed
```

Nothing new is built: retry / abandon / replay already exist and are the entire
reason `event_retry_service` was written.

## Conflict audit

A conflict writes no business row, so without evidence only a rotating log would
remain. `platform_audit.record` acquires its **own** connection and never raises,
so it survives the loser's rollback — precisely the property needed.

```
ONE audit event type to add, following the existing SCREAMING_SNAKE convention
(cf. PLATFORM_AUTH_FAILURE, CROSS_TENANT_ACCESS_DENIED):

  LEAD_INGEST_IDEMPOTENCY_CONFLICT

Bounded by chk_platform_audit_event_type; migration 075 is the extension
precedent. No business conflict table — DEC-P5A-INGEST-03.
```

**Safe:** `tenant_id` · service-account **public** identifier · `source_system` ·
`external_correlation_id` · operation · outcome · timestamp · fingerprint prefix.
**Never:** canonical payload · full fingerprint · email · phone · postcode ·
`Authorization` · token · secret · credential hash or version.

`platform_audit._scrub` already denies keys matching
`email|phone|token|secret|authorization|address` *and* redacts values that look
like an email or phone — it catches the `detail="…"` case a key allowlist misses.

## Producer retry matrix — normative

**This replaces the Phase 1 status table where they disagree.**

| class | examples | producer behaviour |
|---|---|---|
| **TRANSIENT** | DB unavailable, timeout with no response, selected 5xx | retry with bounded backoff, then queue |
| **PERMANENT** | validation (422), authentication (401), authorization (403) | **do not retry blindly** — stop and alert |
| **IDEMPOTENT_REPLAY** | 200 | treat as success, store the returned `prospect_id` |
| **IDEMPOTENCY_CONFLICT** | 409 | **not accepted.** Park for reconciliation. **No automatic retry. No new correlation id. Do not mark the lead exported.** |

The last row is the correction. A producer that auto-minted a fresh correlation
id would turn one person into two prospects and hand the problem to contact
deduplication, which nobody owns.

## Observability

**Allowed:** `tenant_id` · service-account public identifier · `source_system` ·
`external_correlation_id` · `prospect_id` after success · `attribution_id` ·
domain outcome · `duration_ms` · replay/conflict classification · short
fingerprint prefix.

**Forbidden:** `first_name` · `last_name` · `email` · `phone` · `postcode` ·
canonical payload · full fingerprint · `Authorization` · secret · credential hash
· credential version.

## Boundary with the transport tracer

T14 receives an **already-verified machine identity** and owns orchestration,
atomicity, idempotency, durable scheduling, conflict evidence and the domain
result. A later tracer owns `Authorization` parsing, invoking the verifier,
enforcing `prospects.ingest`, HTTP status mapping, route exposure, and the
`enforced = TRUE` transition.

Splitting here is deliberate: bundling them would force capability enforcement
live before the domain behaviour is proven, and a new external capability is
disabled by default — *« Un drapeau neuf vaut `False`. Toujours. »*


---

# Phase 5A-P7 — The HTTP transport boundary

**Status: SPECIFIED, not implemented.** No route, no migration, no DTO or
fingerprint change, `prospects.ingest.enforced` untouched, no credential minted.
This section is normative and **supersedes the Phase 1 request/response block**
where they disagree.

Platform tracer: **T15** in `doc/plan.md`. Product story: **US-20** in
`doc/prd.md`.

## Owner decisions — final, not reopenable

| id | decision |
|---|---|
| **DEC-P5A-TRANSPORT-01** | After successful authentication, machine traffic is rate-limited on the **verified** identity — `tenant_id` + service-account public identifier. Before authentication, the existing anonymous/IP protection stands. **No second authentication implementation** may exist inside the rate limiter: the secret is never parsed or revalidated by a parallel security path. Rate limiting is an operational control, never an authentication mechanism. No new infrastructure. |
| **DEC-P5A-TRANSPORT-02** | The success response is **minimal**: `outcome`, `prospect_id`, `external_correlation_id` — and no `prospect_id` on conflict. `tenant_id`, `score`, `dedup`, attribution internals, fingerprint and service-account internals are never returned. The Phase 1 shape is superseded. |

## The contract

```http
POST /api/v1/lead-ingest
Authorization: Bearer <public_identifier>.<secret>
Content-Type: application/json
```

Body: `LeadIngestRequest`, unchanged. **Not under `/webhooks`** — that prefix is
skipped entirely by `rate_limit.classify()` and connotes signature auth, which
this is not.

| outcome | status | body |
|---|---|---|
| `CREATED` | **201** | `outcome`, `prospect_id`, `external_correlation_id` |
| `IDEMPOTENT_REPLAY` | **200** | `outcome`, `prospect_id`, `external_correlation_id` |
| `IDEMPOTENCY_CONFLICT` | **409** | `outcome`, `external_correlation_id` |

Errors use the platform's existing global envelope —
`{"error", "status_code", "request_id"}` — applied by `main.py`'s exception
handler. The application service knows no HTTP status; the route projects.

## Order of guards

```
1. Content-Type              non-JSON refused
2. body size                 refused BEFORE full parse
3. authentifier()            → IdentiteMachine, or 401
4. possede(prospects.ingest) → or 403
5. rate limit                on the VERIFIED machine identity
6. DTO validation            → or 422
7. fingerprint v1
8. T14 ingerer_lead(identite, demande)
9. status projection         201 / 200 / 409
```

The order is the specification. **T14 is never reached if 3 or 4 refuses** —
that is an acceptance criterion, not a hoped-for consequence.

## Authentication and tenant

`service_account_auth.authentifier(<raw header>)`. The route reimplements
nothing. Tenant comes from `identite.tenant_id` and nowhere else — never body,
query, path, Host or a tenant header.

**All six refusal categories** — `ABSENT`, `MALFORME`, `INVALIDE`, `INACTIF`,
`COUPE_CIRCUIT`, `EXPIRE` — return the **same 401 and the same body**. The
verifier already collapses "unknown identifier" and "wrong secret" into one
category; the route must not re-expand them.

## Authorization and its audit

`identite.possede("prospects.ingest")`, in the route, before T14. The human path
(`exiger_permission` → `authorization_service.autoriser`) is membership-centric
and not reusable for a machine identity. Missing capability → **403**,
uninformative body, zero T14 invocation.

**A defect this specification surfaced.** `authorization_service.journaliser_decision`
writes `AUTHZ_DENIED` / `AUTHZ_DECISION`, but **neither is in
`platform_audit.EVENT_TYPES` nor in the database CHECK**. `record()` never
raises: it logs `platform_audit_unknown_event_type` and returns `False`. Measured
consequence — for all **25 sensitive human permissions**, every authorization
decision has been discarded in silence since that code was written. This is
migration 075's documented trap one layer up: the Python allowlist refuses before
the CHECK is ever consulted.

So the vocabulary is not invented, it is **repaired**: register `AUTHZ_DENIED`
and `AUTHZ_DECISION`, and reuse `AUTHZ_DENIED` for machine capability denial. The
side effect — human authorization decisions start being recorded again — is the
repair working, not a widening of scope.

## Rate limiting

```
BEFORE auth   existing anonymous/IP protection, unchanged
AFTER auth    rl:machine:<tenant_id>:<public_identifier>
              — same shape as api_user_key / api_anon_key
NEVER key on  the secret · Authorization · an email ·
              external_correlation_id · source_system alone
```

**Enforced in the route, after authentication**, calling
`rate_limit_service.check_rate_limit`. Not in the middleware: it runs before the
route and could only learn the verified identity by **re-authenticating**, i.e.
by building a second security path that parses the secret. Two implementations of
one check always diverge, and the one that is not primary is the one nobody
remembers to fix.

Same Redis, same counters, and the same **fail-open** policy the middleware
already documents — inventing a stricter one here would create a second policy.

## Body size

```
MEASURED   sum of DTO bounds                ≈ 3,825 characters
           + keys and JSON punctuation      ≈ 4,175 bytes in ASCII
           × 4 (UTF-8 worst case)           ≈ 16 KiB
           pathological \uXXXX escaping     ≈ 50 KiB
ADOPTED    64 KiB
```

About fifteen times the realistic payload, covering the worst encoding case, and
**four times smaller** than the repository's existing precedent
(`calendly_webhook_service`: 256 KiB), which carries something else entirely.
Copying 256 KiB would have been easier and wrong: the bound comes from the actual
maximum valid document. It must apply early enough that a huge body is never
parsed in full.

## The two correlations are not the same

```
TRANSPORT  X-Correlation-ID / X-Request-ID — middleware, honoured inbound,
           echoed outbound. Does NOT enter fingerprint v1.
BUSINESS   external_correlation_id, in the body. Enters fingerprint v1 and the
           database idempotency identity.
```

Neither is defaulted from the other. Conflating them would make idempotency
identity depend on a transport header — turning a legitimate replay into a new
submission.

## Observability

The middleware already logs method, path, status, duration, request id and
correlation id; the route does not repeat them.

**Allowed:** authenticated `tenant_id` · service-account **public** identifier ·
`source_system` · `external_correlation_id` · outcome · status · duration ·
`prospect_id` after success.
**Never:** `Authorization` · secret · credential hash or version · names · email
· phone · postcode · canonical payload · full fingerprint.

## Failure matrix

| | HTTP | Retry safe | Business writes | Evidence |
|---|---|---|---|---|
| **A** invalid JSON | 422 | no | none | request log |
| **B** invalid DTO | 422 | no | none | request log, no field values |
| **C** auth failure | **401**, identical body | no | none | `PLATFORM_AUTH_FAILURE` |
| **D** capability absent | **403** | no | none | `AUTHZ_DENIED` |
| **E** CREATED | 201 | yes → replay | five, one txn | request log |
| **F** REPLAY | 200 | yes | **none** | request log |
| **G** CONFLICT | 409 | **no** — park | none | `LEAD_INGEST_IDEMPOTENCY_CONFLICT` |
| **H** transient internal | 5xx | **yes**, backoff | none | error log, no PII |
| **I** disconnect after COMMIT | not observed | yes → **F** | committed once | request log |
| **J** revoked concurrently | 401 or 201 | yes | 0 or 1 | auth audit if refused |

**J** resolves at authentication: status and permissions are read there, so a
revocation lands either before the check (401, nothing written) or after it (the
request completes). No torn state either way.

## `prospects.ingest.enforced`

Migration 095 stays **immutable**. No runtime code reads `enforced` — for any
permission — so flipping it is **declarative**, a statement of intent. The actual
enforcement is `possede()` in the route, and **route enforcement must never
depend on the flag**.

A new migration **097** exists solely to set `enforced = TRUE`, after real
enforcement ships. Its rollback sets it back to `FALSE`.

## Deployment order

The CD pipeline runs **no migrations** (`cd.yml`: *« aucune migration »*), so code
and schema are sequenced by hand. Both windows fail closed:

```
1. apply migrations 094 / 095 / 096
2. deploy route code that authenticates and enforces prospects.ingest
3. apply 097 (enforced = TRUE) + the audit-vocabulary repair
4. only then mint and grant a service account

route before 095 → capability absent from the catalogue → no grant can exist
                 → 403 for everyone
095 before route → capability exists, nothing reachable

ROLLBACK  withdraw the route code first; roll back 097 second if release policy
          requires it. Removing the router registration closes the door.
```

## Fingerprint v1 arming

There is no route feature flag in this architecture, and the API is publicly
served. **Producer-reachable therefore means: the deployed image containing the
router registration.** The gate is the commit that registers the machine router.

Until that ships, v1 changes only by approved spec amendment. After it ships, v1
is immutable and any canonical field-set or layout change is a **v2 beside v1,
never over it**.

An **arming record** must be written into this document at that moment:

```
FINGERPRINT_V1_ARMED
  arming commit      <sha>
  deployed revision  <image revision / sha>
  armed at           <UTC timestamp>
  fingerprint_version 1
  golden digest      <TestGoldenV1.CONDENSE>
  canonical field set §Phase 5A-P5
```

The route is **not production-ready** until that record exists. `TestGoldenV1`
already pins the digest and the canonical bytes; arming makes that pin permanent
rather than deliberately updatable.

## OpenAPI, CORS, CSRF

Measured: production serves `/openapi.json` (200, externally reachable) while
`/docs` and `/redoc` are 404 (`docs_url` gated on `app_debug`). The convention is
*schema public, UI disabled*, and the route follows it. **Hiding the route would
be security through obscurity and is not a control** — it is authenticated, and
that is the control.

No CSRF machinery exists in the backend, and none applies to a bearer M2M call.
CORS governs browsers only, grants no authentication, and must never become the
access control. Neither changes.
