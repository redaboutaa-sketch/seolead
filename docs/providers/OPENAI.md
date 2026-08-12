# OpenAI — live content writer

Phase 3's preferred writer, used through the Phase 2 `LLMProvider` abstraction
without changes to it. `OpenAICompatibleProvider` speaks `/chat/completions`, so
the same adapter serves OpenAI, DeepSeek, Together or a local vLLM — base URL and
model are configuration.

```
SEOLEAD_LLM_PROVIDER=openai_compatible
SEOLEAD_LLM_API_KEY=            # runtime only; absent is a handled state
SEOLEAD_LLM_BASE_URL=https://api.openai.com/v1
SEOLEAD_LLM_MODEL=gpt-4o        # configurable, never hard-coded
SEOLEAD_LLM_TIMEOUT_SECONDS=120
SEOLEAD_LLM_MAX_RETRIES=2
```

## Where the model is allowed to act

| Stage | Role | If it fails |
|---|---|---|
| SERP / research | none | — |
| Relevance Stage A | **none** — deterministic | — |
| Relevance Stage B | classify LOW_RELEVANCE only | keeps the deterministic decision |
| Package assembly | **none** — provenance is code | — |
| Brief | title and outline only | falls back to the deterministic brief |
| Draft | required | pipeline stops, nothing persisted |
| Factual QA | **none** | — |
| SEO QA (deterministic) | **none** | — |
| Advisory QA | optional, never blocking | recorded as SKIPPED |
| Approval | **none** | — |

Two of these are non-negotiable: the model cannot touch provenance, and it cannot
overturn a hard relevance rejection. A model that disagrees with "this source
shares no topic with the query" is wrong, and asking invites it to be.

## What the writer receives

Vertical configuration, the ContentBrief, ResearchPackage V2's **eligible**
evidence, the unresolved facts, the claim restrictions and the CTA objective.

It does **not** receive rejected evidence, and it does not receive competitor page
text. SERP structure reaches it as derived observations and questions, never as
copy to imitate.

## Prompt rules

Explicitly instructed: never invent a fact, price, subsidy, statistic, regulation,
study or testimonial; never present an estimate as a measurement; do not write
around the listed limitations; no keyword stuffing; no manufactured urgency or
guaranteed outcomes; write for the reader first; close with one honest next step.

Restricted topics with no supporting evidence are named individually in the system
prompt, drawn from the vertical profile — so the prohibition is specific to this
vertical and this evidence rather than generic boilerplate.

## Content quality target

The mission is explicit that length is not the goal. The brief targets a concise,
useful, well-structured answer to the actual intent, with transparent uncertainty
and a clear next step. QA enforces a floor (150 words) but no ceiling, and rewards
covering the questions Google surfaces rather than word count.

## Usage and cost

Every draft stores `provider`, `model`, `input_tokens`, `output_tokens`,
`total_tokens` and `latency_ms`. `cost_cents` stays `None` until a price table is
configured — "we did not price this" and "this was free" are different facts.

**No hidden chain-of-thought is stored.** Only the final output is persisted.

## Errors

| Condition | Behaviour |
|---|---|
| No key | `LLM_NOT_CONFIGURED` — pipeline stops cleanly after the brief |
| Timeout | `LLM_TIMEOUT`, retried with backoff |
| 429 / 5xx | `LLM_PROVIDER_ERROR`, retried |
| Other 4xx | Not retried — a 400 will not become a 200 |
| Non-JSON draft | `LLM_PROVIDER_ERROR`, not salvaged by regex |

The key travels only as an `Authorization: Bearer` header — asserted by test never
to appear in a URL or request body — and the log redactor covers it if a provider
quotes it back in an error.
