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
