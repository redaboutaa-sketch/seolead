"""Lire un montant comme la source l'écrit (2026-09-10).

CE QUE LA PAGE PRIX AFFICHAIT
=============================
Deux montants faux, publiés du 13 août au 10 septembre, sur la page dont tout
l'objet commercial est d'annoncer des prix — et découverts le jour même où
elle est devenue indexable :

  « Comptez entre 1€ et 1,2€ par watt crête »   → affiché « 1 € – 12 € »
  « … budget entre 6.000 et 10.000 € »          → affiché « 10 000 € »

Le premier est un lecteur de nombres qui retirait tout ce qui n'était pas un
chiffre : « 1,2 » devenait 12. Un facteur dix.

Le second est une fourchette réduite à sa borne haute, parce que seule la
borne haute portait le symbole €. C'est le défaut du « 5 ans » tiré de
« 5 à 7 ans », de l'autre côté du mur : la règle des bornes existait pour les
affirmations du corps de l'article, jamais pour les montants extraits.

Aucun des deux n'était visible d'un test : la suite n'exerçait le lecteur que
sur des entiers propres.
"""
from __future__ import annotations

import pytest

from app.services.price_normalization import (PriceBasis, extract_price_context,
                                              plain)
from app.site.publication import BASES_NOT_DISPLAYED, _public_answer

# Les deux phrases telles que le paquet fa6e2a44 les porte.
WATT_CRETE = "Comptez entre 1€ et 1,2€ par watt crête installé."
KIT_3KWC = ("Globalement, pour un kit dont la puissance est de 3kWc, prévoyez "
            "un budget entre 6.000 et 10.000 € tout compris.")


class TestLesDeuxMontantsDeLaPagePrix:

    def test_la_virgule_decimale_ne_disparait_plus(self):
        context = extract_price_context(WATT_CRETE)
        assert context.amounts == (1.0, 1.2)
        assert context.basis is PriceBasis.PER_WP
        # Le défaut exact : 12 ne doit plus jamais sortir de cette phrase.
        assert 12 not in context.amounts

    def test_une_fourchette_dont_seule_la_borne_haute_porte_l_euro(self):
        context = extract_price_context(KIT_3KWC)
        assert context.amounts == (6000.0, 10000.0)
        assert context.is_range is True
        assert context.basis is PriceBasis.TOTAL


class TestLireUnNombreOuRefuser:

    @pytest.mark.parametrize("texte,attendu", [
        ("Entre 4.000 € et 14.000 € TVAC.", (4000.0, 14000.0)),
        ("Le panneau seul revient à 130 € – 170 €/m².", (130.0, 170.0)),
        ("Un budget de 1 234,56 € par installation.", (1234.56,)),
        ("Une installation à 1.234.567 € au total.", (1234567.0,)),
        ("Un total de 9 500 € pour l'installation.", (9500.0,)),
        ("Comptez 1.2 € par watt crête.", (1.2,)),
    ])
    def test_les_separateurs_sont_lus(self, texte, attendu):
        assert extract_price_context(texte).amounts == attendu

    def test_l_ambigu_est_refuse_plutot_que_devine(self):
        """« 1,500 » vaut 1,5 en français et 1500 en anglais. Aucune des deux
        lectures n'est sûre, et un montant faux sur une page de prix coûte
        plus cher qu'un montant absent."""
        assert extract_price_context("Un tarif de 1,500 € par panneau.") is None

    def test_un_montant_entier_reste_entier_en_json(self):
        assert plain(6000.0) == 6000 and isinstance(plain(6000.0), int)
        assert plain(1.2) == 1.2


class TestCeQueLaPageAffiche:

    def _answer(self, claim: str, **contexte) -> dict:
        """Une réponse telle que le brief la porte : le texte de la source, et
        un contexte de prix calculé le jour du brief."""
        return {"claim": claim, "category": "OBSERVED_PRICE_RANGE",
                "qualification": "a figure this source reports",
                "price_context": {"amounts": [1, 12], "currency": "EUR",
                                  "basis": "PER_M2", "vat_status": "UNKNOWN",
                                  "system_size_kwp": [], "is_range": True,
                                  "battery_included": None,
                                  "installation_included": None, **contexte}}

    def test_les_chiffres_sont_relus_depuis_le_texte_pas_repris_du_brief(self):
        """Le contexte gelé dit 1 et 12 ; la source dit 6.000 à 10.000. C'est
        la source qui fait foi."""
        answer = _public_answer(self._answer(KIT_3KWC))
        assert answer["amounts"] == [6000, 10000]
        assert answer["is_range"] is True

    def test_la_ligne_watt_crete_n_est_plus_affichee(self):
        """Décision du propriétaire du 2026-09-10 : retirée, pas corrigée."""
        assert "PER_WP" in BASES_NOT_DISPLAYED
        assert _public_answer(self._answer(WATT_CRETE)) is None

    def test_une_affirmation_illisible_est_retiree_pas_affichee_avec_l_ancien_chiffre(self):
        answer = self._answer("Une phrase sans le moindre montant.")
        assert _public_answer(answer) is None

    def test_le_texte_de_la_source_voyage_avec_le_chiffre(self):
        answer = _public_answer(self._answer(KIT_3KWC))
        assert answer["claim"] == KIT_3KWC
        assert answer["qualification"] == "a figure this source reports"
        # Jamais d'URL de source dans ce que le visiteur reçoit.
        assert "sources" not in answer and "http" not in str(answer)
