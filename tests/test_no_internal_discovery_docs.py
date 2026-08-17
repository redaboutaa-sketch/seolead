"""Internal infrastructure documentation must not be committed to this repository.

This repository is public. Documents that map the live server — Traefik routing,
container names, `/opt` paths, PostgreSQL topology — were published here until
2026-08-17 and have been moved to the owner's private operational repository.

The move is only half the fix. The other half is this file, because the way that
material arrived was ordinary: someone wrote a careful report of what a gate had
just discovered, and committed it alongside the code it described. Nothing about
that felt like a disclosure at the time, and nothing would feel like one the next
time either. So the rule is written down here rather than remembered.

The guard is deliberately narrow. It matches names, not prose, and it says
nothing about ordinary runbooks: a public project is allowed to document how to
run itself, and a rule that forbade `docker compose` in the docs would be
abandoned within a week. It catches the artifacts that have a stable name — a
discovery report, a VPS survey, anything under `docs/discovery/` — and leaves
judgement for everything else.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Exact paths that were privatised on 2026-08-17. Named individually so that a
# revert, a cherry-pick or a restored backup is caught by name and not only by
# the patterns below.
PRIVATISED = (
    "SEO_LEAD_FACTORY_DISCOVERY_REPORT.md",
    "docs/discovery/VPS_DISCOVERY.md",
    "MONPROJETSOLAIRE_DOMAIN_INTEGRATION_REPORT.md",
)

# Naming conventions for the same class of artifact. These are the shapes this
# project actually uses when it writes a survey of the live infrastructure.
MOTIFS_INTERNES = (
    re.compile(r"(^|/)[A-Z0-9_]*DISCOVERY[A-Z0-9_]*\.md$"),
    re.compile(r"(^|/)[A-Z0-9_]*VPS[A-Z0-9_]*\.md$"),
    # Un rapport d'intégration de domaine relève DNS, routage et TLS sur le
    # serveur vivant. `test_le_garde_reconnait_bien_les_noms_privatises` a
    # attrapé l'oubli de ce motif : les deux autres ne mentionnent ni DISCOVERY
    # ni VPS, et le troisième document serait revenu sans bruit.
    re.compile(r"(^|/)[A-Z0-9_]*DOMAIN_INTEGRATION[A-Z0-9_]*\.md$"),
    re.compile(r"^docs/discovery/(?!README\.md$).+$"),
)

# `docs/discovery/README.md` is the public-safe placeholder that replaced the
# directory's contents. It is the one file allowed to live there.
AUTORISES = frozenset({"docs/discovery/README.md"})


def fichiers_suivis() -> list[str]:
    """The tracked tree, asked of git rather than walked from disk.

    Walking would also see untracked scratch files, and failing a test for a file
    the author never offered to commit teaches people to distrust the test.
    """
    sortie = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ligne for ligne in sortie.stdout.splitlines() if ligne]


@pytest.fixture(scope="module")
def suivis() -> list[str]:
    return fichiers_suivis()


class TestDocumentsPrivatises:
    def test_aucun_document_privatise_n_est_revenu(self, suivis: list[str]):
        revenus = sorted(set(PRIVATISED) & set(suivis))
        assert not revenus, (
            "Ces documents ont été retirés du dépôt public le 2026-08-17 parce "
            "qu'ils cartographient l'infrastructure. Ils vivent désormais dans "
            "le dépôt privé, sous docs/operations/seolead/. S'ils sont "
            f"réapparus ici, c'est une régression, pas une mise à jour : {revenus}"
        )

    def test_le_remplacement_public_est_en_place(self, suivis: list[str]):
        assert "docs/discovery/README.md" in suivis

    def test_le_remplacement_ne_decrit_aucune_topologie(self):
        texte = (REPO / "docs/discovery/README.md").read_text(encoding="utf-8")
        # Le remplaçant explique qu'il n'y a rien à voir. S'il se met à nommer
        # des conteneurs ou des chemins de serveur, il est devenu le problème
        # qu'il remplace.
        for interdit in ("/opt/", "traefik", "platform_api", "seolead_api", "5432"):
            assert interdit.lower() not in texte.lower(), (
                f"Le remplaçant public mentionne « {interdit} »."
            )


class TestConventionDeNommage:
    def test_aucun_artefact_de_decouverte_interne_n_est_suivi(
        self, suivis: list[str]
    ):
        fautifs = sorted(
            chemin
            for chemin in suivis
            if chemin not in AUTORISES
            and any(motif.search(chemin) for motif in MOTIFS_INTERNES)
        )
        assert not fautifs, (
            "Ces fichiers portent le nom d'un relevé d'infrastructure interne. "
            "Ce dépôt est public : un tel document appartient au dépôt privé, "
            f"sous docs/operations/seolead/. Fichiers : {fautifs}"
        )

    def test_le_garde_reconnait_bien_les_noms_privatises(self):
        # Sans cette vérification, une expression rationnelle cassée rendrait le
        # garde silencieusement inutile — il passerait, et ne protégerait rien.
        for chemin in PRIVATISED:
            assert any(motif.search(chemin) for motif in MOTIFS_INTERNES), chemin

    @pytest.mark.parametrize(
        "chemin",
        [
            "README.md",
            "docs/ARCHITECTURE.md",
            "docs/runbooks/LOCAL_PIPELINE.md",
            "docs/runbooks/MONPROJETSOLAIRE_DEPLOYMENT.md",
            "docs/runbooks/MONPROJETSOLAIRE_DNS.md",
            "docs/site/STAGING.md",
            "docs/discovery/README.md",
            "PHASE2_IMPLEMENTATION_REPORT.md",
            "PHASE5A_LEAD_DESTINATION_REPORT.md",
            "PHASE3_4_PRICE_EVIDENCE_REPORT.md",
        ],
    )
    def test_la_documentation_publique_ordinaire_reste_permise(self, chemin: str):
        # Le garde doit rester étroit. Un runbook public est légitime ; c'est la
        # cartographie du serveur qui ne l'est pas.
        if chemin in AUTORISES:
            return
        assert not any(motif.search(chemin) for motif in MOTIFS_INTERNES), (
            f"Le garde est trop large : il rejetterait {chemin}."
        )


class TestAucunLienPublic:
    def test_aucun_fichier_suivi_ne_pointe_vers_un_document_privatise(
        self, suivis: list[str]
    ):
        noms = [Path(chemin).name for chemin in PRIVATISED]
        fautifs: list[str] = []
        for chemin in suivis:
            if chemin == "tests/test_no_internal_discovery_docs.py":
                continue  # ce fichier cite les noms, c'est son travail
            fichier = REPO / chemin
            try:
                texte = fichier.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(nom in texte for nom in noms):
                fautifs.append(chemin)
        assert not fautifs, (
            "Ces fichiers citent un document privatisé. Un lien mort dans un "
            "dépôt public nomme quand même la chose qu'on a retirée : "
            f"{fautifs}"
        )
