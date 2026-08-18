"""Le routage public de monprojetsolaire.be, et ce qui l'a fait disparaître.

CE QUI S'EST PASSÉ
------------------
Le 2026-08-18, `https://monprojetsolaire.be` et `https://www.monprojetsolaire.be`
répondaient un 404 Traefik. Le DNS était juste (A et AAAA vers cette machine),
le certificat valide, l'application saine : `seolead_web` servait un 200 sur
`127.0.0.1:3100` et son healthcheck disait vrai.

Ce qui manquait, c'était la route. Le conteneur avait été recréé le 2026-08-17
à 08:56 par un `docker compose up -d` sans les deux `-f` : il est reparti sans
les étiquettes Traefik et sans le réseau `traefik-public`. Traefik n'avait donc
plus rien à faire correspondre à cet hôte, et répondait son propre 404.

La panne est silencieuse par construction : rien ne tombe, rien n'alerte, les
conteneurs restent « healthy ». C'est pour cela qu'elle mérite un test.

CE QUE CE FICHIER VÉRIFIE
--------------------------
Que l'overlay versionné décrit bien le routage attendu : les deux hôtes, le
port réel de l'application, la redirection www → apex, et l'en-tête `noindex`
au niveau du bord. Il lit le rendu de `docker compose config`, c'est-à-dire ce
que Docker appliquerait vraiment, plutôt que le texte du fichier.

Ce qu'il ne peut pas vérifier : que l'overlay soit effectivement chargé sur la
machine de production. Cela dépend de `COMPOSE_FILE` dans un `.env` non
versionné. `test_le_fichier_exemple_documente_compose_file` garde la trace
écrite ; la vérification vivante est le contrôle post-déploiement du runbook.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

RACINE = Path(__file__).resolve().parent.parent
OVERLAY = RACINE / "infra/traefik/docker-compose.public.yml"
BASE = RACINE / "docker-compose.yml"

APEX = "monprojetsolaire.be"
WWW = "www.monprojetsolaire.be"
PORT_APPLICATIF = "3100"

besoin_de_compose = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker absent — le rendu compose ne peut pas être demandé",
)


@pytest.fixture(scope="module")
def etiquettes() -> dict[str, str]:
    """Les étiquettes telles que Docker les appliquerait, pas telles qu'écrites.

    Le rendu résout l'interpolation et la fusion des deux fichiers ; c'est la
    seule forme qui prouve quelque chose sur le comportement réel.
    """
    env = dict(os.environ)
    # Valeur de banc : l'overlay interpole `${SEOLEAD_PREVIEW_BASICAUTH}`, et un
    # rendu ne doit pas dépendre du secret de production.
    env.setdefault("SEOLEAD_PREVIEW_BASICAUTH", "banc:$$apr1$$non$$secret")
    env.pop("COMPOSE_FILE", None)  # on nomme les fichiers explicitement ici

    rendu = subprocess.run(
        ["docker", "compose", "-f", str(BASE), "-f", str(OVERLAY), "config"],
        cwd=RACINE, capture_output=True, text=True, env=env,
    )
    if rendu.returncode != 0:
        pytest.skip(f"rendu compose indisponible : {rendu.stderr.strip()[:200]}")

    services = yaml.safe_load(rendu.stdout).get("services", {})
    return services.get("seolead_web", {}).get("labels", {}) or {}


@besoin_de_compose
class TestRoutageApex:
    def test_l_apex_a_une_regle_de_route(self, etiquettes):
        regle = etiquettes.get("traefik.http.routers.monprojetsolaire.rule", "")
        assert f"Host(`{APEX}`)" in regle, (
            "aucune règle Traefik pour l'apex : sans elle Traefik ne connaît pas "
            "l'hôte et répond son propre 404, quel que soit l'état de l'app.")

    def test_traefik_est_active_et_sur_le_bon_reseau(self, etiquettes):
        assert etiquettes.get("traefik.enable") == "true"
        assert etiquettes.get("traefik.docker.network") == "traefik-public", (
            "Traefik est configuré avec providers.docker.network=traefik-public ; "
            "un conteneur qui ne le rejoint pas est invisible pour lui.")

    def test_le_service_vise_le_port_reellement_ecoute(self, etiquettes):
        port = etiquettes.get(
            "traefik.http.services.monprojetsolaire.loadbalancer.server.port")
        assert port == PORT_APPLICATIF, (
            f"le service Traefik vise {port!r} alors que next-server écoute sur "
            f"{PORT_APPLICATIF}. Un port faux donne un 502, pas un 404 — mais il "
            f"casse tout autant.")


@besoin_de_compose
class TestRoutageWww:
    def test_www_a_sa_propre_regle(self, etiquettes):
        regle = etiquettes.get("traefik.http.routers.monprojetsolaire-www.rule", "")
        assert f"Host(`{WWW}`)" in regle

    def test_www_redirige_vers_l_apex_de_facon_permanente(self, etiquettes):
        pref = "traefik.http.middlewares.monprojetsolaire-www-to-apex.redirectregex"
        assert etiquettes.get(f"{pref}.permanent") == "true"
        remplacement = etiquettes.get(f"{pref}.replacement", "")
        assert remplacement.startswith(f"https://{APEX}/"), remplacement


@besoin_de_compose
class TestInvariantDIndexation:
    def test_le_bord_impose_noindex(self, etiquettes):
        """Publier une route ne publie pas le site.

        L'application envoie déjà `noindex` ; cet en-tête au bord le rend vrai
        même pour une réponse que l'application n'a pas produite, par exemple une
        page d'erreur Traefik. Restaurer le routage ne doit jamais rendre le site
        indexable — c'est une décision distincte, et elle appartient à l'owner.
        """
        cle = ("traefik.http.middlewares.monprojetsolaire-security-headers"
               ".headers.customResponseHeaders.X-Robots-Tag")
        valeur = etiquettes.get(cle, "")
        assert "noindex" in valeur and "nofollow" in valeur, valeur

    def test_le_prefixe_preview_reste_authentifie_au_bord(self, etiquettes):
        """Le jeton d'aperçu authentifie le serveur, pas le visiteur."""
        milieux = etiquettes.get(
            "traefik.http.routers.monprojetsolaire-preview.middlewares", "")
        assert "monprojetsolaire-preview-auth" in milieux
        priorite = etiquettes.get(
            "traefik.http.routers.monprojetsolaire-preview.priority")
        assert priorite == "100", (
            "sans priorité supérieure à celle de l'apex, la route d'aperçu ne "
            "gagne pas et le contenu non publié passe sans authentification.")


class TestTraceEcrite:
    def test_le_fichier_exemple_documente_compose_file(self):
        """La panne venait d'un fichier qu'il fallait penser à passer.

        `.env.example` est versionné ; le `.env` de production ne l'est pas. On
        ne peut donc pas tester la machine depuis ici — mais on peut garder la
        raison écrite à l'endroit où quelqu'un installera la prochaine.
        """
        texte = (RACINE / ".env.example").read_text(encoding="utf-8")
        assert "COMPOSE_FILE" in texte
        assert "docker-compose.public.yml" in texte

    def test_l_overlay_existe_et_reste_separe_de_la_base(self):
        assert OVERLAY.exists()
        base = BASE.read_text(encoding="utf-8")
        assert "monprojetsolaire.be" not in base, (
            "le routage public a été déplacé dans docker-compose.yml : un "
            "`up -d` ordinaire publierait alors le site sans décision.")
