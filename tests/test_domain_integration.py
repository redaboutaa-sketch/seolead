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
        raw["seo"] = {**raw["seo"], "canonical_origin": bad}
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
        raw["seo"] = {**raw["seo"], "canonical_origin": None}
        config = SiteConfig(**raw)
        assert config.canonical_url("/prix") == "/prix"


class TestDomainDoesNotEnableIndexing:
    def test_the_configured_site_is_still_not_indexable(self):
        config = load_site("solar_be")
        assert config.domain == DOMAIN
        assert config.staging is True
        assert config.seo.allow_indexing is False
        assert config.is_indexable is False, \
            "acquiring a domain must not, by itself, make a site indexable"

    def test_the_yaml_on_disk_has_indexing_off(self):
        """Read the file, not the object: this is the line an edit would change."""
        raw = yaml.safe_load(Path("config/sites/solar_be.yaml").read_text())
        assert raw["seo"]["allow_indexing"] is False
        assert raw["staging"] is True

    def test_enabling_indexing_while_staging_is_still_refused(self):
        raw = load_site("solar_be").model_dump()
        raw["seo"] = {**raw["seo"], "allow_indexing": True}
        with pytest.raises(ValueError, match="may not allow indexing"):
            SiteConfig(**raw)

    def test_launching_needs_two_deliberate_changes_not_one(self):
        """`staging: false` AND `allow_indexing: true`, together."""
        base = load_site("solar_be").model_dump()

        only_staging_off = {**base, "staging": False}
        assert SiteConfig(**only_staging_off).is_indexable is False

        launched = {**base, "staging": False,
                    "seo": {**base["seo"], "allow_indexing": True}}
        assert SiteConfig(**launched).is_indexable is True


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
