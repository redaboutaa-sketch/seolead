# DataForSEO — Search Intelligence provider

Capabilities: `SERP`, `KEYWORD_METRICS`.

## Contract

Verified against the official v3 documentation during implementation. Nothing here
was guessed.

```
POST https://api.dataforseo.com/v3/serp/google/organic/live/advanced
POST https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live
Authorization: Basic base64(login:password)
Content-Type: application/json
```

**The body is a JSON array of task objects**, and a live endpoint accepts exactly
one task per call:

```json
[{"keyword": "prix panneaux solaires Belgique",
  "location_code": 2056, "language_code": "fr",
  "device": "desktop", "os": "windows", "depth": 20, "se_domain": "google.be"}]
```

Results live at `tasks[].result[].items[]`.

### Two-level status, and why both are checked

DataForSEO returns `status_code` at the envelope **and** on each task. A successful
envelope (`20000`) can carry a failed task. Trusting the envelope alone produces a
confidently empty SERP — a result that says "Google shows nothing here" when the
truth is that the request was malformed. Both levels are checked, and a failed task
raises rather than returning zero results.

### Item types

Organic items carry `type`, `rank_group`, `rank_absolute`, `domain`, `title`,
`url`, `description`, `breadcrumb`. `people_also_ask` and `related_searches` appear
in the same array, each nesting its payload under `items`.

An unrecognised type is recorded as `OTHER` with its raw name preserved in
`provider_metadata.dataforseo.unmapped_item_types`. Google adds SERP features
without notice, and an unknown feature is information about the result page, not a
parse failure.

## Search context

Belgium is not a generic global Google search, and `BE/fr` and `BE/nl` are
different result pages for the same product. Nothing Belgian is hard-coded into the
provider — it takes a `SearchContext`, and `app/providers/search/location.py` maps
a (market, language) pair onto one.

| Context | location_code | language | se_domain |
|---|---|---|---|
| BE/fr | 2056 | fr | google.be |
| BE/nl | 2056 | nl | google.be |
| BE/de | 2056 | de | google.be |
| FR/fr | 2250 | fr | google.fr |
| NL/nl | 2528 | nl | google.nl |

Mobile is a distinct context, not a variant: it produces a different SERP, and it
is part of the cache key.

An unconfigured market raises `UnsupportedSearchContext` rather than defaulting to
a global search — a silent fallback would return a SERP no one in that market sees.

## Keyword metrics

`search_volume`, `cpc`, `competition`, `competition_index` from Google Ads.

Every metric is stored with `provider`, `metric_type`, `retrieved_at` and an
`observability` value under a CHECK constraint. A metric absent from the response
is **omitted**, and the opportunity score records it as `UNKNOWN` in
`missing_inputs` rather than scoring it zero.

Metrics are `OBSERVED` in the sense that a named provider reported them at a known
time. That is not the same as a fact about the world, and the stored provenance is
what lets a reader tell the difference.

## Cost

DataForSEO returns its own `cost` in USD on every response. That is recorded as
`cost_is_actual = true` — real billing data, not an estimate. Roughly $0.002 per
live advanced SERP call at the time of writing; the recorded value is authoritative.

Per-job ceiling: `SEOLEAD_MAX_CALLS_PER_PROVIDER` (default 3). Exceeding it raises
`PROVIDER_BUDGET_EXCEEDED` before the request, not after.

## Errors

| Condition | Behaviour |
|---|---|
| No credentials | `PROVIDER_NOT_CONFIGURED`, no request attempted |
| 401 | Not retryable. The message never echoes the credential. |
| 402 insufficient funds | Not retryable — an operator action, not a transient fault |
| 429 | Retryable |
| Envelope or task status ≠ 20000 | `LAST30DAYS_CONTRACT_ERROR` (contract family) |
| Non-JSON body | Contract error |

## Credentials

```
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=      # the API password from the dashboard, not the account one
DATAFORSEO_BASE_URL=https://api.dataforseo.com
```

`httpx` builds the Basic header from `auth=(login, password)`, so the credential is
never assembled into a string this code logs and never appears in a URL.

## Live validation, 2026-08-12

```
POST /v3/serp/google/organic/live/advanced  →  HTTP 403
{"status_code": 40104,
 "status_message": "Please verify your account before using the API. ..."}
```

**Credentials are valid.** Bad credentials return 401; DataForSEO authenticated the
request and returned a business state. The account requires verification in the
provider panel. Cost incurred: $0.00 (`cost: 0` in the response).

The run exposed a defect since fixed: the handler reported only
`"DataForSEO returned 403"`, discarding `status_code 40104` and the message naming
the exact remedy. An HTTP status alone is not actionable. `_error_detail()` now
surfaces the provider's own code and message on every error branch, bounded to 300
characters and reading only those two named fields.

Still unverified against the real API: organic results, PAA, related searches,
keyword metrics, and the Belgium/French context beyond request acceptance.

## Caching

SERP snapshots are cached for `SEOLEAD_SERP_TTL_HOURS` (default 24) keyed on
normalised query + location + language + device. `--force-refresh` overrides.
Result pages move daily; a stale SERP misreads the competition.
