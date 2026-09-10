"""Une seule ligne vivante par adresse — et l'ordre des écritures (2026-09-10).

CE QUE LA PRODUCTION A TROUVÉ
=============================
La republication de `/prix-panneaux-solaires-belgique` est morte sur
`uq_pub_live`, l'index partiel qui interdit deux lignes PUBLISHED à la même
adresse. `publish_content` archivait bien l'ancienne ligne — mais laissait les
deux écritures en attente dans le MÊME flush, et SQLAlchemy ordonne les UPDATE
d'une même table par clé primaire, pas par ordre d'écriture. Les clés sont des
UUID aléatoires : une publication sur deux environ émettait « la nouvelle
devient PUBLISHED » avant « l'ancienne devient ARCHIVED ».

POURQUOI AUCUN TEST NE L'AVAIT VU
=================================
`uq_pub_live` n'existait que dans la migration 0005. La suite construit son
schéma avec `Base.metadata.create_all`, donc l'index n'a jamais été créé en
test : chaque test tournait sur une base capable de porter deux lignes
vivantes. Le garde était invisible à la seule chose qui aurait pu le vérifier.
Il est maintenant déclaré dans le modèle, et ce fichier le prouve.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.enums import PublicationState
from app.models import PublishedContent, Site, Vertical
from app.site.config import load_site
from app.site.publication import publish_content

SLUG = "prix-panneaux-solaires-belgique"


async def _site(session) -> Site:
    vertical = Vertical(code="SOLAR_BE", name="Solar Belgium", market="BE",
                        default_language="fr", active=True)
    session.add(vertical)
    await session.flush()
    site = Site(vertical_id=vertical.id, name="solar_be", domain=None,
                market="BE", default_language="fr", status="PLANNED")
    session.add(site)
    await session.flush()
    return site


def _row(site, *, id_: uuid.UUID, version: int, state: PublicationState,
         noindex: bool) -> PublishedContent:
    return PublishedContent(
        id=id_, site_id=site.id, locale="fr", slug=SLUG, version=version,
        content_type="ARTICLE", state=state.value, title="Prix des panneaux",
        sections=[], price_evidence={}, cta={}, qa_provenance={},
        canonical_path=f"/{SLUG}", noindex=noindex)


async def _publier(session, site, *, ancien: uuid.UUID, nouveau: uuid.UUID):
    """Un instantané vivant, un instantané en scène, puis la mise en ligne."""
    session.add(_row(site, id_=ancien, version=1,
                     state=PublicationState.PUBLISHED, noindex=True))
    neuf = _row(site, id_=nouveau, version=2, state=PublicationState.STAGED,
                noindex=True)
    session.add(neuf)
    await session.flush()
    return await publish_content(session, snapshot=neuf,
                                 config=load_site("solar_be"))


@pytest.mark.asyncio
class TestLOrdreDesEcritures:

    async def test_publier_quand_la_nouvelle_cle_precede_l_ancienne(
            self, session):
        """Le cas qui échouait : la clé de la nouvelle ligne trie AVANT celle
        de l'ancienne, donc son UPDATE partait en premier."""
        site = await _site(session)
        neuf = await _publier(
            session, site,
            ancien=uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
            nouveau=uuid.UUID("00000000-0000-4000-8000-000000000001"))
        assert neuf.state == PublicationState.PUBLISHED.value

    async def test_publier_quand_la_nouvelle_cle_suit_l_ancienne(self, session):
        """Le cas qui passait par chance. Il doit continuer de passer."""
        site = await _site(session)
        neuf = await _publier(
            session, site,
            ancien=uuid.UUID("00000000-0000-4000-8000-000000000001"),
            nouveau=uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"))
        assert neuf.state == PublicationState.PUBLISHED.value

    @pytest.mark.parametrize("ordre", ["avant", "apres"])
    async def test_une_seule_ligne_reste_vivante(self, session, ordre):
        site = await _site(session)
        petit = uuid.UUID("00000000-0000-4000-8000-000000000001")
        grand = uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
        ancien, nouveau = (grand, petit) if ordre == "avant" else (petit, grand)
        await _publier(session, site, ancien=ancien, nouveau=nouveau)

        vivantes = (await session.execute(
            select(PublishedContent).where(
                PublishedContent.slug == SLUG,
                PublishedContent.state == PublicationState.PUBLISHED.value)
        )).scalars().all()
        assert len(vivantes) == 1
        assert vivantes[0].id == nouveau
        archivee = await session.get(PublishedContent, ancien)
        assert archivee.state == PublicationState.ARCHIVED.value

    async def test_le_noindex_du_lancement_en_douceur_est_leve(self, session):
        """Ce que la republication vient chercher : `noindex` recalculé depuis
        l'état courant du site, qui est indexable."""
        site = await _site(session)
        assert load_site("solar_be").is_indexable
        neuf = await _publier(
            session, site,
            ancien=uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
            nouveau=uuid.UUID("00000000-0000-4000-8000-000000000001"))
        assert neuf.noindex is False


class TestLeGardeEstVisibleDesTests:

    def test_l_index_partiel_est_dans_les_metadonnees(self):
        """Un garde qui n'existe que dans une migration n'est vérifié par
        aucun test. Celui-ci doit voyager avec le modèle."""
        index = {i.name: i for i in PublishedContent.__table__.indexes}
        assert "uq_pub_live" in index, (
            "uq_pub_live doit être déclaré dans le modèle, sinon "
            "`create_all` ne le crée pas et la suite ne le teste jamais")
        vivant = index["uq_pub_live"]
        assert vivant.unique is True
        assert [c.name for c in vivant.columns] == ["site_id", "locale", "slug"]

    @pytest.mark.asyncio
    async def test_deux_lignes_vivantes_sont_refusees_par_la_base(self, session):
        """Le garde lui-même, prouvé sur la base des tests."""
        from sqlalchemy.exc import IntegrityError

        site = await _site(session)
        session.add(_row(site, id_=uuid.uuid4(), version=1,
                         state=PublicationState.PUBLISHED, noindex=False))
        await session.flush()
        session.add(_row(site, id_=uuid.uuid4(), version=2,
                         state=PublicationState.PUBLISHED, noindex=False))
        with pytest.raises(IntegrityError):
            await session.flush()
