"""Le cas d'épreuve : l'article 8a1f6e46 tel qu'il a été PUBLIÉ le 2026-08-31.

Le corps est celui de `draft show 8a1f6e46-8b0c-4603-8bcf-1ced0a4e7534
--body`, rendu par l'hôte le 2026-09-03. Les affirmations sont les 199 du
paquet f9534a41, réduites aux champs que les gardes lisent (aucune URL),
dans `package_f9534a41_claims.jsonl` — texte tronqué à 260 caractères par
l'export, sauf le passage prosumer, rétabli en entier depuis un second
export parce que c'est lui qui a tout changé.

Une première version de ce fichier (matin du 2026-09-03) avait été
reconstruite à partir du rapport `--explain`, qui tronque les affirmations
à 200 caractères ; les 46 derniers caractères du passage prosumer — ceux
qui disent « … sachez qu'une installation standard est rentabilisée au bout
de 5 ans » — avaient été complétés de mémoire, sans le chiffre. Le
diagnostic « un retour sur investissement qu'aucune source ne porte » en
est sorti, et il était faux : le portail wallon de l'énergie le porte, en
Wallonie, sur une page non datée présentée comme en vigueur. Ce qui reste
vrai de l'article publié se lit dans les gardes : la règle 2023/2030 sans
région, aucune source ni date affichée, aucune fourchette par région et
par taille.

Règle du propriétaire pour la tranche structurelle : chaque garde doit
échouer sur cette version et passer sur la version révisée ; une garde qui
passe sur les deux ne prouve rien. Là où une garde passe sur l'article
publié parce que son chiffre était sourcé, le test le dit et prouve la
garde sur la mutation la plus proche — jamais sur une fixture arrangée.
"""
from __future__ import annotations

import json
import pathlib

# ── Ce que la page publiée disait — au caractère près ────────────────────────

PUBLISHED_TITLE = "Guide Complet sur la Rentabilité des Panneaux Solaires en Belgique"
PUBLISHED_META_TITLE = "Rentabilité des Panneaux Solaires en Belgique"
PUBLISHED_META_DESCRIPTION = ("Découvrez la rentabilité des panneaux solaires en "
                              "Belgique et comment elle varie selon les régions.")

# La phrase de rentabilité. Portée par le portail wallon (OFFICIEL, BE-WAL).
SENTENCE_A = ("En Wallonie, une installation standard est généralement "
              "rentabilisée au bout de 5 ans, même avec l'entrée en vigueur du "
              "tarif prosumer, qui vise à faire contribuer équitablement les "
              "utilisateurs du réseau.")
# Portée par une source commerciale non datée.
SENTENCE_B = ("Une installation typique peut couvrir la consommation annuelle "
              "d'une famille de 4 personnes, soit environ 5000 kWh.")
# La règle wallonne énoncée sans région : le seul défaut déterministe.
SENTENCE_C = ("Les ménages qui ont installé des panneaux avant le 31 décembre "
              "2023 peuvent bénéficier du « compteur qui tourne à l'envers » "
              "jusqu'au 31 décembre 2030.")
# Portée par le portail wallon, datée.
SENTENCE_D = ("Oui, la rentabilité des petites installations photovoltaïques "
              "est comprise entre 7,3% et 8,4% en Wallonie.")
# « sans soutien public » — portée textuellement par une source OFFICIELLE.
SENTENCE_E = ("De plus, les petites installations sont jugées intéressantes "
              "même sans soutien public, surtout face à la hausse des prix de "
              "l'énergie.")
SENTENCE_F = ("Oui, surtout en Wallonie où les installations sont rentables "
              "même sans soutien public.")
# Le ménage bruxellois — Bruxelles Environnement, document de 2013.
SENTENCE_G = ("Par exemple, un ménage bruxellois moyen de 2 à 3 personnes "
              "consommant environ 3000 à 3500 kWh par an peut s'attendre à ce "
              "qu'une installation de 8 m² fournisse environ un tiers de son "
              "électricité totale nécessaire.")

PUBLISHED_BODY = f"""# Guide Complet sur la Rentabilité des Panneaux Solaires en Belgique

## Introduction
Ce guide a pour objectif d'informer les propriétaires de maisons individuelles et les petites entreprises en Belgique sur la rentabilité des panneaux solaires. À la fin de ce guide, vous aurez une meilleure compréhension des facteurs influençant cette rentabilité et des erreurs à éviter.

## Les Notions de Base des Panneaux Solaires
Les panneaux solaires photovoltaïques convertissent la lumière du soleil en électricité. {SENTENCE_B}

## Facteurs Influant sur la Rentabilité
La rentabilité des panneaux solaires dépend de plusieurs éléments, notamment la taille de l'installation, l'orientation du toit, et le coût de l'électricité. En Wallonie, malgré la fin du système de compensation, l'installation de panneaux solaires reste rentable. {SENTENCE_E}

## Erreurs Fréquentes à Éviter
Les propriétaires doivent éviter des erreurs telles que ne pas vérifier l'orientation de leur toit ou ne pas estimer correctement leur consommation d'électricité. Une carte solaire est disponible pour connaître le potentiel de chaque toit à Bruxelles.

## Analyse de Rentabilité selon Votre Situation
La rentabilité de votre installation dépendra de votre consommation personnelle. {SENTENCE_G}

## Questions Fréquemment Posées
1. **Est-il vraiment rentable d'installer des panneaux solaires ?** {SENTENCE_F}
2. **Est-il rentable d'investir dans des panneaux photovoltaïques ?** {SENTENCE_D}
3. **Est-il encore intéressant de mettre des panneaux photovoltaïques ?** Oui, l'investissement reste pertinent face à l'augmentation des coûts de l'énergie.
4. **Quel est le rendement d'un panneau solaire en hiver ?** Les rendements peuvent varier, mais il est important de prendre en compte la saisonnalité lors de l'évaluation de la rentabilité.

## Est-il Vraiment Rentable d'Installer des Panneaux Solaires ?
{SENTENCE_A}

## Investir dans des Panneaux Photovoltaïques : Est-ce Rentable ?
L'investissement dans des panneaux photovoltaïques est considéré comme rentable, surtout avec l'augmentation des prix de l'énergie. {SENTENCE_C}

## Est-il Encore Intéressant de Mettre des Panneaux Photovoltaïques ?
Oui, même après les changements réglementaires, l'installation de panneaux solaires reste un choix judicieux pour les propriétaires en Wallonie, surtout en tenant compte de la hausse des coûts de l'énergie.

Pour en savoir plus sur la rentabilité des panneaux solaires et recevoir des conseils personnalisés, n'hésitez pas à **recevoir le guide complet**.
"""

# ── Les 199 affirmations du paquet f9534a41 ──────────────────────────────────

_CLAIMS_PATH = pathlib.Path(__file__).with_name("package_f9534a41_claims.jsonl")


def _load_claims() -> list[dict]:
    out = []
    for line in _CLAIMS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out.append({"claim": row["x"], "evidence_status": row["s"],
                    "claim_risk": row["r"], "category": row["c"],
                    "region": row["g"], "regionally_determined": row["d"],
                    "has_dated_support": row["t"],
                    "best_source_quality": row["q"],
                    "reason": "paquet f9534a41"})
    return out


PUBLISHED_CLAIMS: list[dict] = _load_claims()


def _find(prefix: str) -> dict:
    for claim in PUBLISHED_CLAIMS:
        if claim["claim"].startswith(prefix):
            return claim
    raise LookupError(prefix)


# Le passage officiel qui porte le « 5 ans » (OFFICIEL, BE-WAL, en vigueur).
CLAIM_PROSUMER_5_ANS = _find("Même à la suite de l'entrée en vigueur")
# Le même passage tel que le rapport --explain l'avait montré (200 caractères)
# et tel que la première fixture l'avait complété : SANS le chiffre. Gardé
# comme mutation, parce que c'est l'erreur qui a coûté une journée.
CLAIM_PROSUMER_MECHANISM_TRUNCATED = {
    **CLAIM_PROSUMER_5_ANS,
    "claim": ("Même à la suite de l'entrée en vigueur du tarif prosumer - qui a "
              "pour objectif de faire contribuer de manière équitable "
              "l'ensemble des utilisateurs du réseau de distribution "
              "d'électricité à l'entretien du réseau - une installation reste "
              "rentable."),
}
CLAIM_ROI_UNDER_7 = _find("Mais malgré l’arrêt des primes de la Wallonie")
CLAIM_PROFITABLE_WITHOUT_SUBSIDY = _find("Malgré l’arrêt des subsides")
CLAIM_FAMILY_5000 = _find("Soit de quoi couvrir la consommation moyenne")
CLAIM_CWAPE_CALCULATION = _find("Puissance électrique nette développable")
CLAIM_ROI_5_TO_7_SPECIALIST = _find("On estime aujourd’hui sa rentabilisation")
CLAIM_ROI_7_TO_11_OFFICIAL = _find("En fonction de ces paramètres, un retour")
CLAIM_YIELD_7_3_TO_8_4_OFFICIAL = _find("La rentabilité atteinte par les petites")
CLAIM_REVERSE_METER_2030 = _find("À noter que les ménages qui ont installé")
CLAIM_SMALL_WITHOUT_SUPPORT_OFFICIAL = _find("Bref, les petites installations")
CLAIM_BRUSSELS_HOUSEHOLD = _find("Ainsi, pour un ménage bruxellois moyen")
CLAIM_BRUSSELS_MAX_7 = _find("Votre installation est ainsi amortie")
CLAIM_COMPENSATION_END_COMMERCIAL = _find("Malgré la fin du système de compensation")

# Les alias de la première fixture, conservés pour les tests qui les nomment.
CLAIM_PROSUMER_MECHANISM = CLAIM_PROSUMER_5_ANS


def claims_without(*excluded: dict) -> list[dict]:
    return [c for c in PUBLISHED_CLAIMS if not any(c is e for e in excluded)]


# ── La version révisée : ce que les sources permettent d'écrire ──────────────

# Attribuée et datée (ou non datée, dit comme tel). Le « 7 à 11 ans pour
# 0,8 kWc » n'y figure pas : dans le paquet d'août il n'est que PARTIELLEMENT
# étayé, et la garde le refuse — à raison — tant qu'un paquet ne l'établit pas.
REVISED_SENTENCE_A = (
    "En Wallonie, selon le portail wallon de l'énergie (page non datée), une "
    "installation standard est rentabilisée au bout de 5 ans, et la "
    "rentabilité des petites installations y est comprise entre 7,3% et 8,4%.")

REVISED_SENTENCE_C = (
    "En Wallonie, les ménages qui ont installé des panneaux avant le 31 "
    "décembre 2023 peuvent bénéficier du « compteur qui tourne à l'envers » "
    "jusqu'au 31 décembre 2030.")

REVISED_BODY = PUBLISHED_BODY.replace(SENTENCE_C, REVISED_SENTENCE_C).replace(
    SENTENCE_A, REVISED_SENTENCE_A)
assert REVISED_BODY != PUBLISHED_BODY
