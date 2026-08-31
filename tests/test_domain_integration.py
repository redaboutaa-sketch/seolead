"""Domain integration — monprojetsolaire.be.

The domain arriving is exactly the moment a site accidentally becomes indexable.
These tests pin the opposite: having an address and being ready to be found at it
are separate decisions, and only the owner makes the second one.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.site.config import SiteConfig, available_sites, load_site


def _with_validated_consents(base: dict) -> dict:
    """Simulate the day counsel-validated consent texts land, in every locale.

    Leaving staging now ALSO requires that no consent case — base text or any
    supported-locale variant — is still marked `pending_legal_review`: a launch
    with placeholder consent text is refused by the loader. Tests that model a
    launch must model that step too.
    """
    fields = []
    for field in base["conversion"]["fields"]:
        cleaned = {k: v for k, v in field.items() if k != "pending_legal_review"}
        if cleaned.get("i18n"):
            cleaned["i18n"] = {
                locale: {k: v for k, v in variant.items()
                         if k != "pending_legal_review"}
                for locale, variant in cleaned["i18n"].items()
            }
        fields.append(cleaned)
    return {**base, "conversion": {**base["conversion"], "fields": fields}}

DOMAIN = "monprojetsolaire.be"
ORIGIN = "https://monprojetsolaire.be"
OVERLAY = Path("infra/traefik/docker-compose.public.yml")
BASE_COMPOSE = Path("docker-compose.yml")


class TestCanonicalOrigin:
    def test_the_canonical_origin_is_the_production_domain(self):
        config = load_site("solar_be")
        assert config.seo.canonical_origin == ORIGIN
        assert config.domain == DOMAIN

    def test_canonicals_are_absolute_and_on_the_production_origin(self):
        config = load_site("solar_be")
        for path in ("/", "/prix-panneaux-solaires-belgique", "/nl/prijzen"):
            url = config.canonical_url(path)
            assert url.startswith(f"{ORIGIN}/"), url

    @pytest.mark.parametrize("bad", [
        "https://localhost:3100", "https://127.0.0.1", "https://seolead_web:3100",
        "https://monprojetsolaire.local", "https://site.internal",
    ])
    def test_an_internal_host_is_refused_as_a_canonical_origin(self, bad):
        """A canonical pointing at a host no crawler can reach is worse than none."""
        raw = load_site("solar_be").model_dump()
        raw["domain"] = None
        raw["seo"] = {**raw["seo"], "canonical_origin": bad,
                      "allow_publication": False}
        with pytest.raises(ValueError):
            SiteConfig(**raw)

    def test_a_plain_http_origin_is_refused(self):
        raw = load_site("solar_be").model_dump()
        raw["seo"] = {**raw["seo"], "canonical_origin": f"http://{DOMAIN}"}
        with pytest.raises(ValueError, match="https"):
            SiteConfig(**raw)

    def test_an_origin_that_contradicts_the_domain_is_refused(self):
        raw = load_site("solar_be").model_dump()
        raw["seo"] = {**raw["seo"], "canonical_origin": "https://autre-site.be"}
        with pytest.raises(ValueError, match="does not match domain"):
            SiteConfig(**raw)

    def test_no_origin_falls_back_to_a_relative_path_not_a_guess(self):
        raw = load_site("solar_be").model_dump()
        raw["domain"] = None
        # Refermer les portes du site lancé : une fixture sans domaine ne
        # peut être ni non-staging ni indexable, les validateurs refusent.
        raw["staging"] = True
        raw["seo"] = {**raw["seo"], "canonical_origin": None,
                      "allow_publication": False, "allow_indexing": False}
        config = SiteConfig(**raw)
        assert config.canonical_url("/prix") == "/prix"


class TestDomainDoesNotEnableIndexing:
    def test_the_configured_site_is_launched(self):
        """Publication ouverte le 2026-08-31 sur autorisation explicite du
        propriétaire — les deux décisions sont prises, ensemble."""
        config = load_site("solar_be")
        assert config.domain == DOMAIN
        assert config.staging is False
        assert config.seo.allow_indexing is True
        assert config.is_indexable is True

    def test_the_yaml_on_disk_records_the_launch(self):
        """Read the file, not the object: this is the line an edit would change."""
        raw = yaml.safe_load(Path("config/sites/solar_be.yaml").read_text())
        assert raw["seo"]["allow_indexing"] is True
        assert raw["staging"] is False

    def test_enabling_indexing_while_staging_is_still_refused(self):
        # Le mécanisme, épinglé sur une config remise explicitement en
        # préproduction : il ne dépend plus de l'état du fichier vivant.
        raw = load_site("solar_be").model_dump()
        raw["staging"] = True
        raw["seo"] = {**raw["seo"], "allow_indexing": True}
        with pytest.raises(ValueError, match="may not allow indexing"):
            SiteConfig(**raw)

    def test_launching_needs_two_deliberate_changes_not_one(self):
        """`staging: false` AND `allow_indexing: true`, together — rebuilt
        from the explicitly closed state, so the invariant outlives launch."""
        base = _with_validated_consents(load_site("solar_be").model_dump())
        base = {**base, "staging": True,
                "seo": {**base["seo"], "allow_indexing": False}}

        only_staging_off = {**base, "staging": False}
        assert SiteConfig(**only_staging_off).is_indexable is False

        launched = {**base, "staging": False,
                    "seo": {**base["seo"], "allow_indexing": True}}
        assert SiteConfig(**launched).is_indexable is True


class TestPublicationAndIndexingAreSeparateGates:
    """The distinction this site now depends on.

    A soft launch is: real URL, real visitors, no search engines. It only exists
    if "may be served" and "may be indexed" are different questions.
    """

    def test_the_site_may_serve_published_content_but_not_be_indexed(self):
        # La distinction, épinglée sur la variante soft-launch construite —
        # le site vivant a désormais les deux portes ouvertes.
        base = load_site("solar_be").model_dump()
        base["seo"] = {**base["seo"], "allow_indexing": False}
        config = SiteConfig(**base)
        assert config.is_publishable is True
        assert config.is_indexable is False

    def test_publication_does_not_require_indexability(self):
        base = load_site("solar_be").model_dump()
        base["seo"] = {**base["seo"], "allow_publication": True,
                       "allow_indexing": False}
        config = SiteConfig(**base)
        assert config.is_publishable and not config.is_indexable

    def test_indexing_still_requires_leaving_staging(self):
        """The stricter gate did not move."""
        base = _with_validated_consents(load_site("solar_be").model_dump())
        base = {**base, "staging": True,
                "seo": {**base["seo"], "allow_indexing": True}}
        with pytest.raises(ValueError, match="may not allow indexing"):
            SiteConfig(**base)

        launched = {**base, "staging": False}
        assert SiteConfig(**launched).is_indexable is True

    def test_indexing_cannot_be_enabled_without_publication(self):
        """Indexing a page nobody can fetch is incoherent."""
        base = _with_validated_consents(load_site("solar_be").model_dump())
        base["staging"] = False
        base["seo"] = {**base["seo"], "allow_publication": False,
                       "allow_indexing": True}
        with pytest.raises(ValueError, match="requires allow_publication"):
            SiteConfig(**base)

    def test_publication_requires_a_domain_to_serve_on(self):
        base = load_site("solar_be").model_dump()
        base["domain"] = None
        base["staging"] = True
        base["seo"] = {**base["seo"], "canonical_origin": None,
                       "allow_publication": True, "allow_indexing": False}
        with pytest.raises(ValueError, match="requires a domain"):
            SiteConfig(**base)

    def test_the_yaml_on_disk_is_launched(self):
        raw = yaml.safe_load(Path("config/sites/solar_be.yaml").read_text())
        assert raw["seo"]["allow_publication"] is True
        assert raw["seo"]["allow_indexing"] is True
        assert raw["staging"] is False


class TestTraefikRoutingIsPreparedNotApplied:
    def test_the_base_compose_publishes_nothing(self):
        """A routine `docker compose up -d` must not put the site on the internet."""
        compose = yaml.safe_load(BASE_COMPOSE.read_text())
        web = compose["services"]["seolead_web"]
        labels = web.get("labels") or {}
        assert not [k for k in labels if "traefik" in k.lower()]
        assert "traefik-public" not in (web.get("networks") or [])

    def test_the_base_compose_binds_the_port_to_loopback_only(self):
        compose = yaml.safe_load(BASE_COMPOSE.read_text())
        for mapping in compose["services"]["seolead_web"]["ports"]:
            assert str(mapping).startswith("127.0.0.1:"), \
                f"port {mapping} would be reachable from the internet"

    def test_the_overlay_exists_and_declares_both_hostnames(self):
        overlay = yaml.safe_load(OVERLAY.read_text())
        labels = overlay["services"]["seolead_web"]["labels"]
        rules = [v for k, v in labels.items() if k.endswith(".rule")]
        assert any(f"Host(`{DOMAIN}`)" == r for r in rules)
        assert any(f"Host(`www.{DOMAIN}`)" == r for r in rules)

    def test_www_redirects_permanently_to_the_apex(self):
        labels = yaml.safe_load(OVERLAY.read_text())["services"]["seolead_web"]["labels"]
        redirect = {k: v for k, v in labels.items() if "www-to-apex" in k}
        assert redirect, "no www→apex redirect configured"
        assert any(str(v).strip() == "true"
                   for k, v in redirect.items() if k.endswith(".permanent"))
        replacement = next(v for k, v in redirect.items()
                           if k.endswith(".replacement"))
        assert replacement.strip().startswith(f"https://{DOMAIN}/")

    def test_the_overlay_reuses_the_existing_resolver_and_network(self):
        """Not a second Traefik, not a second ACME account."""
        overlay = yaml.safe_load(OVERLAY.read_text())
        labels = overlay["services"]["seolead_web"]["labels"]
        resolvers = {v for k, v in labels.items() if k.endswith("certresolver")}
        assert resolvers == {"letsencrypt"}
        assert labels["traefik.docker.network"] == "traefik-public"
        assert overlay["networks"]["traefik-public"]["external"] is True
        assert "traefik" not in overlay["services"], \
            "the overlay must never define a Traefik instance"

    def test_preview_paths_require_edge_authentication(self):
        """The gap a public hostname opened, and why it is closed here.

        The application's preview token authenticates the SERVER to the API; it
        says nothing about who holds the browser. On loopback that gap was
        harmless — the only reachable client was the operator. On a public
        hostname it served unpublished content to anyone who guessed the path,
        which is exactly what publication state exists to prevent.
        """
        labels = yaml.safe_load(OVERLAY.read_text())["services"]["seolead_web"]["labels"]

        rule = labels["traefik.http.routers.monprojetsolaire-preview.rule"]
        assert "PathPrefix(`/preview`)" in rule
        # It must out-prioritise the catch-all apex router, or it never matches.
        apex_priority = int(labels.get(
            "traefik.http.routers.monprojetsolaire.priority", 0))
        preview_priority = int(
            labels["traefik.http.routers.monprojetsolaire-preview.priority"])
        assert preview_priority > apex_priority

        middlewares = labels[
            "traefik.http.routers.monprojetsolaire-preview.middlewares"]
        assert "monprojetsolaire-preview-auth" in middlewares
        assert any("basicauth.users" in k for k in labels)

    def test_the_edge_credential_is_not_committed(self):
        """The label interpolates an env var; the secret lives only in .env."""
        raw = OVERLAY.read_text()
        assert "${SEOLEAD_PREVIEW_BASICAUTH}" in raw
        # An apr1 hash or a plaintext pair would both be secrets in git.
        assert "$apr1$" not in raw
        assert "$$apr1$$" not in raw

    def test_the_overlay_forces_noindex_at_the_edge_too(self):
        labels = yaml.safe_load(OVERLAY.read_text())["services"]["seolead_web"]["labels"]
        tag = next(v for k, v in labels.items() if k.endswith("X-Robots-Tag"))
        assert "noindex" in tag and "nofollow" in tag

    def test_hsts_is_not_preloaded(self):
        """Preload is effectively irreversible and this site has served nothing."""
        labels = yaml.safe_load(OVERLAY.read_text())["services"]["seolead_web"]["labels"]
        assert not any("stsPreload" in k for k in labels)


class TestGenericSiteArchitectureSurvivesTheDomain:
    def test_a_second_site_still_loads_with_no_domain(self):
        """The isolation control must not have acquired a Solar assumption."""
        assert {"solar_be", "demo_generic"} <= set(available_sites())
        generic = load_site("demo_generic")
        assert generic.domain is None
        assert generic.seo.canonical_origin is None
        assert generic.is_indexable is False
        assert generic.canonical_url("/contact") == "/contact"

    def test_the_solar_hostname_appears_in_no_generic_code(self):
        """The domain lives in configuration. Anywhere else is a bug."""
        roots = [Path("app"), Path("web/app"), Path("web/components"),
                 Path("web/lib")]
        offenders = []
        for root in roots:
            for path in root.rglob("*"):
                if path.suffix not in {".py", ".ts", ".tsx"}:
                    continue
                if DOMAIN in path.read_text(encoding="utf-8"):
                    offenders.append(str(path))
        assert offenders == [], f"hard-coded hostname in {offenders}"

    def test_the_generic_site_carries_no_solar_vocabulary(self):
        blob = str(load_site("demo_generic").model_dump()).lower()
        for term in ("panneau", "solaire", "kwc", "belgique", "monprojetsolaire"):
            assert term not in blob
