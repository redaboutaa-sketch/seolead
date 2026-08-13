# PHASE 5A — OPEN THE REAL LEAD DESTINATION

**Date:** 2026-08-13
**SEO Lead Factory:** `/opt/seolead`, branch `main`, HEAD `3ad9cb0` (unchanged)
**Prospect 360:** `github.com/redaboutaa-sketch/techformanord`, deployed revision `79666ba912cb`
**Outcome:** **BLOCKED at the platform gate (§50).** Discovery complete; no code
written in either repository.

---

## 1. Executive Summary

Discovery is finished and it changed the picture. Three of the eight §50 stop
gates are triggered, and the mission is explicit that these are stop conditions
rather than obstacles to route around.

**The blocking finding: there is no canonical prospect creation service to call.**
Prospect creation lives inline inside the HTTP route handler
`backend/routes/prospects.py::create_prospect`, bound to the browser tenant-scope
dependency. §13 forbids duplicating that logic into a new ingest route, and the
only compliant alternative — extracting a domain service — is a refactor of a live
production write path on a repository that is under active development right now.
That is an owner decision, not an implementation detail.

**The good news is larger than expected.** The platform is materially more ready
than Phase 1 recorded:

- `tenant_service_accounts` is now backed by real code — create, rotate, revoke,
  with hashed secrets, a kill switch armed by default, and a machine-role flag. It
  is well-suited to §7 and should be **reused**, not adapted.
- A consent SSOT exists (`consent_records`) whose `type` vocabulary already
  contains `data_processing` alongside channel-scoped `email_marketing` /
  `sms_marketing` / `phone_marketing`. Consent maps almost cleanly.
- `event_outbox`, `event_destinations`, `event_dead_letters` and
  `platform_audit_logs` all exist — the audit and outbound-delivery architecture
  the mission asks for is already there.
- `prospects` already carries `utm_source`, `utm_medium`, `utm_campaign`,
  `utm_content`, `source`, `source_detail`.

**What is genuinely missing is narrow and buildable:** a credential *verifier*
(accounts can be minted but nothing authenticates them), an idempotency key with a
database constraint, `utm_term` and the SEO-specific attribution fields, and one
consent mapping decision that carries legal weight.

Nothing in either system was modified. No lead exists to be at risk: the funnel is
empty and lead capture is unchanged.

---

## 2. Initial State

| Item | Value |
|---|---|
| seolead branch / HEAD | `main` / `3ad9cb053c3eaeba62fccf54586da7fb29c41c0a` |
| seolead working tree | clean |
| `captured_lead` | 0 |
| `lead_attribution` | 0 |
| `PENDING_EXPORT` | 0 |
| `EXPORTED` | 0 |

No real visitor has submitted since the last verification, so nothing needed
preserving. Had a lead existed it would have been treated as real.

---

## 3. Prospect 360 Current Deployment Discovery

```
VERIFIED_ACTIVE_RELEASE   /opt/techformanord-releases/79666ba912cb
VERIFIED_ACTIVE_SHA       79666ba912cb9a92ac342654036c1729c552e952
VERIFIED_PLATFORM_DB      acquisition_platform @ platform_postgres (pgvector/pg16)
VERIFIED_API_CONTAINER    platform_api
                          ghcr.io/redaboutaa-sketch/techformanord/api
                          @sha256:e2b695c2a40b…
                          built 2026-08-13T18:52:03Z
```

Canonical repository: `github.com/redaboutaa-sketch/techformanord` (private).
Default branch `claude/ai-acquisition-platform-w0e9wl`, whose tip is **identical**
to the deployed revision.

### A trap the mission warned about, and it was real

`/opt/techformanord` **is not the deployed source**. It is a stale working
checkout: branch `claude/beaver-ui-redesign`, HEAD `d54daea` from 29 July, with
**27 uncommitted modified files**. Developing there would have built on the wrong
code and destroyed someone else's uncommitted work. It was not touched.

Discovery was done in a fresh clone at `/opt/p360-phase5a`, checked out detached at
the deployed revision, zero local changes.

### Architecture, measured not assumed

`CLAUDE.md` in that repository is explicit that several common assumptions are
wrong, and it is correct:

| Assumed | Actual |
|---|---|
| SQLAlchemy / ORM | **zero** — `asyncpg` and hand-written SQL |
| Alembic migrations | **none** — numbered `database/migrations/NNN_*.sql` + `MANIFEST.tsv` |
| `org_id` | `tenant_id` |

Two conventions govern any change here:

- **Every** read and write goes through `tenant_transaction(tenant_id, pool=pool)`,
  which sets a transaction-local `app.tenant_id`. Tenant comes **exclusively** from
  a verified JWT; a client-supplied `tenant_id` is an assertion to check, never an
  instruction. Another tenant's object returns **404**, never 403.
- **No external effect may be triggered from an HTTP request.** Anything destined
  for n8n, a CRM or a provider is written to `event_outbox` *in the same
  transaction* as the business write. A `BackgroundTasks` webhook is described as a
  defect, not a shortcut.

Runtime DB role is `platform_app` — NOSUPERUSER, NOBYPASSRLS, owns nothing.

### Active development in flight

PR #67 was opened at 20:03Z, roughly twenty minutes before this discovery, and the
deployed image was built ninety minutes before it. This repository is being worked
on concurrently. That is a coordination fact the owner should weigh before a second
stream of work adds an authentication surface to it.

---

## 4. Verification of Phase 1 Findings

| Phase 1 finding | Status | Evidence |
|---|---|---|
| Prospect-write routes rely on cookie/JWT auth | **UNCHANGED** | `create_prospect` depends on `exiger_portee_tenant`; tenant from verified JWT only |
| Host↔tenant binding enforced | **UNCHANGED** | `enforce_host_binding` in `backend/deps.py` |
| `tenant_service_accounts` exists | **UNCHANGED** | migration `069_invitations_and_service_accounts.sql` |
| …had zero rows | **UNCHANGED** | live count = **0** |
| …no backend code references it | **CHANGED** | `services/tenant_membership_service.py` + `routes/tenant_admin.py` now create / rotate / revoke |
| `ProspectCreate` lacks UTM fields | **UNCHANGED (model)** / **CHANGED (table)** | model has none; `prospects` table **has** `utm_source, utm_medium, utm_campaign, utm_content` |
| n8n webhook is a log/discard stub | **NO_LONGER_APPLICABLE** | `POST /webhooks/n8n/{slug}` still exists but is irrelevant — §27 forbids n8n for this phase |

---

## 5. Service Account Authentication — assessment

**Schema verdict: REUSE.** `tenant_service_accounts` is close to purpose-built:

```
tenant_id             FK → tenants          tenant-scoped
owner_membership_id   a membership, not a bare user_id
role_code             + role_human_assignable  (machine-role flag)
status                default 'PROVISIONING'
public_identifier     circulates and is logged; proves nothing alone
credential_hash       the fingerprint, never the secret
credential_version    increments on rotation; old secret dies immediately
kill_switch_engaged   DEFAULT TRUE — inert until explicitly disarmed
```

Minting exists: `secrets.token_urlsafe(32)`, stored hashed, cleartext crossing the
boundary exactly once. Rotation and revocation exist. Management routes are gated
on `tenant.service_accounts.manage`.

**The gap: nothing authenticates with it.** No dependency, route or middleware
reads `credential_hash` to verify an inbound machine request. Accounts can be
minted, rotated and revoked, and there is no door for the holder to knock on.

That is a build task, not an incompatibility — but it means Phase 5A would
introduce a **new authentication surface into a live multi-tenant CRM**, which is
the single highest-risk change in this mission and the reason the platform gate
matters.

---

## 6. Tenant Isolation

Verified live, not trusted from the prompt:

```
64edc9e3-0b91-442a-9d02-7964f2001a55 | solar-belgium | Solar Belgium
```

Isolation model is strong and already enforces what §10 requires: tenant derives
from verified identity, never from a body parameter; RLS is `ENABLE` **and**
`FORCE`, one policy per command; composite foreign keys `(tenant_id, x_id)`.

A service-account credential resolving to exactly one tenant fits this model
naturally — the credential becomes the identity, replacing the JWT as the tenant
source, with `assert_tenant_match` semantics unchanged.

---

## 7–8. Ingestion Contract and Idempotency — what is missing

| Need | Present? |
|---|---|
| `utm_source / medium / campaign / content` | **yes** on `prospects` |
| `utm_term` | **no** |
| `source`, `source_detail` | yes |
| `landing_page`, `content_id`, `locale`, `search_intent`, `keyword_cluster`, `cta`, `conversion_type` | **no** |
| `external_correlation_id` / `external_id` | **no** |
| unique constraint for `(tenant, source_system, external_id)` | **no** |

Idempotency therefore **cannot be database-enforced today**. It needs an additive
migration adding the key and a partial unique index. That is straightforward and
matches repository convention — but it is platform work, and §50 lists
DB-unenforceable idempotency as a stop condition for proceeding as-is.

§14's attribution set is better served by a dedicated acquisition-attribution table
than by widening `prospects`, consistent with §13's guidance.

---

## 9. Consent — one decision, with legal weight

Better than feared. `consent_records` is a proper SSOT:

```
type    ∈ { data_processing, email_marketing, sms_marketing,
            phone_marketing, cookies, profiling }
status  ∈ { granted, revoked, expired }
+ text_version, purpose, proof, evidence, granted_at, revoked_at,
  actor_type, actor_id, ip_address, user_agent
```

Mapping:

| SEO Lead Factory | Prospect 360 | Verdict |
|---|---|---|
| `consent_processing` (required) | `type = 'data_processing'` | **clean** |
| `consent_version`, `consent_timestamp`, `consent_source` | `text_version`, `granted_at`, `source`/`purpose` | **clean** |
| `consent_marketing` (optional, **channel-unspecified**) | requires a *channel*: email / sms / phone | **DECISION NEEDED** |

The site's checkbox reads *"J'accepte de recevoir des informations sur les offres
et conseils"* — it names no channel. Writing `email_marketing` is an inference;
writing all three would manufacture consent the visitor never gave. §17 forbids
inferring, so this needs an owner/counsel answer rather than a default chosen by me.

It also connects to an already-open item: the privacy wording is still unreviewed
(`legal.reviewed: false`).

---

## 10–11. Attribution and Audit

Attribution: partially present (§7–8 above). Audit: the architecture is there —
`platform_audit_logs`, `audit_logs`, `events`, `event_outbox`, `event_destinations`,
`event_dead_letters`. Whether the event vocabulary is a closed enum with pinned
test lists was **not** fully determined, because the phase stopped before design.
§18's "add the minimal correct event, or stop and report the gate" therefore remains
open and must be settled before implementation.

---

## 12–14. SEO Lead Factory Adapter — deliberately not started

`Prospect360LeadDestination`, the export state machine, retries and the worker were
**not implemented**. Building the adapter now would mean guessing the payload shape
while the consent mapping and the attribution model are undecided — speculative
work that would likely be rebuilt. `LocalLeadDestination` remains in place and
unchanged; leads continue to be captured durably and held at `PENDING_EXPORT`.

---

## 15–19. Security / Canary / UI / Cleanup / Enablement

Not reached. No canary was run, no credential was minted, no synthetic prospect was
created in any tenant. Automatic export remains **DISABLED**.

---

## 20–22. Tests, Migrations, Resources

No code changed in either repository, so no new tests and no migrations. The
seolead baseline verified earlier this session stands: 662 backend, 20 frontend,
migration replay 6 up → 6 down → 6 up, npm audit 0 vulnerabilities.

No new container or permanent process was added.

---

## 23. Remaining Owner Inputs

Unchanged from `OWNER_INPUTS_REQUIRED_FOR_LAUNCH.md`, and now load-bearing:

- **Privacy and terms wording** — `legal.reviewed: false`. Directly blocks the
  consent-channel decision in §9.
- **Company / legal identity** — still `null`.
- **Commercial contact destination** — still unresolved; this phase existed to
  answer it.
- Domain and brand name remain the only resolved items.

---

## 24. Known Limitations

1. Event-vocabulary amendment policy not fully determined (§18).
2. The platform is under concurrent development; a second stream touching auth
   needs coordination.
3. `/opt/techformanord` is a stale, dirty checkout that looks authoritative and is
   not — a trap for the next person.

---

## 25. Exact Next Action

Four decisions unblock the whole phase. All four are owner calls:

1. **Approve extracting a prospect-creation domain service** in Prospect 360, so
   both the existing browser route and the new ingest route call one path. Without
   this, §13 cannot be satisfied.
2. **Decide the marketing-consent channel mapping** — most defensibly
   `email_marketing` only, since email is the one channel the form requires and the
   copy names no other. Ideally settled together with the privacy wording.
3. **Confirm the attribution model**: a dedicated acquisition-attribution table
   rather than widening `prospects`.
4. **Confirm timing**, given PR #67 and today's deployment.

Once those are answered, the implementation itself is well-scoped: an additive
migration (idempotency key, attribution table, `utm_term`), a service-account
credential verifier, a thin `/api/v1/lead-ingest` route, the extracted prospect
service, and the seolead adapter with its export state machine.
