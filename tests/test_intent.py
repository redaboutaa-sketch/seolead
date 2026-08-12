"""Intent classification, content-type selection and slugs."""
from __future__ import annotations

import pytest

from app.core.enums import ContentType, SearchIntent
from app.services.intent import (classify_intent, normalize_query,
                                 select_content_type, slugify)


class TestNormalization:
    def test_accents_and_case_collapse(self):
        assert normalize_query("Rentabilité") == normalize_query("rentabilite")

    def test_whitespace_collapses(self):
        assert normalize_query("  prix   panneaux  ") == "prix panneaux"


class TestIntent:
    def test_price_query_is_commercial(self, solar_profile):
        assert classify_intent("prix panneaux solaires", solar_profile) is \
            SearchIntent.COMMERCIAL

    def test_market_name_does_not_imply_local_intent(self, solar_profile):
        """'Belgique' is the market, not a locality.

        Without this rule every query in a national vertical classifies as LOCAL,
        which routes the whole vertical to the wrong content type and CTA.
        """
        assert classify_intent("prix panneaux solaires Belgique", solar_profile) is \
            SearchIntent.COMMERCIAL

    def test_a_real_locality_does_imply_local_intent(self, solar_profile):
        assert classify_intent("prix panneaux solaires Liège", solar_profile) is \
            SearchIntent.LOCAL

    def test_regions_count_as_localities(self, solar_profile):
        """Wallonia and Flanders have genuinely different rules."""
        assert classify_intent("prix installation Wallonie", solar_profile) is \
            SearchIntent.LOCAL

    def test_comparison_query_is_commercial(self, solar_profile):
        assert classify_intent("comparatif onduleurs solaires", solar_profile) is \
            SearchIntent.COMMERCIAL

    def test_question_query_is_informational(self, solar_profile):
        assert classify_intent("comment fonctionne un panneau solaire",
                               solar_profile) is SearchIntent.INFORMATIONAL

    def test_dutch_commercial_vocabulary_works(self, solar_profile):
        assert classify_intent("prijs zonnepanelen", solar_profile) is \
            SearchIntent.COMMERCIAL


class TestContentTypeSelection:
    def test_comparison_query_becomes_a_comparison(self, solar_profile):
        assert select_content_type("comparatif onduleurs", SearchIntent.COMMERCIAL,
                                   solar_profile) is ContentType.COMPARISON

    def test_commercial_query_becomes_a_landing_page(self, solar_profile):
        assert select_content_type("prix panneaux solaires", SearchIntent.COMMERCIAL,
                                   solar_profile) is ContentType.LANDING_PAGE

    def test_informational_query_becomes_a_guide(self, solar_profile):
        assert select_content_type("comment fonctionne un panneau",
                                   SearchIntent.INFORMATIONAL,
                                   solar_profile) is ContentType.GUIDE

    def test_not_everything_becomes_an_article(self, solar_profile):
        """The mission's explicit rule."""
        chosen = {
            select_content_type(q, i, solar_profile)
            for q, i in [
                ("prix panneaux solaires", SearchIntent.COMMERCIAL),
                ("comparatif onduleurs", SearchIntent.COMMERCIAL),
                ("comment fonctionne un panneau", SearchIntent.INFORMATIONAL),
                ("prix installation Liège", SearchIntent.LOCAL),
            ]
        }
        assert len(chosen) > 1
        assert ContentType.ARTICLE not in chosen

    def test_local_intent_never_selects_local_page_in_phase2(self, solar_profile):
        """LOCAL_PAGE needs locally-specific verified facts. Nothing enforces
        that yet, so the type stays unreachable."""
        assert select_content_type("prix installation Liège", SearchIntent.LOCAL,
                                   solar_profile) is not ContentType.LOCAL_PAGE


class TestSlug:
    def test_accents_and_punctuation_are_stripped(self):
        assert slugify("Rentabilité des panneaux ? (2026)") == \
            "rentabilite-des-panneaux-2026"

    def test_long_slugs_cut_on_a_word_boundary(self):
        slug = slugify(" ".join(["motlong"] * 30))
        assert len(slug) <= 80
        assert not slug.endswith("-")

    def test_empty_input_never_produces_an_empty_slug(self):
        assert slugify("???") == "untitled"
