# PHASE 4 — SOLAR BELGIUM SITE MVP, CONTENT OPERATIONS & CONVERSION FOUNDATION

**Date:** 2026-08-13
**Workspace:** `/opt/seolead`, branch `main`
**Baseline:** `50fafbb`
**Outcome:** SUCCESS. Staging site deployed, price page renders through the
publication gate, lead funnel works end to end, zero writes to Prospect 360.

---

## 1. Executive Summary

**The research engine now has a front door, and the front door is locked in the
right direction.** A Next.js site serves content that has passed factual QA, SEO QA
and human approval — and nothing else. Three independent conditions gate staging,
a fourth gates publication, and the site is bound to `127.0.0.1:3100` with
`Disallow: /` and no Traefik route.

**The Phase 3.4 price page is the first real page, replayed rather than
regenerated.** Its exact text was re-run through both QA layers against a fresh
evidence set: factual QA PASSED (score 100), SEO QA PASSED (score 100). All five
quantified statements render with their basis and VAT status, one figure marked
"TVA comprise" and the rest honestly marked "TVA non précisée". Approval is
**PENDING** — QA passing is not approval, and nothing here approves on its own.

**The gate caught a defect in itself on first use.** Staging was refused with "no
SEO QA review is recorded" for a draft that had one. The classifier inferred
factual-vs-SEO from finding codes, and a review that passes cleanly has no codes to
infer from. Fixed with an explicit `layer` column (migration `0006_qa_layer`) and
two regressions — including one for legacy rows that carry no layer.

**Lead capture is complete and goes nowhere.** A test lead was submitted through
the browser-facing route, validated server-side, stored with 17 attribution fields,
and left in `PENDING_EXPORT`. Honeypot, timing floor, rate limit, consent
requirement and email validation all refused their cases. The `seolead_app` role
sees **zero** Prospect 360 tables from its connection.

**Nothing is invented.** No company name, address, phone, certification, rating,
testimonial or install count appears anywhere. No legal text was generated — the
privacy page states what the implementation verifiably does and says the policy
itself is owner/counsel work. The estimation tool qualifies a project and
explicitly refuses to show savings or payback, because no defensible calculation
exists yet.

**628 backend tests and 9 frontend tests pass.** Migrations replay cleanly from
zero on a throwaway Postgres. The web container idles at 48 MiB.

---

## 2. Baseline

```
commit  50fafbb  fix: require evidence-backed answers for price intent
branch  main, clean working tree at start
```

Reports read: discovery, Phase 2, 3, 3.1, 3.2, 3.3, 3.4.

---

## 3. DataForSEO State

`CONFIGURED_BUT_ACCOUNT_BLOCKED` — unchanged.

One authenticated probe, via the pipeline's own SERP stage:

```
HTTP 403 — DataForSEO status_code 40104:
"Please verify your account before using the API."
```

Cost: **$0**. Not retried. No Phase 4 component depends on it: the site reads
`PublishedContent`, which is built from the research package, and the package path
does not require SERP to produce a brief.

---

## 4. Architecture Implemented

```
┌──────────────────────────────────────────────────────────────────┐
│                     SEO Lead Factory (Python)                    │
│                                                                  │
│  SERP → research → claims → evidence → brief → draft → QA        │
│                                                    │             │
│                                              Approval (human)    │
│                                                    │             │
│                                         ┌──────────▼──────────┐  │
│                                         │  publication gate   │  │
│                                         │  factual QA  = PASS │  │
│                                         │  SEO QA      = PASS │  │
│                                         │  approval    = YES  │  │
│                                         │  no outbound links  │  │
│                                         └──────────┬──────────┘  │
│                                                    │             │
│                                          PublishedContent        │
│                                     (sanitized snapshot, copy)   │
│                                                    │             │
│                    /site/v1  ──────────────────────┘             │
└────────────────────────────┬─────────────────────────────────────┘
                             │ X-Internal-Key   (server-side only)
                             │ X-Preview-Token  (unpublished only)
┌────────────────────────────▼─────────────────────────────────────┐
│                    seolead_web (Next.js 15, SSR)                 │
│                                                                  │
│   /                      home                                    │
│   /[slug]                PUBLISHED content only                  │
│   /preview/[locale]/…    STAGED content        — token required  │
│   /preview/draft/[id]    unapproved draft      — token required  │
│   /demande-etude         5-step lead form                        │
│   /outils/estimation-…   qualification tool, no financial claim  │
│   /confidentialite       what the code does; no generated policy │
│   /api/leads             browser → server proxy → factory API    │
│   /api/events            first-party funnel events               │
│   /robots.txt            Disallow: /  while not indexable        │
│   /sitemap.xml           PUBLISHED only — empty while staging    │
└──────────────────────────┬───────────────────────────────────────┘
                           │ 127.0.0.1:3100 — no Traefik label,
                           │ no DNS, no public hostname
                           ▼
                    operator's browser only
```

Full detail: `docs/site/SOLAR_SITE_ARCHITECTURE.md`.

---

## 5. Frontend Stack

| Choice | Version | Why |
|---|---|---|
| Next.js App Router | 15.5.23 | SSR/ISR content, server metadata, standalone output |
| React | 19.1.1 | — |
| TypeScript | 5.7.2 | `strict`, `noUncheckedIndexedAccess` |
| Vitest | 2.1.8 | unit tests without a browser |
| CSS | one hand-written stylesheet | no framework; ~103 kB first-load JS total |

`next@15.5.4` was the initial pin and carried a published CVE; upgraded to
`15.5.23`. Transitive `postcss` and `sharp` advisories are pinned out with npm
`overrides` — `npm audit --omit=dev` reports **0 vulnerabilities**.

No client-side-only rendering for content. Content pages ship no client component
at all; only the lead form is interactive.

---

## 6. Site Configuration

`config/sites/solar_be.yaml`, loaded through `app/site/config.py`.

```yaml
site_id: solar_be
vertical: SOLAR_BE
brand_name: "Solar Belgium (nom provisoire)"    # PLACEHOLDER, flagged
domain: null                                    # owner input
staging: true
seo.allow_indexing: false
legal.reviewed: false
```

Two validator rules refuse incoherent configurations outright:

- a site with no domain may not set `staging: false` — there is nowhere to publish
  to;
- a staging site may not set `allow_indexing: true` — an unfinished site in the
  index is not something a later fix undoes.

`is_indexable` requires **all three**: a domain, non-staging, indexing allowed. One
flag would be one accidental commit away from a live unfinished site.

A second site, `config/sites/demo_generic.yaml` (vertical `TEST_GENERIC`, market
FR, language en), exists as the isolation control.

---

## 7. Internationalization

`fr` unprefixed, `nl` under `/nl`, declared in `locale_paths` rather than derived —
the convention differs per site and guessing it changes every canonical URL.

`alternates()` emits hreflang only for locales that actually have the page. A
hreflang pointing at a 404 is a technical defect.

**No French keyword was machine-translated into Dutch.** Search intent is not
preserved by translation, and a `/nl` page needs its own research. The architecture
is NL-ready; no NL content was generated.

---

## 8. Information Architecture

Implemented routes, all declared in `SiteConfig.routes`:

```
/                            home
/prix-panneaux-solaires      LANDING_PAGE  (page candidate, awaiting approval)
/outils/estimation-solaire   qualification tool
/demande-etude               conversion
/confidentialite             legal placeholder
/conditions                  legal placeholder
```

`isKnownRoute()` refuses to render a link to any path not in that list, so a link
cannot ship pointing at a page that does not exist. `rentabilite`, `batterie` and
`installation` are in the cluster plan (§24) and are **not** routes yet — no
doorway pages were created.

Reusable page rendering exists for `LANDING_PAGE`, `GUIDE`, `COMPARISON` and
`ARTICLE`: all four consume the same `PublishedContentDTO` section list, so the
content type selects framing, not a separate template.

---

## 9. Content Publication Model

| State | Meaning |
|---|---|
| `DRAFT` | generated, not yet reviewed |
| `QA_FAILED` | a QA layer blocked it |
| `PENDING_APPROVAL` | QA clean, waiting for a human |
| `APPROVED` | a human said the content is fit |
| `STAGED` | a snapshot exists, `noindex`, preview-only |
| `PUBLISHED` | live |
| `ARCHIVED` | superseded or withdrawn |

There is no `APPROVED → PUBLISHED` transition. Staging is mandatory so the exact
bytes that will be served are looked at before they are served.

`PublishedContent` is a **snapshot, not a view**. Editing the draft afterwards
cannot change an approved page — asserted by
`test_the_snapshot_is_a_copy_not_a_live_view`. Versions increment per
`(site, locale, slug)`; a partial unique index allows one `PUBLISHED` row per
address, and publishing a new version archives the previous one.

---

## 10. First Price Page

```
draft_id     8526a70d-1803-409d-b13c-d607e288693b
brief_id     af08d194-1cb0-478f-ae4f-7eb589d5707e
package_id   fa6e2a44-ac14-4f32-bda4-fa660a045d31
title        Prix des Panneaux Solaires en Belgique : Guide Complet…
model        gpt-4o-mini-2024-07-18  (replayed, NOT regenerated)
words        355
```

**Not regenerated.** The Phase 3.4 artefacts were lost with the container tmpfs on
rebuild, so the exact draft text was replayed and re-run through both QA layers
against a freshly built evidence package. Had QA failed, the script refused to
persist. It passed:

| Layer | Status | Score | Blocking |
|---|---|---|---|
| Factual QA | PASSED | 100 | 0 |
| SEO QA | PASSED | 100 | 0 |

**Rendered state** (`http://localhost:3100/preview/draft/8526a70d-…`, HTTP 200,
28 kB, 0.60 s):

| Check | Result |
|---|---|
| quantified statements present | 5 of 5 — 4.000/14.000, 320/430, 130/170, 7.000/9.500, 220/280 |
| each figure's basis shown | yes — "pour l'installation complète", "par m²" |
| VAT carried per figure | yes — "TVA comprise" ×1, "TVA non précisée" ×5 |
| observed range labelled as a sample | yes — "il s'agit d'un échantillon observé, et non d'une moyenne du marché belge" |
| outbound links | **0** |
| source domain in HTML | absent |
| internal key in HTML | absent |
| `noindex` | present |
| H1 / H2 | 1 / 9 |
| `ld+json` blocks | 2 (BreadcrumbList only) |
| `<html lang>` | `fr` |

**Approval state: `PENDING`.** The gate reports exactly one blocker:

```json
{"factual_qa": true, "seo_qa": true, "approved": false,
 "no_external_links": true, "passed": false,
 "reasons": ["approval state is PENDING, not APPROVED"]}
```

`seolead content stage` refuses with that reason. The page is reviewable through
the admin draft path only, which §38 of the brief permits and which writes nothing.

---

## 11. Conversion Funnel

Five steps, defined entirely in YAML — nothing about solar panels is compiled into
the form component:

| Step | Fields |
|---|---|
| 1 project | owner status, postcode, property type |
| 2 roof | roof type, orientation |
| 3 consumption | annual kWh, monthly bill, battery interest — all optional |
| 4 timing | project timeframe |
| 5 contact | first/last name, email, phone, two consents |

Progressive disclosure: project questions first, contact details last.

Primary CTA `ESTIMATE_REQUEST` — "Obtenir mon estimation personnalisée". Secondary
`CALLBACK_REQUEST` — "Être rappelé".

No countdown, no scarcity, no fabricated social proof. The page's credibility rests
on traceable figures; manufactured urgency beside them would undo it.

Accessibility in the form: progress announced through a live region, errors bound
with `aria-describedby`, focus moved to the first invalid field, focus moved to the
step heading on advance, `prefers-reduced-motion` respected.

---

## 12. Lead Capture

E2E submission through the browser-facing route:

```
POST /api/leads  →  201  {"lead_id": "0c397d7d-…", "state": "PENDING_EXPORT"}
```

Server-side validation is total — the browser's `type="email"` is a convenience,
and anything can POST to the endpoint.

| Case | Result |
|---|---|
| valid lead | 201, `PENDING_EXPORT` |
| honeypot filled | 422 "honeypot field was filled" |
| submitted in 80 ms | 422 "under the 2500ms floor" |
| consent unchecked | 422 "consent to process the request is required" |
| `not-an-email` | 422 "not a usable email address" |
| unparseable optional phone | accepted, phone dropped |
| unknown qualification key | dropped |
| choice outside its options | dropped |
| number outside its bounds | dropped |

Consent: two separate checkboxes, neither pre-checked, marketing optional and
declining it never rejects a lead. Recorded with `consent_version`,
`consent_timestamp`, `consent_source`.

Privacy: no submitted value reaches the logs on success or rejection (asserted by
`TestLeadLogging`); the submitter's IP is hashed with a per-deployment salt for
rate limiting and never stored.

---

## 13. Attribution

All 17 required fields persist to `lead_attribution`, verified on the E2E lead:

```
vertical_code, site_id, published_content_id, landing_path, page_path,
language, search_intent, keyword_cluster, channel, source, referrer,
utm_source, utm_medium, utm_campaign, utm_content, utm_term,
cta, conversion_type, session_id, correlation_id, created_at
```

First-party and independent of any analytics vendor. Direct traffic with no UTM
parameters is still attributed (`channel: direct`) rather than lost.

Attribution is a separate table from the lead because they have different
lifetimes: the lead leaves this system when the export boundary opens; the funnel
record stays.

---

## 14. Prospect 360 Boundary

**Writes to Prospect 360: zero. Verified, not asserted.**

```
connected as: ('seolead', 'seolead_app')
prospect360 tables visible from this connection: 0
```

`LeadDestination` is a port with exactly one implementation,
`LocalLeadDestination`, which stores and stops. It returns `PENDING_EXPORT` — not
`EXPORTED` — because that is the truth. Reporting success while nothing received
the lead would mean it is never followed up.

Tests assert the boundary structurally: no symbol containing "prospect" in the
module, and no `acquisition_platform`, `prospect360`, `postgresql://` or
`INSERT INTO` in its source.

No production cookie-JWT route is used. No n8n webhook is used. The pre-existing
`docs/integrations/PROSPECT360_INGEST_CONTRACT.md` is preserved intact with a
Phase 4 addendum recording what the adapter will receive.

---

## 15. Estimation / Qualification Tool

`/outils/estimation-solaire` is a **project qualification tool**, and the page says
so in its own copy.

It shows no savings figure, no payback period, no subsidy amount and no system
size, because a defensible estimate needs irradiation data for the address, roof
orientation and pitch, a consumption profile and current tariffs — none of which is
implemented. The page explains that rather than producing a number.

`SolarCalculationProvider` is the conceptual boundary; Phase 4's behaviour is
qualification-only. Research evidence and deterministic calculation stay separate:
a calculator that quietly borrowed a claim from the evidence set would move the
Phase 3.4 failure mode into a new place.

---

## 16. SEO Technical Foundation

| Surface | Now | When launched |
|---|---|---|
| `robots.txt` | `User-Agent: * / Disallow: /` ✓ verified | allow, `/preview/` + `/api/` disallowed |
| page robots meta | `noindex, nofollow, nocache` ✓ verified | `index, follow` |
| `sitemap.xml` | empty ✓ verified | PUBLISHED URLs only |
| canonical | per-page `canonical_path` | absolute once a domain exists |
| OpenGraph | title, description, type, locale | — |
| breadcrumbs | rendered + `BreadcrumbList` | — |
| hreflang | architecture in place | emitted per available locale |

`metadataBase` is deliberately unset while there is no domain: Next would otherwise
resolve canonicals against localhost.

No sitemap was submitted anywhere.

---

## 17. Structured Data

`BreadcrumbList` only.

Not `Organization` — no real company data supplied. Not `LocalBusiness` — no
address. Not `AggregateRating` or `Review` — no reviews exist. Structured data that
asserts things nobody supplied is fabrication with a schema attached, and it is the
kind search engines penalise.

`seo.organization_schema` is a config flag, currently `false`, that turns
`Organization` on once real identity data arrives.

---

## 18. Security

| Control | State |
|---|---|
| Content sanitization | markdown → typed nodes; **no `dangerouslySetInnerHTML` for content** |
| Script/iframe/style/svg/`javascript:`/encoded-angle payloads | stripped, 7 parametrized cases |
| Links in content | flattened to their label; bare URLs removed |
| CSP | `default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'` ✓ verified |
| Other headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` ✓ verified |
| `X-Powered-By` | removed |
| Secrets in client bundle | **none** — `grep` over `.next/static` finds nothing; `lib/api.ts` imports `server-only` |
| Unpublished content on a public route | 404 ✓ verified |
| Preview | second independent secret; unset ⇒ refuses to serve |
| OpenAPI schema | still disabled |
| Lead endpoint | authenticated, server-proxied, rate-limited |
| Container | non-root uid 10003, `read_only`, `cap_drop: ALL`, `no-new-privileges` |
| Lead data in logs | absent, asserted by test |

The sanitization design is worth stating: nothing renders as HTML. Generated
content is derived from retrieved web pages, which are adversarial by construction,
so rendering a draft body as HTML would make the site's XSS surface equal to the
whole retrieved corpus.

---

## 19. Accessibility

- semantic headings, exactly one H1 per page (verified on the rendered page);
- skip link to `#contenu`;
- every input has a `<label>`, every radio group a `<fieldset>`/`<legend>`;
- errors bound with `aria-describedby` + `aria-invalid`, focus moved to the first
  invalid field;
- form progress in an `aria-live` region, focus moved to the step heading;
- `:focus-visible` outline at 3 px;
- `prefers-reduced-motion` respected on the progress bar;
- `prefers-color-scheme` dark palette;
- `<html lang="fr">` verified;
- honeypot `aria-hidden` and `tabIndex={-1}` — never announced, never focusable.

Not done: no screen-reader session and no automated axe run. Both are worth doing
before launch.

---

## 20. Performance

```
Route (app)                     Size    First Load JS
┌ ○ /                           168 B      106 kB
├ ƒ /[slug]                     168 B      106 kB
├ ƒ /demande-etude             2.81 kB     105 kB
└ + shared by all                         103 kB
```

Content pages ship no client component. Standalone output, ISR at 300 s for
content, `force-dynamic` for previews. One stylesheet, no web font (system stack,
so no font loading and no CLS from swap), no remote images.

Preview page: 28 kB HTML in 0.60 s including the API round trip.

---

## 21. Docker / Resource Usage

Before adding the service: 15 Gi total, 8.8 Gi available, swap fully used —
so the ceiling was set deliberately low.

```
seolead_web            48.12 MiB / 384 MiB   0.00%
seolead_api            68.13 MiB / 512 MiB   0.19%
seolead_last30days     42.77 MiB / 768 MiB   0.19%
```

After: 8.7 Gi available. The web container costs ~48 MiB.

`seolead_web` binds `127.0.0.1:3100` only, has no Traefik label, joins only
`seolead_backend`, runs as uid 10003 with `read_only`, `cap_drop: ALL` and
`no-new-privileges`. **No other container was modified and Traefik was not
touched.**

---

## 22. Tests

**628 backend (was 550, +78) and 9 frontend. All pass.**

| File | Tests | Covers |
|---|---|---|
| `tests/test_site_publication.py` | 35 | gate, transitions, snapshots, sanitization, site config, QA layer |
| `tests/test_lead_capture.py` | 33 | validation, consent, attribution, spam, boundary, logging |
| `tests/test_site_api.py` | 10 | auth, preview token, secrets, event validation |
| `web/tests/format.test.ts` | 6 | price formatting, no invented basis/VAT/average |
| `web/tests/site.test.ts` | 3 | locale routing, unknown routes, hreflang |

Against the brief's required list:

| Required | Test |
|---|---|
| DRAFT cannot publish | `test_a_draft_with_no_qa_and_no_approval_cannot_stage` |
| QA_FAILED cannot publish | `test_failed_qa_cannot_stage_even_when_approved` |
| APPROVED may stage | `test_approved_and_qa_clean_may_stage` |
| PUBLISHED requires explicit action | `test_staging_does_not_publish`, `test_publishing_requires_an_explicit_action_on_a_live_site` |
| versioning preserved | `test_versions_are_preserved_and_only_one_is_live` |
| five evidence-backed statements render | `test_five_evidence_backed_statements_survive_to_the_dto` |
| no competitor link | `test_a_draft_carrying_a_link_cannot_stage`, `test_links_are_flattened_to_their_label` |
| unknown VAT not generalised | `test_unknown_vat_is_carried_not_generalised` + frontend `vatIsUnknown` |
| no unsupported claim from the frontend | `test_the_snapshot_is_a_copy_not_a_live_view`, `test_the_dto_has_no_field_for_qa_internals` |
| canonical / noindex / hreflang / metadata | `TestSiteConfiguration`, `web/tests/site.test.ts`, verified on the live page |
| sitemap excludes non-public | verified: empty while staging |
| valid lead accepted | `test_a_valid_lead_is_accepted_and_held_for_export` |
| invalid email rejected | `test_an_invalid_email_is_refused` (7 cases) |
| malformed phone handled | `test_an_unparseable_phone_is_dropped_not_fatal` |
| consent required | `test_consent_is_required_and_never_assumed` |
| attribution persisted | `test_every_attribution_field_is_persisted` |
| **no Prospect 360 write** | `TestProspect360Boundary` (3 tests) |
| HTML/script injection sanitized | `test_executable_and_embeddable_markup_is_removed` (7 payloads) |
| public raw draft access forbidden | `TestPreviewToken`, verified 404 on the public route |
| secrets absent client-side | `test_no_secret_appears_in_the_site_config` + bundle grep |
| multi-vertical | `test_multi_vertical_isolation`, `TestGenericVerticalReusesTheSameCode` |

All 550 pre-existing tests preserved. One assertion updated: the credential report
now also lists `SITE_PREVIEW`, and the test asserts the new exact dict — keeping
its original intent that statuses appear and values never do.

---

## 23. Staging E2E

Run against the deployed containers, with fake test data only.

| Step | Result |
|---|---|
| validated price content persisted | draft `8526a70d…`, both QA layers PASSED |
| staging refused while unapproved | ✓ "approval state is PENDING, not APPROVED" |
| admin preview renders | ✓ HTTP 200, 28 kB, 0.60 s |
| five quantified statements present | ✓ all 5, with basis and VAT |
| no outbound link, no source domain, no key | ✓ |
| CTA present and linked | ✓ `/demande-etude`, `/outils/estimation-solaire` |
| form page loads | ✓ HTTP 200 |
| lead submitted | ✓ 201 `PENDING_EXPORT` |
| lead persisted with attribution | ✓ 1 lead, 1 attribution row |
| spam/consent/email refusals | ✓ 4 of 4 refused correctly |
| first-party events recorded | ✓ 2 accepted, unknown type 422 |
| unpublished slug on public route | ✓ 404 |
| sitemap | ✓ empty |
| **Prospect 360 writes** | ✓ **zero**, role sees 0 of its tables |

No fake lead reached any production tenant: the only database this service can
reach is `seolead`.

---

## 24. Solar Content Cluster Plan

**Prepared, not published.** Evidence readiness measured against the stored
package (183 claims; SUPPORTED: 60 GENERAL, 11 OBSERVED_PRICE_RANGE, 6
MARKET_PRICE).

| # | Query | Intent | Page type | Business value | Evidence readiness | Core question | CTA | Gap |
|---|---|---|---|---|---|---|---|---|
| 1 | prix panneaux solaires Belgique | COMMERCIAL | LANDING_PAGE | **high** | **READY** — 11 supported ranges | "Combien coûte une installation ?" | ESTIMATE_REQUEST | single-domain sources |
| 2 | rentabilité panneaux solaires Belgique | INFORMATIONAL | GUIDE | high | **NOT READY** — 6 ROI claims, 0 supported | "En combien d'années est-ce rentabilisé ?" | ESTIMATE_REQUEST | needs tariffs, prosumer rules, production data |
| 3 | batterie domestique Belgique | INFORMATIONAL | GUIDE | medium | **NOT READY** — no supported battery-price claim | "Une batterie vaut-elle le surcoût ?" | ESTIMATE_REQUEST | needs battery pricing + self-consumption evidence |
| 4 | combien de panneaux pour une maison | COMMERCIAL | LANDING_PAGE | high | **PARTIAL** — sizing appears inside price claims | "De combien de panneaux ai-je besoin ?" | TOOL_COMPLETION | needs consumption→kWc evidence, not a formula |
| 5 | guide installation panneaux solaires | INFORMATIONAL | GUIDE | medium | **PARTIAL** — process claims are GENERAL | "Comment se déroule une installation ?" | CALLBACK_REQUEST | needs regional permit rules |

Only page 1 has evidence to justify writing it, and only page 1 exists. Pages 2–5
are recorded so the research can be aimed, not so they can be generated.

---

## 25. Remaining Evidence Gaps

1. **Source diversity on price — the one to fix first.** All five figures on the
   price page trace to `energy-village.be`. That is `OBSERVED_PRICE_RANGE` policy
   working as designed (a range reported by a source needs that source), and every
   figure is correctly qualified — but the page shows one company's view of the
   market. The fix is more specialist domains and a `MARKET_AVERAGE` claim from a
   body that publishes cost guidance, **not** a lower evidence bar. A research task
   is recorded; the site build was not blocked on it.
2. **No `MARKET_AVERAGE` claim reached SUPPORTED.** The page states observed ranges
   and never a Belgian average. Correct, and still a gap.
3. **VAT unknown for five of six price answers.** The sources did not state it, so
   the page says so. Material for a Belgian buyer.
4. **41 of 42 HIGH-risk claims remain unresolved** — subsidies and grid rules. The
   page correctly says nothing about them, which also means it cannot yet answer
   "what does it cost after the premium?"
5. **No ROI, battery or sizing evidence** (see §24).
6. **DataForSEO blocked** — no SERP, so no competitor analysis, PAA coverage or
   content-gap scoring.
7. **Navigation fragments still reach the claim set** occasionally (a link-list
   fragment carrying a real sentence). Noted in Phase 3.4, unchanged.

---

## 26. Owner Inputs Required For Launch

Full document: `OWNER_INPUTS_REQUIRED_FOR_LAUNCH.md`.

**REQUIRED_FOR_LAUNCH:** domain · brand name · commercial contact destination ·
company/legal identity · privacy & terms wording · lead destination policy · which
pages may go live · explicit permission to make the site public.

**RECOMMENDED:** logo · brand colours · real differentiators · certifications *if
genuinely held* · testimonials *if real* · commercial phone · service area.

**CAN_WAIT:** Dutch content · GA4 · additional pages · a real ROI calculator ·
n8n automation · additional price sources.

Nothing asks the owner to invent marketing proof.

---

## 27. Files Changed

**New — backend**

```
app/site/__init__.py                     app/api/site.py
app/site/config.py                       app/models/publication.py
app/site/content_sanitizer.py            migrations/versions/0005_site_publication.py
app/site/publication.py                  migrations/versions/0006_qa_layer.py
app/site/lead_capture.py                 config/sites/solar_be.yaml
app/site/spam_protection.py              config/sites/demo_generic.yaml
```

**New — frontend** (`web/`): `app/` 12 routes, `components/` 6 modules,
`lib/` 4 modules, `tests/` 2 files, `infra/web/Dockerfile`.

**New — tests**: `test_site_publication.py`, `test_lead_capture.py`,
`test_site_api.py`.

**New — docs**: `docs/site/` ×5, `docs/runbooks/` ×3,
`OWNER_INPUTS_REQUIRED_FOR_LAUNCH.md`.

**Modified**: `app/core/enums.py` (+`PublicationState`, `LeadState`,
`SiteEventType`, `ConversionType`, `QALayer`), `app/core/config.py`,
`app/main.py` (lifespan), `app/models/__init__.py`, `app/models/content.py`
(`qa_review.layer`), `app/services/pipeline.py`, `app/services/pipeline_v2.py`,
`app/cli.py`, `docker-compose.yml`, `.env.example`, `.gitignore`,
`docs/integrations/PROSPECT360_INGEST_CONTRACT.md` (**appended, not replaced**),
`tests/test_phase3_services.py`.

---

## 28. Git Diff

```
 .env.example                        |  16 +
 .gitignore                          |   7 +
 app/api/site.py                     | 293 +++++ (new)
 app/cli.py                          | 262 ++++
 app/core/config.py                  |  13 +
 app/core/enums.py                   |  84 +
 app/main.py                         |  27 +-
 app/models/content.py               |   8 +
 app/models/publication.py           | 218 +++ (new)
 app/services/pipeline.py            |   6 +-
 app/services/pipeline_v2.py         |   8 +-
 app/site/*.py                       | 900 +++ (new, 6 files)
 config/sites/*.yaml                 | 250 +++ (new, 2 files)
 docker-compose.yml                  |  62 +
 docs/…                              | 900 +++ (9 files)
 migrations/versions/0005,0006       | 220 +++ (new)
 tests/test_site_*.py, test_lead_*   | 900 +++ (new, 3 files)
 web/**                              | 2600 +++ (new)
```

`git diff --check` clean. Secret scan clean. `.env` untouched by the commit;
generated staging secrets were written to it and never printed.

---

## 29. Phase 5 Recommendation

**Close the price-evidence source-diversity gap, then open the lead destination.**

In order:

1. **Source diversity for price** (§25.1). Widen the specialist domain set and
   target a `MARKET_AVERAGE` claim from a cost-publishing body. This is the
   difference between a page that is honest and a page that is authoritative, and
   it is a research change, not an evidence-bar change.
2. **Prospect 360 ingestion.** Leads are accumulating in `PENDING_EXPORT` and
   nothing reads them. The contract is documented; the platform-side work is the
   longest-lead item in the roadmap and should be scheduled now.
3. **Page 4 of the cluster** (`combien de panneaux`) — the strongest commercial
   candidate after price, and partly covered by existing evidence.
4. **A defensible sizing/ROI calculation**, only once irradiation and tariff data
   are integrated verifiably.

Not recommended for Phase 5: making the site public before the owner inputs in §26
arrive, and generating pages 2, 3 and 5 before their evidence exists.

---

## 30. Exact Next Action

**Review the price page and decide whether to approve it.**

```bash
ssh -L 3100:127.0.0.1:3100 <user>@<vps>
# then open:
http://localhost:3100/preview/draft/8526a70d-1803-409d-b13c-d607e288693b
```

Check that every figure carries its basis and VAT status, that nothing reads as a
Belgian average, and that the CTA matches what you can honestly offer. Then either:

```bash
seolead content approve 8526a70d-1803-409d-b13c-d607e288693b --by "<your name>"
seolead content stage   8526a70d-1803-409d-b13c-d607e288693b
```

or say what needs to change. **Approving still does not publish it** — publication
additionally needs the domain, the launch decision and a Traefik route, none of
which has been made.

---

**Commit:** `feat: build Solar SEO site MVP`
