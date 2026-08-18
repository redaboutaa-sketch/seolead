# Technical plan — SEO Lead Factory / Mon Projet Solaire

Identifiers here are namespaced `SL-Tn`, for the reason recorded at the top of
`doc/prd.md`: the platform repository's `doc/plan.md` owns `T1` … `T18`, this
work may not modify it, and an unnamespaced `T1` in this repository would be
indistinguishable from the platform's.

`SL-T1` is the first tracer in this plan.

---

## TRACER SL-T1 — The homepage looks like a service, and still captures the same lead

**Owning story:** `US-SL-01` in `doc/prd.md`.

### The one sentence

A visitor arrives at `monprojetsolaire.be`, is met by a composed full-width hero
with a real solar visual and one dominant call to action, understands within a
screen what the service does and what will be asked of them, and enters *the
existing five-step qualification form, byte-for-byte unchanged in what it sends*.

### Why it is one tracer and not several

The slices below share a single design system. Shipping the hero against the old
token set, or new tokens against the old sections, produces a page that is
internally inconsistent — which is the defect being fixed, reintroduced in a new
form. They land together or not at all.

The form is the natural seam. Everything above `/demande-etude` is presentation;
`/demande-etude` and everything behind it is contract. The tracer stops at that
seam and does not cross it.

### Implementation slices

**SL-T1.1 — Design tokens.**
Replace the flat token set in `web/app/globals.css` with a system: a modular
typographic scale, a spacing scale, container widths, radii, a two-level shadow
set, and a palette refined from the existing accent rather than replaced (see
`docs/site/DESIGN_SYSTEM.md` for the authority question). Dark-mode variants for
every token, because the current file already has them and dropping them would be
a regression. No CSS framework: the site is served to a visitor on 4G and every
kilobyte is theirs.

**SL-T1.2 — Hero.**
A new full-width hero section: headline, one supporting sentence, primary CTA,
secondary CTA, and a vector solar-home composition. Two-column at ≥ 62rem,
stacked at smaller widths with the visual reduced to a band. This slice gets
disproportionate attention; it is the whole first impression.

**SL-T1.3 — Reusable section components.**
`components/home/` — `Hero`, `Assurances`, `Benefits`, `Process`, `Faq`,
`FinalCta`. `app/page.tsx` becomes composition, not markup. Each takes the
`SiteConfigDTO` and reads CTA labels and routes from it, so nothing hard-codes a
label the configuration owns.

**SL-T1.4 — Imagery.**
Author-drawn vector art. The hero composition is a component
(`components/home/HeroVisual.tsx`) so it inlines and costs no round trip; the
favicon ships as `web/public/favicon.svg`. Rationale, and the exact photography
requirements for the owner to supply later, in `docs/site/DESIGN_SYSTEM.md`.
Vector because: the CSP is `img-src 'self' data:` so nothing remote loads
anyway; a vector is a few kB against a photograph's hundreds; it cannot be a
stock cliché; and it carries no licence risk. No competitor imagery is copied,
and no photograph is invented.

**SL-T1.5 — Header, footer, navigation.**
Sticky translucent header, a mobile navigation that is legible at 390 px, and a
three-column footer that keeps the legal links prominent. The footer's conditional
contact block — real details when the owner supplied them, an honest note when not
— is preserved exactly.

**SL-T1.6 — Form and CTA surfaces.**
Restyle `LeadForm`'s chrome: step indicator, choice tiles, inputs, consent block,
actions. **No change to steps, fields, validation, payload, events, honeypot or
timing floor.** `/demande-etude` and `/outils/estimation-solaire` get a composed
page shell around the unchanged form.

One behavioural fix landed here, found by driving the flow during QA rather than
by reading it. Advancing from step 4 to step 5 submitted the form: React reuses
one DOM button for "Continuer" and for submit, and flushes a discrete click
synchronously, so `next()` ran, the re-render retyped that same element to
`type="submit"`, and the browser applied the submit default action to the click.
The visitor arrived at the contact step already showing two red errors for
fields they had not been offered, and a spurious `FORM_SUBMITTED` event was
recorded. `submit()` now refuses any step but the last. No field, rule or
payload changes — it only declines a submission the visitor never asked for.

**SL-T1.7 — Content and legal pages.**
`[slug]`, `/confidentialite`, `/conditions`, `not-found` inherit the new system
through shared classes. The privacy text itself is owner-approved and is not
touched — only the container it renders in.

**SL-T1.8 — Accessibility.**
Semantic landmarks, one `h1` per page, focus ring on the new surfaces, touch
targets ≥ 44 px, `prefers-reduced-motion` honoured, decorative SVG marked
`aria-hidden`, meaningful `alt` on the hero visual.

**SL-T1.9 — Performance.**
System font stack retained (no web font request). No client component added to
the homepage — it stays a server component with zero interactive JavaScript. The
hero SVG is inlined so it costs no round trip and cannot delay LCP. Animation is
limited to CSS transitions on hover and one entrance transition, both disabled
under `prefers-reduced-motion`.

**SL-T1.10 — Tests.**
- Structural regression (`web/tests/homepage.test.tsx`-equivalent, run headless
  against the built app): the primary CTA exists and points at the conversion
  route; the privacy link exists in the footer; exactly one `h1`; the process
  steps match the configured form steps.
- Layout regression: no horizontal overflow at 390 / 1024 / 1440, and no tap
  target under 44 px at 390.
- Consent regression: the existing server-side tests already fail if required
  consent is dropped — that is the layer which actually accepts or rejects a
  lead, so it is the one worth asserting. The browser suite additionally drives
  the five steps with every API call aborted and asserts both checkboxes render
  unchecked, that no validation error is showing on arrival, and that
  `/api/leads` was never reached.
- The full existing suites — `web` (vitest) and the Python suite — must stay
  green.

### What this tracer must leave untouched

`app/api/leads/route.ts`, `app/api/events/route.ts`, `lib/api.ts`, `lib/types.ts`,
`middleware.ts`, `next.config.ts`, `app/robots.ts`, `app/sitemap.ts`,
`config/sites/solar_be.yaml`, everything under `app/site/` in the Python service,
`infra/traefik/docker-compose.public.yml`, `/opt/seolead/.env`, and the whole of
`redaboutaa-sketch/techformanord`.

`lib/types.ts` is listed deliberately. If the redesign needs a field the DTO does
not have, the correct answer is that the redesign does not get to show it — the
type having no field for something is the mechanism that stops a component
rendering it by accident.

### Definition of done

The DoD in the mission brief, verbatim, plus: `docker compose build seolead_web`
succeeds, and the production acceptance checks in
`docs/runbooks/MONPROJETSOLAIRE_DEPLOYMENT.md` §3 pass unchanged after deployment
— in particular all three indexing refusals.


---

## Findings recorded during SL-T1, not fixed by it

**The CSP nonce does not reach statically prerendered routes.** `middleware.ts`
mints a nonce per request, but `/`, `/confidentialite`, `/conditions` and the 404
are prerendered, so their HTML carries a build-time nonce that no longer matches
the response header. Every script on those pages is refused: production's
homepage shows 16 CSP violations today, on the build that predates this work.

It is invisible because those pages have no client component — nothing hydrates,
so nothing can blank. `/demande-etude` and `/outils/estimation-solaire` are
`force-dynamic`, their nonces match, and the lead form hydrates correctly (0
violations, verified).

This redesign is safe under that condition and deliberately keeps it that way:
the homepage stays a server component, the FAQ uses native `<details>`, and
there is no scroll listener anywhere. But the defect is a trap — the first
client component added to a static page will reproduce the blank-page bug that
`tests/hydration.browser.test.ts` exists to catch, and that test only covers a
dynamic route.

Not fixed here because the fix belongs to `middleware.ts` or `next.config.ts`,
both of which SL-T1 is explicitly forbidden to touch, and because it is a
security-policy change rather than a presentation one. It deserves its own
tracer.

**Resolved by `TRACER SL-T2` below.**


---

## TRACER SL-T2 — Every page can satisfy the policy that protects it

**Owning requirement:** `NFR-SEC-CSP` in `doc/prd.md`. No product story is
created: nobody needs to ask for a security policy that works, and inventing a
`US-SL-nn` for a defect would put a bug in the product backlog.

### The defect

`middleware.ts` mints a CSP nonce per request. Next stamps that nonce onto the
scripts it generates by reading the CSP header off the **request**, during
server-side rendering. Four routes were statically prerendered — `/`,
`/confidentialite`, `/conditions` and the 404 — and a prerendered page is built
when no request exists. Their HTML therefore carried either no nonce at all
(fresh build) or a frozen one belonging to whichever request last populated the
route cache (after an ISR revalidation), while the response header carried a
fresh nonce every time. Every script on those pages was refused.

Measured on production before the fix: **26 CSP violations on `/`, 16 on
`/confidentialite`, 15 on a reproduction route.** The pages still painted only
because none of them shipped a Client Component — nothing hydrated, so nothing
could blank.

### Root cause

`STATIC_RENDERING_INCOMPATIBLE_WITH_REQUEST_NONCE`.

Not "the nonce is missing" — that is the symptom. The cause is an architecture
contradiction: a nonce must be unpredictable per response, and a prerendered
response is fixed at build. Next's documentation states the constraint directly:
*"To use a nonce, your page must be dynamically rendered ... Static pages are
generated at build time, when no request or response headers exist—so no nonce
can be injected."*

Proven by discrimination, not inference:

| Test | Result |
|---|---|
| Does the header nonce vary per request? | Yes, every request |
| Does the prerendered body nonce vary? | No — constant across requests, or absent on a fresh build |
| Does forcing dynamic rendering fix it, changing nothing else? | **Yes — 15 violations → 0, `hydrated: no` → `hydrated: yes`** |
| Does request-header propagation work on dynamic routes? | Yes — header and body nonce identical, 0 violations |
| Is `'strict-dynamic'` to blame? | No. Removing it *worsened* the failure: 26 → 19 violations but the page then **blanked** (`__next_f` empty, 2 page errors) — the original bug this CSP was written to fix |

### Options evaluated

- **A — dynamic rendering everywhere.** Proven to work. Costs the full route
  cache on four low-traffic noindex pages. **Selected.**
- **B — static-safe CSP (hashes / experimental `sri`).** Rejected on evidence,
  not taste: Next's SRI support is experimental, App-Router-only, and documented
  as unable to handle *dynamically generated scripts* — which is exactly what the
  inline RSC payload (`self.__next_f.push(...)`) is. Its content changes with page
  data, so no build-time hash set can cover an ISR re-render.
- **C — hybrid: static routes get a nonce-free policy.** Rejected. The only
  non-nonce directive that admits the inline RSC payload is `'unsafe-inline'`,
  which `NFR-SEC-CSP` (2) forbids — and it would apply precisely to the legal
  pages.
- **D — propagation fix.** Falsified. Propagation demonstrably works; dynamic
  routes were already correct.

### The fix

`await connection()` in `app/layout.tsx`. Three deliberate choices:

- **At the root, not per page.** A per-page opt-in is a rule someone has to
  remember; a route added next month would be static by default and would fail
  silently, with HTTP 200 and complete HTML. At the root it cannot be forgotten.
- **`connection()` rather than `dynamic = "force-dynamic"`.** The latter also
  flips the default fetch cache to `no-store`, putting the SEO Lead Factory API
  on the path of every request. Verified: after the fix, 12 homepage requests
  produced **0** API calls — the fetch-level data cache is intact.
- **Nothing in the policy changed.** Same directives, same nonce, same
  `'strict-dynamic'`, no `'unsafe-inline'`, no `'unsafe-eval'`.

One comment in `middleware.ts` was also corrected. It claimed that setting the
CSP only on the response "would leave them unstamped and reproduce the original
bug". Measured on Next 15.5.23: removing `x-nonce`, or the request CSP header, or
both, changes nothing — only the response header is load-bearing. The lines stay
(they are the documented pattern and guard against a version change), but a false
claim in security-critical code is worse than none.

### Security invariant

Every page must satisfy its enforced CSP with zero browser violations caused by
framework-required scripts — **without** any directive being relaxed. Asserted by
`web/tests/csp.browser.test.ts`, which fails if `script-src` gains
`'unsafe-inline'`, `'unsafe-eval'` or a wildcard, and which proves enforcement by
splicing an un-nonced inline script into the served HTML and requiring the
browser to refuse it.

### Regression matrix

| Mutation | Bites |
|---|---|
| Remove `await connection()` | **Yes** — 9 failures across render-mode and CSP suites |
| Add `'unsafe-inline'` to `script-src` | **Yes** |
| Remove the CSP response header | **Yes** — 9 failures |
| Remove request-header propagation | **No, and correctly so** — inert on this Next version; recorded above rather than papered over |

`web/tests/render-mode.test.ts` catches the cause one layer earlier and with no
server running: it asserts the build prerenders nothing, by reading
`prerender-manifest.json` and looking for emitted `.html`.

### Cost

| | Before | After |
|---|---|---|
| `/` median TTFB (loopback) | 9.3 ms | 21.6 ms |
| `/confidentialite` | 5.9 ms | 13.7 ms |
| `/conditions` | 5.3 ms | 12.3 ms |
| API calls per 12 homepage requests | 0 | 0 |
| `/` HTML, gzipped | 13.9 kB | 19.8 kB |

The TTFB change is ~7–12 ms of server render on pages whose network round trip
from Belgium is several times that. The transfer change is real and worth naming:
Next stores cached routes pre-compressed at a high level and compresses streamed
dynamic responses at a faster, weaker one — the same HTML re-gzipped at `-9` is
13.7 kB. Recovering it means disabling Next's compression and letting Traefik
compress instead, which is a second variable and does not belong in a security
fix. Recorded as a follow-up, not smuggled in.

**Done by `TRACER SL-T3` below — and the follow-up turned out to be worth more
than this note estimated: the real figure was 19.7 kB → 10.6 kB, not 19.7 → 13.7,
because Traefik serves brotli rather than a better gzip.**

### Rollback

`docker tag seolead/web:rollback-pre-csp-fix seolead/web:0.1.0 && docker compose
up -d --no-deps seolead_web`. Reverting restores the pre-fix behaviour, which is
the current production state: broken CSP on four routes, no visible symptom.

### Production acceptance

apex / www / legal / preview unchanged; all three noindex mechanisms unchanged;
zero CSP violations in a real browser at 1440, 1024 and 390; a Client Component
hydrates; an injected inline script is still refused.


---

## TRACER SL-T3 — The edge compresses, because it compresses better

**Owning requirement:** `NFR-PERF-WIRE` in `doc/prd.md`.

### The defect

Two compressors sat in the request path, and the weaker one won every
negotiation.

Next's built-in compressor speaks **only gzip**. Traefik 3.7, which fronts every
public request, speaks **brotli and zstd** and prefers brotli. A browser offers
`gzip, deflate, br, zstd` in one header. Next saw `gzip`, compressed, and Traefik
could not improve on a response that already carried a `Content-Encoding`. So the
visitor received the worst algorithm available, on every request.

`SL-T2` noticed the symptom and mis-sized it, estimating a 5.8 kB recovery from
matching gzip's old compression level. The real figure is larger, and for a
different reason.

### Measured, on production

| Accept-Encoding | Encoding served | Homepage document |
|---|---|---|
| `gzip, deflate, br, zstd` (a real browser) | gzip | **19 737 B** |
| `br, gzip` | gzip | 19 746 B |
| `zstd, gzip` | gzip | 19 690 B |
| `br` alone | br | **10 624 B** |
| `zstd` alone | zstd | 12 303 B |
| `br, zstd` | br | 10 624 B |
| `identity` | none | 67 594 B |

The pattern is unambiguous: **whenever `gzip` appears in the request, gzip is
what comes back**, whatever else was on offer.

### Root cause

`DOUBLE_COMPRESSION_LAYER_CONFLICT`.

Not "Traefik is misconfigured" and not "Next compresses badly" — both components
behave exactly as documented. The defect is in the composition: an inner
compressor with a narrower algorithm set answers first, and content negotiation
has no mechanism to reconsider.

Discriminated rather than assumed:

| Test | Result |
|---|---|
| Does the backend alone emit brotli? | No — `Accept-Encoding: br` against `127.0.0.1:3100` returns 67 594 B, identity. Next is gzip-only |
| Does Traefik compress when the backend does not? | Yes — the same request through the edge returns 10 624 B of brotli |
| Which does Traefik prefer? | brotli — `br, zstd` and `zstd, br` both return br |
| Is the gap the compression *level* or the *algorithm*? | Algorithm. The same HTML at `gzip -9` is 13 651 B; brotli reaches 10 624 B |

### Why the gap is widest on the document

Next stores cached routes pre-compressed at a high level and compresses streamed
dynamic responses at a fast, weak one. Since `SL-T2` every route is dynamic, so
every document takes the weak path. Static assets were never as badly affected —
CSS 4 711 → 4 395 B, a chunk 1 672 → 1 570 B — because they are not streamed.

The saving is therefore concentrated exactly where it matters: the HTML document
on the critical path.

### The fix

1. `compress: false` in `next.config.ts`. One line. The app stops answering the
   negotiation and Traefik gets to choose.
2. `monprojetsolaire-compress` added to the **preview** router's middleware chain
   in `infra/traefik/docker-compose.public.yml`.

Point 2 is not incidental. That router carried `preview-auth` and
`security-headers` and no compression — it was covered only by Next's gzip. Left
alone, this change would have silently started serving ~55 kB of raw HTML to the
one person the preview route exists for. Found by reading the chain, not by
waiting for someone to notice.

Traefik's encoding order is left at its default. It already prefers brotli, which
is the smallest of the three here; forcing an order would be a second decision
with no measured benefit.

### What this costs

Anything reaching the app **without** passing through Traefik is now served
uncompressed. That is the loopback `127.0.0.1:3100`, which exists for operator
diagnostics and carries no bandwidth cost — and raw HTML is easier to read in
`curl` anyway.

### Regression matrix

| Mutation | Bites |
|---|---|
| Remove `compress: false` | Yes — the config assertion, and the wire test sees gzip instead of br |
| Remove compress from the preview router | Yes — the router-chain assertion |
| Remove compress from the apex router | Yes — same assertion, and every wire test |
| Serve a document route uncompressed | Yes — "compresses every document route" |

The suite splits by vantage point. Source assertions run anywhere. Wire
assertions require Traefik and run only against an `https://` base URL; against
the loopback backend the opposite is asserted — that the app compresses nothing —
so neither environment silently skips its half of the contract.

### Rollback

`docker tag seolead/web:rollback-pre-compress seolead/web:0.1.0 && docker compose
up -d --no-deps seolead_web`. Reverting restores Next's gzip; the preview router
keeps the extra middleware harmlessly, since Traefik will not re-compress an
already-encoded response.

### Production acceptance

A browser-like `Accept-Encoding` must return `content-encoding: br` on every
document route; the homepage must be under 14 kB on the wire; `/preview` must be
compressed behind its auth; and the three indexing refusals must be untouched.
