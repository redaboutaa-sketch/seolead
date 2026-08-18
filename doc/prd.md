# Product requirements — SEO Lead Factory / Mon Projet Solaire

## Why this file exists, and how its identifiers are numbered

`docs/integrations/PROSPECT360_INGEST_CONTRACT.md` cites `US-19`, `US-20` and
`US-21` in `doc/prd.md`. Those references point at the **platform** repository
(`redaboutaa-sketch/techformanord`), whose `doc/prd.md` holds `US-01` … `US-24`
and whose `doc/plan.md` holds `T1` … `T18`. They describe Prospect 360 ingestion,
not this repository's website.

Until now `seolead` had no product backlog of its own: its record was a series of
phase reports. That is why a story about the **monprojetsolaire.be front end** had
no owning identifier to reuse.

Two identifier schemes were possible and one is wrong:

- Continuing the platform's sequence (`US-25`) would put a seolead story in a file
  this work is explicitly forbidden to modify, and would race the parallel Phase 5A
  work that is currently claiming numbers in that same sequence.
- Numbering a fresh seolead backlog `US-01` would collide, on sight, with the
  platform's `US-01` in a repository that already cross-references the platform's
  numbers.

So this backlog is **namespaced**: `US-SL-nn` here, `TRACER SL-Tn` in
`doc/plan.md`. `SL` is `seolead`. A reader who meets `US-SL-01` and `US-19` in the
same repository can tell which system owns which without opening either file, and
neither sequence can ever be advanced by accident from the other side.

`US-SL-01` is the first story in this backlog.

---

## US-SL-01 — A Belgian homeowner trusts the site enough to start qualifying

**As** a Belgian homeowner considering solar panels,
**I want** to understand within seconds what this site offers me and to feel it is
run by people who know what they are doing,
**so that** I am willing to answer questions about my roof instead of leaving.

### The problem being solved

The site works. Every route resolves, the form captures, consent is recorded, the
legal pages are owner-approved. What it does not do is *look* like somewhere a
person would hand over their address.

The current homepage is an unstyled document: a heading, a paragraph, two buttons,
three bordered boxes, a footer. There is no imagery, no visual hierarchy beyond
font size, no composition. At 1440 px the entire page occupies the left 60 % of
the viewport and the right 40 % is empty. A visitor's first five seconds return
"this is a text file about solar panels", not "this is a service I could use".

That gap is a conversion problem and a trust problem, and it is the only thing
between the current build and a site the owner can send traffic to.

### What must NOT change

This story is presentation-only. It is not permitted to alter:

- the lead-capture data contract (`LeadPayload`, `/api/leads`, the server-side
  validation in `app/site/lead_capture.py`),
- the form's step and field definitions, which live in
  `config/sites/solar_be.yaml` and nowhere else,
- consent semantics: two separate checkboxes, processing required, marketing
  optional and never a precondition, neither pre-checked, `consent_version`
  recorded per lead,
- the legal pages or their owner-approved wording,
- the indexing gate: `robots.txt`, `X-Robots-Tag`, the `meta robots` tag, and
  sitemap behaviour all stay exactly as they are. **This story does not make the
  site indexable.**
- the exporter, the Prospect 360 integration contract, webhook security,
  routing, or the preview / basic-auth behaviour.

### What must NOT be invented

The site's entire credibility rests on the rule that it publishes only what a
source actually said. A redesign that decorates that rule with fabricated proof
destroys the thing it is decorating. No customer reviews, no certification
claims, no partner logos, no savings figures, no installation counts, no subsidy
amounts, no guarantees, no prices — unless the project already holds authority for
them. Today it holds none of those, so the design must be premium *without* social
proof, which is a harder design problem and the actual one to solve.

`OWNER_INPUTS_REQUIRED_FOR_LAUNCH.md` records what the owner has and has not
supplied. That file, not the designer's judgement, is the authority.

### Acceptance criteria

1. **Premium first impression.** A visitor landing at 1440 px, 1024 px or 390 px
   sees a composed page — a full-width hero with a real visual, deliberate
   vertical rhythm, and a typographic scale — not a left-aligned document.
2. **Clear value proposition.** The hero states what the visitor gets, in one
   headline and one supporting sentence, above the fold at all three widths.
3. **A primary CTA that dominates.** Exactly one visually primary action per
   viewport, using the canonical label from `conversion.primary_cta_label`. It is
   reachable without scrolling on mobile.
4. **Trust without fabrication.** The trust presentation uses only the site's
   real, defensible properties — sourced figures, stated uncertainty, no invented
   averages, local processing, withdrawable consent. Every trust statement traces
   to something in the repository or in the owner-approved privacy text.
5. **An understandable process.** The visitor can see, before committing, what
   happens after they click: what is asked, and what comes back. The steps shown
   match the real five-step form in `solar_be.yaml`.
6. **Responsive by design, not by reflow.** 390 px is a designed layout, not a
   collapsed desktop one. No horizontal overflow at any of the three widths.
7. **Low-friction entry.** The qualification journey opens from a CTA rather than
   dumping every field above the fold, and the underlying form and its data
   contract are unchanged.
8. **Consent and legal semantics preserved,** provably, by tests that fail if the
   required consent, the privacy link, or the primary CTA is removed.
9. **Accessibility preserved or improved:** one `h1` per page, semantic heading
   order, visible focus, labelled fields, `aria-describedby` errors, alt text that
   means something, contrast that passes AA for body text.
10. **Performance not regressed.** No web font download, no JavaScript added to
    the homepage's critical path, no raster hero, no video. The hero visual must
    be inline or a cached vector asset.

### Out of scope

A savings or ROI calculator (needs irradiation, roof geometry, consumption and
tariff data — none of which exist), Dutch content, analytics vendors, indexing,
and any change to lead destination or Prospect 360 producer configuration.
