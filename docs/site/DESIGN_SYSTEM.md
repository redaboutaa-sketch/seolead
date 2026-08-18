# Design reference — Mon Projet Solaire

Design authority for `US-SL-01` / `TRACER SL-T1`. Written before implementation
and used as the input to the SPEC CONSISTENCY gate.

---

## 1. The brief in one line

Premium, modern, bright, residential, Belgian/European, energy-tech — and
trustworthy *without a single fabricated proof point*.

That last clause is the whole design problem. The standard playbook for a solar
landing page is star ratings, installer logos, install counts and a "€1 200/year"
headline. This site holds authority for none of those, and inventing them is the
one thing the system exists not to do. So credibility has to come from
composition, restraint and specificity instead of from borrowed proof.

## 2. Competitive / design benchmark

Research only. No branding, layout or copy is reproduced.

| Pattern | Why it works | Applicable here |
|---|---|---|
| Full-bleed hero with a residential roof visual, headline overlaid or beside it | Establishes subject and context before a word is read; solar is a visual product | **YES** — as an author-drawn vector, since no licensed photography exists |
| Benefit-led headline naming the visitor's outcome | Outperforms feature-led headlines materially on click-through | **YES**, but the outcome must be "a clear picture of your project", not a savings figure |
| CTA labelled with what the visitor *gets* ("Get my free estimate") not what they do ("Submit") | Reduces the perceived cost of clicking | **ALREADY TRUE** — `primary_cta_label` is *Obtenir mon estimation personnalisée*. Reuse it verbatim; it is configuration, not copy |
| Star ratings / review counts above the fold | Strongest single above-fold conversion lever in the category | **NO** — no reviews exist. Fabricating them is refused |
| Partner / installer logo carousel | Borrowed authority | **NO** — no partners exist |
| "Gratuit · sans engagement" reassurance next to the CTA | Removes the two objections that stop a click | **YES** — and it is factually true: the form asks for nothing, charges nothing, and the site has no contract |
| Form above the fold (Suncom pattern) | Highest raw conversion; every field is a visible cost | **NO** — five steps above the fold is a wall. A CTA into a designed flow is the better trade here, and the flow already opens with cheap, non-personal questions |
| Content-first, form deferred until self-qualification (Energy Village pattern) | Suits an evidence-led page; the visitor arrives to *learn* | **PARTLY** — the hero CTA stays, but the page earns the second CTA with substance in between |
| 6-step "how installation works" demystification | Converts anxiety into a sequence | **ADAPTED** — the site does not install anything. It shows *its own* three-step journey, which is the honest version |
| Pricing matrix with explicit ranges and per-Wc metrics | Specificity reads as expertise | **YES, indirectly** — the price page already does exactly this. The homepage should point at it as the proof it is |
| FAQ answering "is this legitimate / what happens to my data" | Handles the objection a lead form creates | **YES** — and this site can answer it better than the category, because the answers are true and documented |
| Repeated sticky CTA anchors on mobile | Removes scroll-back friction | **YES**, but one sticky bar that appears after the hero leaves the viewport — not anchors scattered through the page |

**Conclusion.** The category's conversion patterns split cleanly in two: the ones
that need proof this site does not have, and the ones that are pure composition.
Take all of the second group, refuse all of the first, and replace the missing
proof with the site's actual differentiator — that it says where its numbers come
from and admits what it does not know. That is a real position in a category
built on quote-farming, and no competitor benchmarked here makes it.

## 3. Palette — authority check

`OWNER_INPUTS_REQUIRED_FOR_LAUNCH.md` lists brand colours under **RECOMMENDED**,
not RESOLVED: *"The palette is a neutral practical green; two hex values retune
it."* So there is no hard brand constraint, and §9 of the brief permits proposing
a refinement.

The existing accent `#0f6b4f` is not weak — it is a credible, unfashionable
Belgian green that avoids the eco-cliché lime the category overuses. Replacing it
would be changing brand identity for taste, with no authority to do so.

**Decision: refine, do not replace.** `#0f6b4f` is kept as the primary and the
system is built around it — a deepened ink for text, a warm daylight amber as the
single accent for the solar/energy register, and a cool neutral ramp. This is a
palette *extension*, reversible by the two hex values the owner may later supply.
No `OWNER_DESIGN_DECISION_REQUIRED` is raised.

```
Primary    #0f6b4f  brand green (unchanged, existing token)
           #0b5340  pressed / strong
           #e8f3ee  tint surface
Solar      #f2a71b  daylight amber — accent only, never a CTA
           #fdf3e0  tint surface
Ink        #0d1b16  headings
           #4a5a53  body muted
Neutral    #ffffff #f7f9f8 #eef2f0 #dde5e1   surfaces and borders
Focus      #0a5cc4  unchanged (AA against every surface above)
```

Dark mode: every token has a variant, as today. The amber desaturates to `#f0b850`
so it does not glow.

## 4. Typographic scale

System font stack, unchanged. A web font is a render-blocking request on a 4G
connection for a visual gain a well-set system stack largely provides, and the
performance criterion in `US-SL-01` forbids it.

```
--step--1  0.875rem   captions, tags, legal
--step-0   1.0625rem  body (unchanged)
--step-1   1.1875rem  lede
--step-2   clamp(1.35rem, 1.15rem + 0.9vw, 1.6rem)   h3 / card titles
--step-3   clamp(1.75rem, 1.4rem + 1.6vw, 2.4rem)    h2
--step-4   clamp(2.25rem, 1.6rem + 3.1vw, 3.75rem)   h1 / hero
```

Headings: `-0.02em` tracking, `1.1` leading at hero size, `text-wrap: balance`.
Body: `1.65` leading, `--measure: 38rem` for prose. Minimum rendered size
anywhere: 0.875 rem.

## 5. Spacing, containers, radii, shadows

```
--space-1 .25rem   --space-2 .5rem   --space-3 .75rem   --space-4 1rem
--space-5 1.5rem   --space-6 2rem    --space-7 3rem     --space-8 4rem
--space-9 6rem

--width-prose  38rem
--width-page   72rem
--width-wide   82rem

--radius-sm 8px   --radius-md 14px   --radius-lg 22px   --radius-pill 999px

--shadow-1  0 1px 2px rgb(13 27 22 / .04), 0 2px 8px rgb(13 27 22 / .04)
--shadow-2  0 2px 4px rgb(13 27 22 / .05), 0 12px 32px rgb(13 27 22 / .08)
```

Two shadow levels only. A third is how a card grid starts looking like a template.

Section rhythm: `--space-9` between major sections at desktop, `--space-7` at
mobile. Alternating surface backgrounds (white → tinted → white) rather than
borders, so the page reads as bands instead of boxes.

## 6. Components

- **Buttons.** Pill, 3 rem min height (48 px, above the 44 px touch floor).
  Primary: solid brand green, one per viewport. Secondary: transparent with a
  1.5 px border. Ghost: text only, for "back". Hover shifts background and lifts
  by 1 px; disabled drops to 55 % opacity. No gradient on any button.
- **Cards.** White on tinted bands, `--radius-lg`, `--shadow-1`, 1 px hairline
  border, generous internal padding (`--space-5`). Icon is a 2.5 rem tinted
  rounded square holding a stroked glyph — drawn in this system, not a stock icon
  set.
- **Assurance strip.** Inline row of three short factual statements with small
  glyphs. Not a logo wall, not a stat counter.
- **Process steps.** Numbered, connected by a hairline rule on desktop, stacked
  with a left rail on mobile.
- **FAQ.** Native `<details>`, restyled. No JavaScript.
- **Form fields.** 1.5 px border, `--radius-md`, 3 rem min height, brand-green
  border and a 3 px tinted ring on focus. Choice options become full-width
  selectable tiles with a visible checked state.
- **Sticky mobile CTA — dropped during implementation.** The intent was a bar
  appearing below 62 rem once the hero had left the viewport. A CSS-only sticky
  element cannot wait for that: pinned to the bottom of a container spanning the
  page, it is visible from the first frame. At 390 px the hero's own primary CTA
  is already above the fold, so the bar rendered the identical label twice,
  adjacent — which reads as a rendering fault, not an affordance. Making it
  appear on scroll would mean shipping JavaScript to a page that ships none. The
  brief permits a sticky CTA "only if UX-justified"; with the primary action
  above the fold and repeated at the qualification and final bands, it is not.

## 7. Imagery — audit and decision

**Audit.** `web/public/` did not exist. The site shipped zero images. The CSP is
`img-src 'self' data:`, so no remote image can load even if one were referenced.

**Decision: author-drawn SVG, and a written photography spec for the owner.**

A stock photograph would be a licence liability and a visible cliché; a generated
photograph of a house that does not exist, presented as a Belgian home, is the
same category of fabrication the content pipeline refuses. A vector composition is
honestly illustrative, weighs a few kilobytes, scales to any viewport, inherits
the palette, and cannot delay LCP.

Assets drawn:

| Asset | Where | Notes |
|---|---|---|
| Hero composition | `components/home/HeroVisual.tsx` | Detached Belgian/Dutch brick house, steep gable, all-black array on the sunward roof plane, morning sky. Inlined rather than a file, so it costs no round trip and cannot delay LCP; carries a factual `<title>` as its accessible name |
| Icon set | `components/home/Icons.tsx` | Eight stroked glyphs on a shared 24-grid, all `aria-hidden` because each sits beside a text label that already carries the meaning |
| Wordmark | `components/Layout.tsx` | Sun-over-roof mark, drawn from palette tokens. Replaced wholesale the day the owner supplies a real logo |
| `favicon.svg` | `web/public/` | The same mark as a 538-byte file |

No section-band texture shipped: the bands are separated by surface colour, and a
decorative repeat would have been ornament without a job.

**What this costs.** +10.7 kB gzipped on the homepage HTML (the inline hero) and
+2.5 kB gzipped of CSS, against the previous build. Zero additional requests,
zero additional JavaScript, no web font. A photographic hero would have cost
100–300 kB and an extra round trip on the LCP path.

**Photography requirement, for when the owner supplies it** — recorded here so it
can be commissioned rather than guessed:

- 3 images minimum, ≥ 2400 px wide, landscape 3:2, licensed for commercial web use;
- subject: detached or semi-detached Belgian/Dutch brick or rendered house,
  pitched roof, modern all-black monocrystalline panels, natural mid-morning
  daylight, no lens flare, no HDR;
- one context shot (whole house in a street), one detail (panel array against
  roof tiles), optionally one with people (installer or homeowner) only if genuinely of this
  service — never a stock model implying a customer we do not have;
- no visible competitor branding, no US-style suburb, no palm trees.

Until those exist, the vector composition is the shipped art direction.

## 8. Homepage information architecture

Evaluated against the actual product, not accepted as given.

1. **Hero** — headline, one sentence, primary CTA (`primary_cta_label`),
   secondary CTA, vector composition. Reassurance line *gratuit · sans engagement
   · consentement retirable à tout moment*.

   **Rejected during SPEC CONSISTENCY:** the first draft of this line ended
   *"vos données restent en Belgique"*. The owner-approved privacy text says no
   such thing — it names a French data controller and explicitly permits
   technical subcontractors for hosting and security. The claim would have been
   fabricated, and the gate caught it. The replacement is quoted almost directly
   from `/confidentialite` (*droit de retirer votre consentement à tout
   moment*). The other two hold: the product has no price and no contract
   anywhere in it.
2. **Assurance strip** — three neutral statements: sourced figures, stated
   uncertainty, withdrawable consent. **Replaces** the benchmark's trust strip,
   because no quantitative social proof exists.
3. **Benefits** — three cards, homeowner outcomes rather than technology.
4. **How it works** — three steps mapped to the *real* journey: describe the
   project → the answers are structured into a qualification → a person comes
   back to you. The brief's suggested structure is kept; only the wording is
   adapted to what actually happens.
5. **Proof section** — replaces the brief's "savings visual". There is no
   calculator and no defensible savings figure, so this section shows the site's
   method and links the published price page when one exists. When nothing is
   published it says so, as the current build already does. *This is the
   deliberate deviation from the proposed IA, and the reason is that the proposed
   section cannot be filled without fabricating.*
6. **Qualification CTA** — the journey made visually central, with the five real
   steps named so the visitor knows the cost before clicking.
7. **FAQ** — four questions, each answerable from the repository or the
   owner-approved privacy text. No question is added to have a fifth.
8. **Final CTA** — one band, one action, no urgency device.
9. **Footer** — legal, privacy, contact-or-honest-absence. Unchanged in substance.

## 9. Mobile (390 px) — designed, not reflowed

Hero: headline at `--step-4`'s lower clamp, lede, primary CTA, secondary link,
then the reassurance row — all above 844 px without scrolling, verified. The
visual becomes a 190 px band below them. Cards stack full-width. Process becomes
a left-railed vertical list. Every tap target ≥ 44 px, asserted by test. No
decorative element overlaps text at any width. `overflow-x` is zero at 390, also
asserted by test.

## 10. Accessibility and performance targets

One `h1` per page; heading order never skips. Landmarks: `header`, `nav`, `main`,
`footer`. Focus ring 3 px `--focus`, offset 2, on every interactive element. Body
text ≥ 4.5:1, large text ≥ 3:1, in both schemes. Decorative SVG `aria-hidden`;
the hero visual carries a factual `alt`. `prefers-reduced-motion` removes every
transition.

Homepage stays a server component with no client JavaScript. No web font. No
raster image, no video. CSS remains a single hand-written stylesheet.

## 11. Explicitly refused

Generic template look · gradient washes · blob shapes · stock icon sets ·
overcrowded cards · entrance animation on scroll · fabricated social proof ·
walls of text · sub-14 px type · the AI-landing-page aesthetic (centred
everything, three identical gradient cards, a purple glow).
