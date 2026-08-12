# RelevanceGate

## The incident it exists for

Phase 2's live run for `prix panneaux solaires Belgique` returned exactly one
"supported fact":

> *The making of Don Matrelli's Legacy, a mod for Grand Prix Circuit (part I)*

A Hacker News post about a racing-game modification, marked OBSERVED and supported,
because nothing in the pipeline asked whether the source was about the query.

## Why naive overlap does not fix it

**"prix" appears in "Grand Prix".** A gate scoring bare token overlap gives that
source a third of the query and calls it partially relevant. The trap is not
sloppiness — it is that a query's words are not equally about the query's subject.

So the gate splits the query into three kinds of token, using the vertical profile:

| Kind | For `prix panneaux solaires Belgique` | Meaning |
|---|---|---|
| **topic** | `panneau`, `solaire` | what the query is *about* |
| **modifier** | `prix` | the commercial or comparative frame |
| **market** | `belgique` | the country's own name — no topical signal |

and applies one hard rule:

> **A source matching zero topic tokens is IRRELEVANT, however many modifiers it
> matches.**

"Grand Prix Circuit" matches `prix` and neither `panneau` nor `solaire`. Rejected
deterministically, with a reason an operator can read, before any model is asked.

## Two levels

**Source relevance** — is this page about the query?

**Claim relevance** — does this sentence help answer it? A page about installation
costs may also mention the author's holiday, and that sentence must not become
eligible evidence. A claim can never outrank its source: an IRRELEVANT source's
claims are IRRELEVANT, and a claim from a LOW_RELEVANCE source is clamped down.

## Statuses

| Status | Eligible as evidence? | Meaning |
|---|---|---|
| `RELEVANT` | **yes** | covers enough of the query's topic |
| `LOW_RELEVANCE` | no | partial match, below threshold |
| `IRRELEVANT` | no | no topical overlap, or score below the floor |
| `UNKNOWN` | no | the query carries no topic tokens to judge against |

`LOW_RELEVANCE` is deliberately **not** eligible. A weak match is exactly the kind
of source that reads plausible in a draft and cannot be defended afterwards.

## Scoring (Stage A — deterministic)

```
title_coverage  = matched topic tokens in title  / topic tokens
body_coverage   = matched topic tokens in body   / topic tokens
topic_score     = 0.6 × title_coverage + 0.4 × body_coverage

modifier_bonus  = 0.15 × modifier coverage       (a bonus, never a rescue)
domain_bonus    = 0.35 × topic coverage in the domain

score = min(1.0, max(topic_score, 0.85 × body_coverage, domain_bonus) + modifier_bonus)
```

The domain bonus is capped below the RELEVANT threshold on purpose.
`panneaux-solaires-belgique.be/tarifs` titled "Nos tarifs" is genuinely on-topic —
but a solar company's careers page is still not evidence about solar pricing. A
matching domain says what the *site* is about; title and body say what the *page*
is about. Domain alone reaches LOW_RELEVANCE, never RELEVANT.

### Thresholds

| Setting | Default | Env |
|---|---|---|
| `relevant_at` | 0.55 | `SEOLEAD_RELEVANCE_RELEVANT_AT` |
| `low_relevance_at` | 0.30 | `SEOLEAD_RELEVANCE_LOW_AT` |

**These numbers are not validated against a labelled corpus.** They were chosen so
the Phase 2 failure is rejected and the obvious good cases pass, and they must not
be presented as if they were measured. Tune them against real rejections using
`seolead package rejected <id>`.

## Stage B — semantic review

Runs only when an LLM is configured, only for `LOW_RELEVANCE`, and never for a hard
rejection. A model that disagrees with "this source shares no topic with the query"
is wrong, and asking invites it to be. It can promote out of LOW_RELEVANCE or demote
to IRRELEVANT; it cannot overturn the deterministic hard rule.

## The stemmer, and a bug worth remembering

Matching needs `panneaux` (query) to reach `panneau` (title). French has two
unrelated plurals ending in `aux`:

- `panneau → panneaux` — drop the `x`
- `cheval → chevaux` — `aux → al`

The first implementation applied the second rule to both, producing `panneal`,
which matches nothing. Since `panneau` is a topic token for the pilot query, that
one-line bug silently disabled the gate's central check. `-eaux` is now tested
before `-aux`, and `TestStemmerRegression` pins it.

## Rejections are kept

A rejected source is persisted with its status, score and reason — on the
`research_source` row and in `research_package.rejected_evidence`. Phase 2 could
not answer "why was this source dropped", which is the first question anyone asks
when a gate misbehaves.

```bash
docker exec seolead_api seolead package rejected <package-id>
curl -H "X-Internal-Key: $KEY" \
  http://127.0.0.1:8100/internal/v1/research-packages/<id>/rejected
```

## Known limitation

Matching is lexical. A source using entirely different vocabulary for the same
concept (`photovoltaïque` where the query says `panneaux solaires`) scores lower
than it deserves, and Stage B only sees it if it lands in LOW_RELEVANCE rather
than IRRELEVANT. Embeddings over `pgvector` would fix this properly and are the
obvious Phase 4 improvement; the profile's vocabulary lists are the interim
mitigation.
