# Owner inputs required before Mon Projet Solaire can launch

The site is built, deployed to staging and tested. Nothing below blocked
implementation — every missing value is a marked placeholder and the code paths
that consume them are exercised. What follows is only what genuinely cannot be
decided without you.

Nothing here asks you to invent marketing proof. If you have no certifications,
no testimonials and no install count, the site works without them and says so
plainly; inventing any of them is the one thing this system will not do.

---

## RESOLVED

### ✅ 1. Domain — `monprojetsolaire.be`

Owner decision, 2026-08-13. Configured as `domain` and as
`seo.canonical_origin: https://monprojetsolaire.be`. Canonicals are already
absolute and correct.

**Still outstanding on the owner's side:** the domain has no DNS delegation yet —
no NS, no SOA, no A/AAAA records. Routing is prepared but cannot be applied.
The exact records to create are in `docs/runbooks/MONPROJETSOLAIRE_DNS.md`.

### ✅ 2. Brand / site name — `Mon Projet Solaire`

Owner decision, 2026-08-13. `brand_name_is_placeholder` is now `false`. Header,
footer, page titles and the title-suffix template all use it.

---

## REQUIRED_FOR_LAUNCH

Nothing can go public until these exist.

### 1. Commercial contact destination

Where a captured lead should actually go — an inbox, a person, or a decision to
wait for the Prospect 360 adapter. Leads are accumulating in `PENDING_EXPORT` and
**nothing is reading them**.

*Currently: `contact.lead_destination_email: null`, destination `local`.*

### 2. Company / legal identity

Legal entity name, company number (BCE/KBO), registered address, and the data
controller for the privacy notice.

*Currently: all `null`. The footer says coordinates are to be confirmed rather
than showing an invented address.*

### 3. Privacy and terms wording

Either your own text, or explicit approval of text you have had reviewed. **No
legal text has been generated.** The pages render an explicit placeholder saying
so.

What the implementation verifiably does is documented at `/confidentialite` and can
be handed to whoever drafts the policy: local storage only, no third-party
transmission, no vendor analytics, consent recorded with version and timestamp,
IP hashed ephemerally for rate limiting and never stored.

*Then set `legal.reviewed: true` and `legal.consent_version` to the real version.*

### 4. Lead destination policy

Answers needed before the Prospect 360 adapter is written (full contract in
`docs/integrations/PROSPECT360_INGEST_CONTRACT.md`):

- the authenticated ingestion endpoint and how its credential is issued,
- deduplication: is a known email an update or a new prospect?
- does marketing consent map to an existing Prospect 360 field?
- how long a lead stays in this database after export.

### 5. Which pages may go live

One page is approved and staged, and is **not published**:

```
draft:   8526a70d-1803-409d-b13c-d607e288693b
content: 34e61730-10bd-41fc-a026-f48ec3a494e5  (version 1)
title:   Prix des Panneaux Solaires en Belgique
state:   APPROVED + STAGED, published_at = NULL
review:  http://localhost:3100/preview/fr/prix-panneaux-solaires-belgique
```

Which pages may go live remains your decision. Staging is not publication, and
`seolead content publish` refuses while the site is not indexable.

### 6. DNS delegation for monprojetsolaire.be

The zone is not published: no nameservers answer for it. Assign nameservers at the
registrar, then create the four records in
`docs/runbooks/MONPROJETSOLAIRE_DNS.md`. Until then the hostname cannot be routed
and no certificate can be issued.

### 7. Explicit permission to make the site public

Publication requires a Traefik route, DNS, and `allow_indexing: true`. **None of
those has been touched**, and none will be without your instruction.

---

## RECOMMENDED

Improves the site materially; launch is possible without them.

| Input | Effect |
|---|---|
| Logo (SVG or high-res PNG) | Replaces the "Mon Projet Solaire" text wordmark |
| Brand colours | The palette is a neutral practical green; two hex values retune it |
| Real differentiators | The "why us" story is currently absent rather than invented |
| Certifications (RESCERT, etc.) | Only if genuinely held — enables a trust block |
| Testimonials | Only if real and attributable |
| Commercial phone number | Enables the "Être rappelé" CTA end to end |
| Service area | Whether the site serves all of Belgium or specific regions |

---

## CAN_WAIT

| Input | Why it can wait |
|---|---|
| Dutch content | The architecture is NL-ready; no NL page is required to launch a French site. French keywords must not be machine-translated and assumed to carry the same intent. |
| GA4 or another analytics vendor | First-party events already cover the funnel |
| Additional pages (rentabilité, batterie, installation) | Cluster plan exists; each needs evidence before it is worth writing |
| A real savings/ROI calculator | Needs irradiation, roof geometry, consumption and tariff data; until then the tool qualifies rather than pretending to simulate |
| n8n automation | Contracts are documented; correctness does not depend on them |
| Additional price sources | See the source-diversity limitation in the Phase 4 report — worth doing, not a launch blocker |

---

## One thing worth your attention before you publish the price page

Every one of the five price figures on that page traces to a **single commercial
domain**. Each is correctly qualified and none is presented as a Belgian average,
so the page is honest — but it currently shows one company's view of the market.
Broadening the source set is the top content recommendation for Phase 5.
