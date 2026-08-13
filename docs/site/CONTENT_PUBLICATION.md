# Content publication

## States

```
DRAFT ──► QA_FAILED ──► DRAFT
  │
  └─► PENDING_APPROVAL ──► APPROVED ──► STAGED ──► PUBLISHED ──► ARCHIVED
```

`APPROVED` and `PUBLISHED` are different facts and are stored as different states.
A human has decided the content is fit; whether it is live also depends on the
site having a domain, being out of staging, and someone running the publish
action. Collapsing them would make "a person said this is good" and "this is on
the internet" the same event, and only one of those is easy to undo.

There is no transition from `APPROVED` straight to `PUBLISHED`. Staging is a
required intermediate step so that the exact bytes that will be served are looked
at before they are served.

## The gate

A draft may be staged only when **all four** hold:

| Condition | Checked by |
|---|---|
| factual QA passed, no blocking issues | `QAReview` with `layer = FACTUAL` |
| SEO QA passed, no blocking issues | `QAReview` with `layer = SEO` |
| a human recorded `APPROVED` | `Approval` |
| the body carries no outbound link | `contains_external_link` |

`evaluate_gate` reports **every** failed condition, not the first, so an operator
sees the whole distance to publishable in one look.

Publication additionally requires `SiteConfig.is_indexable`, which is itself three
conditions: a domain is set, `staging` is false, and `seo.allow_indexing` is true.

## Snapshots, not views

`PublishedContent` stores the sanitized sections that were approved. It is a copy.
Editing the draft afterwards, re-running the pipeline, or changing the renderer
cannot alter a page a human signed off on. Versions increment per
`(site, locale, slug)`; a partial unique index permits only one `PUBLISHED` row
per address, and publishing a new version archives the old one rather than
deleting it.

## Reviewing content that is not approved yet

`/preview/draft/{draft_id}` renders an unapproved draft through the same sanitizer
and the same components, behind the preview token. It writes nothing: looking at a
page never advances its state.

## Commands

```bash
seolead content list --status PENDING        # with the gate evaluated
seolead content list --status APPROVED
seolead site preview-draft <draft-id>        # unapproved review, writes nothing
seolead content approve <draft-id> --by "name"
seolead content stage <draft-id>             # refuses unless the gate passes
seolead site preview <slug>                  # the DTO the site would receive
seolead content publish <content-id>         # refuses while the site is staging
```
