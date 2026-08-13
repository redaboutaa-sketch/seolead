# PHASE 5A — OPEN THE REAL LEAD DESTINATION

**Date:** 2026-08-13
**SEO Lead Factory:** `/opt/seolead`, branch `main`, HEAD `3ad9cb0` (unchanged)
**Prospect 360:** `github.com/redaboutaa-sketch/techformanord`, deployed revision `79666ba912cb`
**Outcome (revised 2026-08-13, after the four owner decisions):** **PARTIAL.**
The blockers are resolved and the refactor they gated is done, tested and pushed.
Implementation stopped at a deliberate boundary before the authentication work.
Nothing is deployed; nothing is enabled.

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


---

# Phase 5A resumption — after the four owner decisions

## PR #67 gate

`PR67_OVERLAP = NONE`. PR #67 ("fix(voice-lab): la réconciliation lit malgré le
verrou") merged at 20:19Z touching 7 files, all voice-lab: `voice_lab_conversation`,
`voice_lab_runtime`, `voice_lab_test_orchestrator`, `twilio_gate_e_operator` and
three test files. Checked against every Phase 5A surface — prospect creation,
`routes/prospects.py`, authentication, `tenant_service_accounts`, RBAC, consent,
migrations, event vocabulary, prospect read model, UI: **clear on all ten**.

## Platform feature branch

```
branch     phase-5a-lead-ingest
start SHA  9931c5f383dcb8d4f293db844f5699450d82807d   (default branch tip after #67)
final SHA  e6885ba6009c68ab14b7b57415cb554ba26c44d7
pushed     yes (CI); NOT merged, NOT deployed
```

Work was done in the clean clone at `/opt/p360-phase5a`. `/opt/techformanord` was
never touched.

## Step 3–4 — canonical prospect creation service: DONE

`backend/services/prospect_creation_service.py` now holds the single write path.
`routes/prospects.py::create_prospect` calls it and no longer contains an INSERT.

Behaviour preserved exactly: same INSERT, same `purge_at` of 730 days, same
`consent_date` rule, same `prospect.created` emitted inside the transaction, same
score persisted before commit, `trigger_qualification` still fired after COMMIT.

Two design points that the later ingest depends on:

- **The connection is a parameter and the service opens no transaction.** The
  ingest route must write prospect + idempotency key + attribution atomically; a
  service owning its own transaction would allow a prospect to exist without its
  key, and the next retry would create a second one.
- **`provenance` / `actor` / `correlation_id` are parameters.** A machine ingest
  becomes distinguishable in the outbox without inventing event vocabulary. The
  browser route keeps `provenance="user"`.

### Non-regression result

`tests/test_prospect_creation_service_extraction.py` — **16 passed**, structural
(AST, not text) with canaries. Mutation-verified: reintroducing an INSERT into the
route fails `test_la_route_ne_contient_plus_d_insert`.

Neighbouring suite: **110 prospect-related tests pass**, 43 skipped. Two collection
errors (`test_frontend_workspace_e2e`, `test_playwright_harness_canary`) are
**pre-existing** — playwright is absent from the API image — reproduced with my
changes stashed.

Two bugs in my own tests were caught by the tests themselves: one read raw source
where the docstring names the forbidden pattern, the other compared a lowercase
needle against an uppercased haystack and therefore passed vacuously. Both are the
exact failure family this repository documents.

## Audit vocabulary — resolved without amendment

`domain_events.CATALOGUE` is closed and raises `UnknownDomainEvent`, and
`platform_audit_logs.event_type` is a closed CHECK. Neither needs extending:

- ingest success → `prospect.created` (already catalogued), carrying tenant,
  prospect id, `provenance`, `actor`, `correlation_id`, timestamp;
- auth failure → `PLATFORM_AUTH_FAILURE` (already present, exact meaning);
- cross-tenant attempt → `CROSS_TENANT_ACCESS_DENIED` (already present).

`event_outbox` has no CHECK on provenance, so `service_account` is admissible.

## Steps 5–20 — not implemented, and why

Everything from here needs the credential verifier, which is **new authentication
code in a live multi-tenant CRM**. That is the highest-risk change in this mission
and the one least suited to being written at the tail of a long session. I stopped
at a boundary where the tree is coherent, tested and deployed nowhere, rather than
produce a security surface with degraded care.

Remaining, in order, with the design already settled:

1. Migration `091` (next free number; MANIFEST.tsv line 092) — additive,
   idempotent, ending in the mandatory `DO $$ … RAISE EXCEPTION` proof block:
   - `lead_acquisition_attributions` with the Decision-3 field set,
     composite FK `(tenant_id, prospect_id) REFERENCES prospects (tenant_id, id)`
     — the required `UNIQUE (tenant_id, id)` already exists as
     `uq_prospects_tenant_id`;
   - `UNIQUE (tenant_id, source_system, external_correlation_id)` — the
     DB-enforced idempotency identity;
   - a payload fingerprint column so the same key with a different payload is a
     detectable 409 rather than a silent overwrite;
   - RLS `ENABLE` **and** `FORCE`, one policy per command.
2. Service-account credential verifier (hash comparison, `credential_version`,
   `kill_switch_engaged`, `status`), resolving to exactly one tenant.
3. `prospect.ingest` capability in the existing permission vocabulary.
4. `POST /api/v1/lead-ingest` — thin, calling the extracted service.
5. §20 test matrix, then migration replay.
6. Only then the seolead adapter, export state machine and canary.

## Marketing consent — behaviour fixed by Decision 2

`consent_processing → consent_records.type = 'data_processing'`. Marketing consent
is **not transmitted at all** from the current form: the wording names no channel,
and `email_marketing` / `sms_marketing` / `phone_marketing` each assert one. The
ingest contract will carry `consent_marketing: false` and write no marketing
record. Request handling is never blocked on it.

Recorded for the later website/legal task: add reviewed, explicitly
channel-specific wording — an optional email-marketing checkbox — before any
marketing consent is exported.


---

# Phase 5A-P2 — platform database foundation

**Verdict: PARTIAL.** Migration 091 is complete, replay-verified and CI-green.
The authentication surface (verifier, capability, DTO, ingest route) is not
written. Nothing deployed, no credential minted.

```
branch     phase-5a-lead-ingest
start SHA  e6885ba6009c68ab14b7b57415cb554ba26c44d7
final SHA  142146d
```

## Migration 091 — `lead_acquisition_attributions`

22 columns. All provenance fields nullable: what the sender did not supply is not
invented. Every free-text field length-bounded by a CHECK.

| Object | Value |
|---|---|
| idempotency | `UNIQUE (tenant_id, source_system, external_correlation_id)` |
| composite FK | `(tenant_id, prospect_id) → prospects (tenant_id, id) ON DELETE CASCADE` |
| fingerprint | `payload_fingerprint` with `CHECK (~ '^[0-9a-f]{64}$')` |
| RLS | ENABLE **and** FORCE, 4 policies (UPDATE and DELETE closed with `USING (false)`) |
| privileges | `platform_app`: SELECT + INSERT only |
| indexes | unique identity, `(tenant_id, id)`, `(tenant_id, prospect_id)`, `(tenant_id, created_at DESC)` |

No index on `tenant_id` alone or `external_correlation_id` alone — both are
already leading columns of the above, and a redundant index is a write cost with
no read benefit.

Contains a REVOKE, so the 031 trap applies: added to `PRIV_MIGRATIONS` in
`scripts/restore.sh` (in sequence order — inserting it out of order failed the
manifest test), `restauration = oui` in `MANIFEST.tsv`, and both pinned lists
updated.

## Proven on a throwaway PostgreSQL 16

88 migrations applied; 091 landed with every object correct and its proof block
passing. With **asymmetric data** — 3 rows for one tenant, 1 for another —
`platform_app` under RLS with **no WHERE clause** saw 3 and 1 respectively, and 0
of the other tenant's rows. Duplicate identity refused by
`uq_lead_acq_attr_identite`. Cross-tenant attribution refused by
`lead_acq_attr_prospect_fk`. Throwaway container removed.

The 4 migrations that failed in that bare harness (002, 006b, 042, 044) are all
numbered below 091 and fail on seed/bootstrap state the harness lacks.

## A regression I introduced, and how it surfaced

The full suite showed 69 failures on my branch. Counting alone would have said
nothing — the branch point already had 68, from infrastructure suites needing
`docker`, `cosign` and network. Running the identical harness against a worktree
at 9931c5f and diffing the failure lists named exactly one new test:
`test_la_migration_maximale_reste_090`.

That test is a deliberate tripwire: a migration must not appear without someone
deciding it should. The fix was to move the pin and record the decision in the
docstring, as the five previous bumps did — not to work around it.

My first attempt at this comparison was worthless: I stashed to get a baseline,
but everything was already committed, so both runs measured the same tree.

## CI — actual results

Run `31746957673`, commit `142146d`, workflow **CI**:

```
test                       success     ← was failure before the pin fix
db-tests                   success
typecheck                  success
lint                       success
security                   success
build                      success
frontend                   success
frontend-browser-tests     success
actionlint                 success
compose-validate           success
linkedin-compliance        success
frontend-legacy-browser-diagnostic   in_progress
```

## Still to build

Service-account credential verifier, `prospect.ingest` capability, machine ingest
DTO, ingest application service (fingerprint canonicalisation, idempotency
execution, consent, attribution), the thin route, the §20 security matrix and the
secret-leak sentinel test.

The transaction model is already settled by the extraction: the ingest service
opens one `tenant_transaction`, and inside it writes the idempotency/attribution
row, calls `creer_prospect`, and records processing consent — one transaction,
committing coherently or not at all. Qualification stays after COMMIT.
