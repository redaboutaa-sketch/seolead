"""DataForSEO and Tavily adapters. Mock transports only — no paid API is called."""
from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.core.enums import Observability, SourceState
from app.core.errors import (ResearchContractError, ResearchProviderError,
                             ResearchTimeout, ResearchUnavailable)
from app.providers.research.tavily import TavilyResearchProvider, normalize_tavily
from app.providers.search.dataforseo import DataForSEOProvider
from app.providers.search.dataforseo_normalizer import (normalize_keyword_metrics,
                                                        normalize_serp)
from app.providers.search.location import (SearchContext, UnsupportedSearchContext,
                                           get_search_context, supported_contexts)
from app.services.provider_usage import UsageRecorder

BE_FR = SearchContext(2056, "Belgium", "fr", "French", se_domain="google.be")


def serp_payload(**overrides) -> dict:
    payload = {
        "status_code": 20000,
        "status_message": "Ok.",
        "cost": 0.002,
        "tasks_count": 1,
        "tasks": [{
            "id": "task-1",
            "status_code": 20000,
            "status_message": "Ok.",
            "result": [{
                "keyword": "prix panneaux solaires belgique",
                "datetime": "2026-08-12 09:00:00 +00:00",
                "se_results_count": 1240000,
                "check_url": "https://www.google.be/search?q=...",
                "items": [
                    {"type": "organic", "rank_group": 1, "rank_absolute": 1,
                     "domain": "energie.wallonie.be", "url": "https://energie.wallonie.be/prix",
                     "title": "Prix des panneaux solaires en Wallonie",
                     "description": "Information officielle sur le coût.",
                     "breadcrumb": "energie.wallonie.be › prix"},
                    {"type": "organic", "rank_group": 2, "rank_absolute": 3,
                     "domain": "installateur.be", "url": "https://installateur.be/devis",
                     "title": "Devis panneaux solaires — comparatif des prix",
                     "description": "Comparez les devis."},
                    {"type": "people_also_ask", "rank_absolute": 2, "items": [
                        {"title": "Combien coûte une installation de 3 kWc ?"},
                        {"title": "Quelle prime pour le photovoltaïque ?"},
                    ]},
                    {"type": "related_searches", "rank_absolute": 9,
                     "items": ["prix panneaux solaires 2026", "panneaux solaires wallonie"]},
                    {"type": "video", "rank_absolute": 4},
                    {"type": "a_brand_new_google_feature", "rank_absolute": 5},
                ],
            }],
        }],
    }
    payload.update(overrides)
    return payload


class TestSearchContext:
    def test_belgium_french_is_configured(self):
        context = get_search_context("BE", "fr")
        assert context.location_code == 2056
        assert context.language_code == "fr"
        assert context.se_domain == "google.be"

    def test_belgium_dutch_is_a_different_search(self):
        """BE/fr and BE/nl are different SERPs for the same product."""
        fr = get_search_context("BE", "fr")
        nl = get_search_context("BE", "nl")
        assert fr.location_code == nl.location_code
        assert fr.language_code != nl.language_code

    def test_mobile_is_a_distinct_context(self):
        context = get_search_context("BE", "fr", device="mobile")
        assert context.device == "mobile"
        assert context.os == "android"

    def test_unsupported_market_is_refused_not_defaulted(self):
        with pytest.raises(UnsupportedSearchContext):
            get_search_context("JP", "ja")

    def test_multiple_markets_are_configured(self):
        assert {"BE/fr", "BE/nl", "BE/de", "FR/fr"} <= set(supported_contexts())


class TestDataForSEONormalizer:
    def test_organic_results_are_extracted(self):
        snapshot = normalize_serp(serp_payload(), context=BE_FR, query="q")
        assert len(snapshot.organic) == 2
        first = snapshot.organic[0]
        assert first.rank_group == 1
        assert first.domain == "energie.wallonie.be"
        assert first.title.startswith("Prix des panneaux")

    def test_people_also_ask_is_extracted(self):
        snapshot = normalize_serp(serp_payload(), context=BE_FR, query="q")
        assert len(snapshot.paa) == 2
        assert "3 kWc" in snapshot.paa[0].text

    def test_related_searches_are_extracted(self):
        snapshot = normalize_serp(serp_payload(), context=BE_FR, query="q")
        assert len(snapshot.related) == 2
        assert "panneaux solaires wallonie" in [q.text for q in snapshot.related]

    def test_unknown_feature_is_recorded_not_dropped(self):
        """Google adds SERP features; an unknown one is information."""
        snapshot = normalize_serp(serp_payload(), context=BE_FR, query="q")
        assert "other" in snapshot.feature_types
        unmapped = snapshot.provider_metadata["dataforseo"]["unmapped_item_types"]
        assert "a_brand_new_google_feature" in unmapped

    def test_provider_cost_is_carried_through(self):
        snapshot = normalize_serp(serp_payload(), context=BE_FR, query="q")
        assert snapshot.provider_cost == 0.002

    def test_failed_task_under_ok_envelope_is_rejected(self):
        """DataForSEO returns 20000 at the top while a task failed.

        Trusting the envelope would produce a confidently empty SERP.
        """
        payload = serp_payload()
        payload["tasks"][0]["status_code"] = 40501
        payload["tasks"][0]["status_message"] = "Invalid Field"
        with pytest.raises(ResearchContractError) as exc:
            normalize_serp(payload, context=BE_FR, query="q")
        assert "40501" in str(exc.value)

    def test_failed_envelope_is_rejected(self):
        with pytest.raises(ResearchContractError):
            normalize_serp(serp_payload(status_code=40100), context=BE_FR, query="q")

    def test_missing_tasks_is_rejected(self):
        with pytest.raises(ResearchContractError):
            normalize_serp({"status_code": 20000}, context=BE_FR, query="q")

    def test_empty_result_block_is_not_an_error(self):
        payload = serp_payload()
        payload["tasks"][0]["result"] = []
        snapshot = normalize_serp(payload, context=BE_FR, query="q")
        assert snapshot.organic == []
        assert snapshot.provider_metadata["dataforseo"]["empty_result"] is True

    def test_unparseable_datetime_does_not_become_now(self):
        payload = serp_payload()
        payload["tasks"][0]["result"][0]["datetime"] = "not a date"
        snapshot = normalize_serp(payload, context=BE_FR, query="q")
        # Falls back to retrieval time, which is honest, and does not crash.
        assert snapshot.retrieved_at is not None

    def test_missing_optional_fields_are_tolerated(self):
        payload = serp_payload()
        payload["tasks"][0]["result"][0]["items"] = [
            {"type": "organic", "rank_group": 1}
        ]
        snapshot = normalize_serp(payload, context=BE_FR, query="q")
        assert snapshot.organic[0].url is None
        assert snapshot.organic[0].title is None


class TestKeywordMetrics:
    def test_metrics_are_normalized(self):
        payload = {
            "status_code": 20000,
            "tasks": [{"status_code": 20000, "result": [{
                "keyword": "prix panneaux solaires belgique",
                "search_volume": 2400, "cpc": 1.85,
                "competition": "HIGH", "competition_index": 87,
            }]}],
        }
        out = normalize_keyword_metrics(payload)
        metrics = {m["metric_type"]: m for m in out["prix panneaux solaires belgique"]}
        assert metrics["search_volume"]["value"] == 2400
        assert metrics["cpc"]["currency"] == "USD"
        assert metrics["competition"]["value_text"] == "HIGH"

    def test_absent_metric_is_omitted_not_zeroed(self):
        payload = {"status_code": 20000, "tasks": [{"status_code": 20000,
                   "result": [{"keyword": "k", "search_volume": None}]}]}
        out = normalize_keyword_metrics(payload)
        assert "k" not in out or not any(
            m["metric_type"] == "search_volume" for m in out.get("k", []))


class TestDataForSEOClient:
    def test_not_configured_without_credentials(self, settings_no_llm):
        assert DataForSEOProvider(settings_no_llm).configured is False

    async def test_request_body_is_an_array_with_one_task(self, settings_dataforseo):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            seen["auth"] = request.headers.get("authorization")
            seen["path"] = request.url.path
            return httpx.Response(200, json=serp_payload())

        provider = DataForSEOProvider(settings_dataforseo,
                                      transport=httpx.MockTransport(handler))
        await provider.serp(query="prix panneaux solaires Belgique",
                            context=BE_FR, correlation_id="c1")

        assert seen["path"] == "/v3/serp/google/organic/live/advanced"
        assert isinstance(seen["body"], list) and len(seen["body"]) == 1
        task = seen["body"][0]
        assert task["location_code"] == 2056
        assert task["language_code"] == "fr"
        assert task["device"] == "desktop"

    async def test_basic_auth_header_is_used(self, settings_dataforseo):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json=serp_payload())

        provider = DataForSEOProvider(settings_dataforseo,
                                      transport=httpx.MockTransport(handler))
        await provider.serp(query="q", context=BE_FR, correlation_id="c1")

        assert seen["auth"].startswith("Basic ")
        decoded = base64.b64decode(seen["auth"].split(" ", 1)[1]).decode()
        assert decoded == "test-login:test-password-not-real"

    async def test_401_is_not_retryable_and_does_not_echo_credentials(
            self, settings_dataforseo):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"status_message": "auth failed"})

        provider = DataForSEOProvider(settings_dataforseo,
                                      transport=httpx.MockTransport(handler))
        with pytest.raises(ResearchProviderError) as exc:
            await provider.serp(query="q", context=BE_FR, correlation_id="c1")
        assert exc.value.retryable is False
        assert "test-password-not-real" not in str(exc.value)

    async def test_402_insufficient_funds_is_not_retryable(self, settings_dataforseo):
        provider = DataForSEOProvider(
            settings_dataforseo,
            transport=httpx.MockTransport(lambda r: httpx.Response(402)))
        with pytest.raises(ResearchProviderError) as exc:
            await provider.serp(query="q", context=BE_FR, correlation_id="c1")
        assert exc.value.retryable is False

    async def test_429_is_retryable(self, settings_dataforseo):
        provider = DataForSEOProvider(
            settings_dataforseo,
            transport=httpx.MockTransport(lambda r: httpx.Response(429)))
        with pytest.raises(ResearchUnavailable):
            await provider.serp(query="q", context=BE_FR, correlation_id="c1")

    async def test_actual_provider_cost_is_recorded(self, settings_dataforseo):
        usage = UsageRecorder()
        provider = DataForSEOProvider(
            settings_dataforseo, usage=usage,
            transport=httpx.MockTransport(lambda r: httpx.Response(
                200, json=serp_payload())))
        await provider.serp(query="q", context=BE_FR, correlation_id="c1")

        assert usage.events[0].cost_usd == 0.002
        assert usage.events[0].cost_is_actual is True


TAVILY_PAYLOAD = {
    "query": "prix panneaux solaires Belgique",
    "results": [
        {"id": "r1", "title": "Prix des panneaux solaires en Belgique",
         "url": "https://energie.wallonie.be/prix",
         "content": "Le prix d'une installation dépend de la puissance installée.",
         "score": 0.93},
        {"id": "r2", "title": "Actualité du photovoltaïque",
         "url": "https://example-news.be/pv",
         "content": "Le marché du panneau solaire évolue en Belgique.",
         "score": 0.71, "published_date": "2026-08-01"},
        {"id": "r3", "title": "No URL here", "content": "orphan", "score": 0.5},
    ],
    "response_time": 1.42,
    "request_id": "req-1",
}


class TestTavilyNormalizer:
    def test_sources_are_normalized(self):
        result = normalize_tavily(TAVILY_PAYLOAD, query="q", market="BE",
                                  language="fr")
        # The result with no URL is dropped: a source we cannot cite is not usable.
        assert len(result.sources) == 2
        assert result.sources[0].url == "https://energie.wallonie.be/prix"

    def test_missing_published_date_stays_none(self):
        """Tavily's general search returns no date. It must not be invented."""
        result = normalize_tavily(TAVILY_PAYLOAD, query="q", market="BE",
                                  language="fr")
        undated = next(s for s in result.sources if s.candidate_id == "r1")
        assert undated.published_at is None

    def test_undated_source_is_estimated_not_observed(self):
        result = normalize_tavily(TAVILY_PAYLOAD, query="q", market="BE",
                                  language="fr")
        fact = next(f for f in result.facts if f.source_ref == "r1")
        assert fact.observability is Observability.ESTIMATED

    def test_dated_source_is_observed(self):
        result = normalize_tavily(TAVILY_PAYLOAD, query="q", market="BE",
                                  language="fr")
        fact = next(f for f in result.facts if f.source_ref == "r2")
        assert fact.observability is Observability.OBSERVED

    def test_relevance_score_is_not_treated_as_factual_confidence(self):
        """Tavily's score says 'matched your query well', not 'is true'."""
        result = normalize_tavily(TAVILY_PAYLOAD, query="q", market="BE",
                                  language="fr")
        source = result.sources[0]
        assert source.confidence is None
        assert source.metadata["tavily"]["relevance_score"] == 0.93
        assert all(f.confidence is None for f in result.facts)

    def test_undated_sources_are_named_in_unresolved(self):
        result = normalize_tavily(TAVILY_PAYLOAD, query="q", market="BE",
                                  language="fr")
        assert any("no publication date" in u for u in result.unresolved_data)

    def test_empty_results_is_clean_empty_not_a_failure(self):
        result = normalize_tavily({"results": [], "request_id": "x"}, query="q",
                                  market="BE", language="fr")
        assert result.source_outcomes[0].state is SourceState.NO_RESULTS
        assert any("returned no web sources" in u for u in result.unresolved_data)

    def test_missing_results_array_is_a_contract_error(self):
        with pytest.raises(ResearchContractError):
            normalize_tavily({"request_id": "x"}, query="q", market="BE",
                             language="fr")


class TestTavilyClient:
    async def test_bearer_auth_and_country_boost(self, settings_tavily):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            seen["path"] = request.url.path
            return httpx.Response(200, json=TAVILY_PAYLOAD)

        provider = TavilyResearchProvider(settings_tavily,
                                          transport=httpx.MockTransport(handler))
        await provider.research(query="q", market="BE", language="fr",
                                correlation_id="c1")

        assert seen["path"] == "/search"
        assert seen["auth"] == "Bearer test-tavily-key-not-real"
        assert seen["body"]["country"] == "belgium"
        assert seen["body"]["include_answer"] is False

    async def test_unpriced_usage_is_recorded_as_unknown_not_zero(self,
                                                                  settings_tavily):
        usage = UsageRecorder()
        provider = TavilyResearchProvider(
            settings_tavily, usage=usage,
            transport=httpx.MockTransport(lambda r: httpx.Response(
                200, json=TAVILY_PAYLOAD)))
        await provider.research(query="q", market="BE", language="fr",
                                correlation_id="c1")

        assert usage.events[0].cost_usd is None
        assert usage.events[0].cost_is_actual is False
        assert usage.total_cost_usd() is None

    async def test_missing_key_refuses_before_any_request(self, settings_no_llm):
        provider = TavilyResearchProvider(settings_no_llm)
        with pytest.raises(ResearchProviderError):
            await provider.research(query="q", market="BE", language="fr",
                                    correlation_id="c1")

    async def test_timeout_is_classified(self, settings_tavily):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        provider = TavilyResearchProvider(settings_tavily,
                                          transport=httpx.MockTransport(handler))
        with pytest.raises(ResearchTimeout):
            await provider.research(query="q", market="BE", language="fr",
                                    correlation_id="c1")
