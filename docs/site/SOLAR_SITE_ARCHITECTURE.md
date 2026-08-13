# Solar Belgium site — architecture

## The boundary this design exists to enforce

The research engine produces claims. The site renders pages. Between them sits a
publication gate that only approved, QA-passed content crosses, and a DTO that
carries nothing else — no source URLs, no claim identifiers, no QA notes, no
provider metadata, no cost data.

That boundary is not a convention. The frontend has no database credentials, no
knowledge of the research schema, and no type with a field for anything it must
not render.

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
│                                       (sanitized snapshot)       │
│                                                    │             │
│                    /site/v1  ──────────────────────┘             │
└────────────────────────────┬─────────────────────────────────────┘
                             │ X-Internal-Key (server-side only)
                             │ X-Preview-Token (unpublished only)
┌────────────────────────────▼─────────────────────────────────────┐
│                    seolead_web (Next.js, SSR)                    │
│                                                                  │
│   /                      home                                    │
│   /[slug]                PUBLISHED content only                  │
│   /preview/[locale]/…    STAGED content, token required          │
│   /preview/draft/[id]    unapproved draft, owner review only     │
│   /demande-etude         multi-step lead form                    │
│   /outils/estimation-…   qualification tool (no financial claim) │
│   /api/leads             browser → server proxy → factory API    │
│   /api/events            first-party funnel events               │
│   /robots.txt            Disallow: / while not indexable         │
│   /sitemap.xml           PUBLISHED only, empty while staging     │
└──────────────────────────┬───────────────────────────────────────┘
                           │ 127.0.0.1:3100, no Traefik label
                           ▼
                    operator's browser only
```

## Layers

| Layer | Location | Knows about |
|---|---|---|
| Vertical profile | `config/verticals/*.yaml` | what may be claimed, evidence policy |
| Site profile | `config/sites/*.yaml` | brand, domain, locales, funnel, legal |
| Publication | `app/site/publication.py` | the gate, snapshots, the DTO |
| Sanitization | `app/site/content_sanitizer.py` | markdown → typed nodes, no HTML |
| Lead capture | `app/site/lead_capture.py` | validation, attribution, destination |
| Site API | `app/api/site.py` | the only surface the frontend reads |
| Frontend | `web/` | rendering, conversion, SEO metadata |

A vertical says what is true. A site says how it is presented. Mixing them would
put brand copy inside the evidence policy, which is how a marketing decision
becomes a factual claim.

## Multi-vertical reuse

Nothing in `web/` mentions solar panels. Page structure comes from the DTO, form
structure from `SiteConfig.conversion`, navigation from `SiteConfig.routes`.
`config/sites/demo_generic.yaml` is a second site over a different vertical in a
different language, and it exists so that any Solar assumption leaking into the
generic infrastructure fails a test rather than shipping.

Adding `AI_TRAINING_FR` is: one vertical YAML, one site YAML, one `Site` row.

## Why Next.js, server-rendered

Content pages must be crawlable without executing JavaScript, carry
server-rendered metadata and canonicals, and be cheap to serve. A client-rendered
SPA fails the first requirement outright. `output: "standalone"` keeps the runtime
image small on a host that runs a dozen other containers.

## What is deliberately absent

- No CMS. The database is already the authoritative content workflow store, and a
  second source of truth for page content would let a page drift from the draft a
  human approved.
- No Prospect 360 adapter. The interface exists; there is no implementation, and
  the tests assert there is none.
- No analytics vendor. First-party events only.
- No `Organization` or `LocalBusiness` structured data. Nobody supplied a real
  company identity, and schema.org is not a place to invent one.
