# LLM providers

## The port

```python
class LLMProvider(Protocol):
    code: str
    @property
    def configured(self) -> bool: ...
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
```

`LLMRequest` carries a **capability**, not a model name:

```
RESEARCH_SYNTHESIS · CONTENT_BRIEF · LONG_FORM_WRITING · CLASSIFICATION · SEO_QA
```

Business code asks for `LONG_FORM_WRITING` and never names a model, so changing
provider or tier is configuration. The shape is borrowed from the Hermes gateway
verified in Phase 1 — capability in, usage accounting out.

`LLMResponse` always returns `content`, `provider`, `model`, `usage`
(`input_tokens`, `output_tokens`, `total_tokens`, `cost_cents`) and `latency_ms`.
Usage is persisted on every `content_draft`. The project's KPI is *profitable*
leads; a content factory that cannot report its own cost cannot report profit.

**No hidden reasoning is ever stored.** Only the final output is persisted.

## Implementations

| Provider | Status | Notes |
|---|---|---|
| `OpenAICompatibleProvider` | implemented | `/chat/completions` dialect — serves OpenAI, DeepSeek, Together, local vLLM. Base URL and model are configuration. |
| `NullLLMProvider` | implemented | Refuses every call with `LLM_NOT_CONFIGURED`. Selected automatically when no key is set. |
| `HermesGatewayProvider` | **not implemented, deliberately** | The seam exists; the coupling does not. See below. |
| `ClaudeProvider`, `GeminiProvider` | not implemented | Add behind the same protocol. |

### Why there is no fabricating fallback

`NullLLMProvider` refuses rather than producing content from a template. A
deterministic stitcher would emit something that reads like an article and was
written by nobody, from no evidence — the exact failure this pipeline exists to
prevent. Selection lives in `app/providers/llm/registry.py` and is a single
readable function.

### Hermes

Phase 1 verified the existing Hermes gateway is a stateless, 3-route, DeepSeek-
backed service belonging to the TechFormaNord stack, and it is read-only. Phase 2
therefore does not integrate it and does not clone it. What was adopted is the
*pattern*: capability routing, `UsageInfo` on every response, correlation IDs, and
the provider key held only by the process that needs it.

Adding `HermesGatewayProvider` later means implementing the protocol against
`POST /v1/generate` with an `X-Internal-Key` header. Nothing else changes.

## Configuration

```
SEOLEAD_LLM_PROVIDER=openai_compatible
SEOLEAD_LLM_API_KEY=            # absent is a valid, handled state
SEOLEAD_LLM_BASE_URL=https://api.openai.com/v1
SEOLEAD_LLM_MODEL=gpt-4o-mini
SEOLEAD_LLM_TIMEOUT_SECONDS=120
SEOLEAD_LLM_MAX_RETRIES=2
```

Credentials arrive from the environment only. No key is ever a default, a
command-line argument, or a log field.

## Running without a credential

Phase 2 is designed for it, and the default test suite passes with no keys at all.

- `settings.llm_configured` is checked before every generation step.
- With no key: research runs, the package is built, the **deterministic brief is
  built and persisted**, and the pipeline stops with `LLM_NOT_CONFIGURED`.
- The brief is complete without a model — required facts, required sources,
  cautionary claims, CTA and missing-information are all deterministic.

Verified in the real run of 2026-08-12: `stopped_at: "draft"`,
`error_code: "LLM_NOT_CONFIGURED"`, with `research_package_id` and
`content_brief_id` both populated.

## Where the LLM is allowed to act

| Stage | LLM role | If it fails |
|---|---|---|
| Research | none | — |
| Package assembly | **none** — provenance is deterministic | — |
| Brief | optional: title and outline only | falls back to the deterministic brief |
| Draft | required | pipeline stops, nothing persisted |
| Deterministic QA | **none** | — |
| Advisory QA | optional, never blocking | recorded as `SKIPPED` |
| Approval | **none** | — |

Two of these are non-negotiable. The LLM cannot touch provenance, and it cannot
block or pass QA — an advisory review is stored separately with
`qa_type=LLM_ASSISTED` and its findings are forced to `blocking: false`.

## Error handling

| Condition | Behaviour |
|---|---|
| No key | `LLM_NOT_CONFIGURED`, no HTTP call |
| Timeout | `LLM_TIMEOUT`, retried with backoff |
| 429 / 5xx | `LLM_PROVIDER_ERROR`, retried |
| Other 4xx | `LLM_PROVIDER_ERROR`, **not retried** — a 400 will not become a 200 |
| Malformed body | `LLM_PROVIDER_ERROR` |
| Non-JSON draft | `LLM_PROVIDER_ERROR` — not salvaged by regex |

Upstream error text is bounded to 200–500 characters and never interpreted. The
log redactor (`app/core/logging.py`) is the guarantee that a key quoted back in an
error body never reaches a log line.

## Cost control

Every draft stores `provider`, `model`, token counts and `latency_ms`. `cost_cents`
is `None` until a price table is configured — "we did not price this" and "this was
free" are different facts, and conflating them would understate spend.
