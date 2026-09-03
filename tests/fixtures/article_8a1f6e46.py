"""Le cas d'épreuve : l'article 8a1f6e46 tel qu'il a été PUBLIÉ le 2026-08-31.

Chaque phrase et chaque affirmation ci-dessous est reprise au caractère près
du rapport `draft rejudge --explain` et du paquet f9534a41 rendus par l'hôte
le 2026-09-03. Ce n'est pas une reconstitution : c'est ce qui était en ligne.

Règle du propriétaire pour la tranche structurelle : chaque garde doit
ÉCHOUER sur cette version et PASSER sur la version révisée. Une garde qui
passe sur les deux ne prouve rien — d'où les deux jeux de phrases.
"""
from __future__ import annotations

# ── Ce que la page publiée disait ────────────────────────────────────────────

# Phrase A — trois paires d'arbitrage sur cinq. La queue reprend presque mot
# pour mot un passage étayé sur le tarif prosumer ; la tête affirme un chiffre
# qu'aucune source ne porte.
SENTENCE_A = ("En Wallonie, une installation standard est généralement "
              "rentabilisée au bout de 5 ans, même avec l'entrée en vigueur du "
              "tarif prosumer, qui vise à faire contribuer équitablement les "
              "utilisateurs du réseau.")

# Phrase B — deux paires. Ici l'arbitrage avait raison : le rival étayé porte
# les deux chiffres.
SENTENCE_B = ("Une installation typique peut couvrir la consommation annuelle "
              "d'une famille de 4 personnes, soit environ 5000 kWh.")

# La règle régionale énoncée sans région (jamais examinée par aucun contrôle).
SENTENCE_C = ("Les ménages qui ont installé des panneaux avant le 31 décembre "
              "2023 peuvent bénéficier du « compteur qui tourne à l'envers » "
              "jusqu'au 31 décembre 2030.")

# La réponse FAQ dont le chiffre EST étayé par une source officielle wallonne.
SENTENCE_D = ("Oui, la rentabilité des petites installations photovoltaïques "
              "est comprise entre 7,3% et 8,4% en Wallonie.")

PUBLISHED_BODY = "\n\n".join([
    "# Guide Complet sur la Rentabilité des Panneaux Solaires en Belgique",
    "## Les Notions de Base des Panneaux Solaires",
    "Les panneaux solaires photovoltaïques convertissent la lumière du soleil "
    "en électricité. " + SENTENCE_B,
    "## Questions Fréquemment Posées",
    "- **Est-il rentable d'investir dans des panneaux photovoltaïques ?** "
    + SENTENCE_D,
    "## Est-il Vraiment Rentable d'Installer des Panneaux Solaires ?",
    SENTENCE_A,
    "## Investir dans des Panneaux Photovoltaïques : Est-ce Rentable ?",
    "L'investissement dans des panneaux photovoltaïques est considéré comme "
    "rentable, surtout avec l'augmentation des prix de l'énergie. " + SENTENCE_C,
])

# ── Les affirmations du registre que ces phrases ont rencontrées ─────────────

def _claim(text, *, status, risk, category, region="BE", regionally=False,
           dated=False, reason="fixture 8a1f6e46"):
    return {"claim": text, "evidence_status": status, "claim_risk": risk,
            "category": category, "region": region,
            "regionally_determined": regionally, "has_dated_support": dated,
            "reason": reason}

# Le rival étayé qui a « gagné » la phrase A (paires 1, 2, 3) — un passage sur
# le MÉCANISME du tarif prosumer, sans aucun chiffre de rentabilité.
CLAIM_PROSUMER_MECHANISM = _claim(
    "Même à la suite de l'entrée en vigueur du tarif prosumer - qui a pour "
    "objectif de faire contribuer de manière équitable l'ensemble des "
    "utilisateurs du réseau de distribution d'électricité à l'entretien du "
    "réseau - une installation reste rentable.",
    status="SUPPORTED", risk="LOW", category="GENERAL", region="BE-WAL",
    dated=True)

# L'affirmation contestée de la paire 1 : « moins de 7 ans », NON étayée, et
# déjà plus prudente que le « 5 ans » publié.
CLAIM_ROI_UNDER_7 = _claim(
    "Mais malgré l'arrêt des primes de la Wallonie et l'arrivée du nouveau "
    "tarif Prosumer, une installation photovoltaïque en Belgique permet, en "
    "général, un retour sur investissement sur moins de 7 ans.",
    status="UNSUPPORTED", risk="HIGH", category="SUBSIDY", region="BE-BRU",
    regionally=True,
    reason="SUBSIDY claims require a OFFICIAL source; the best supporting "
           "source is SPECIALIST.")

CLAIM_PROFITABLE_WITHOUT_SUBSIDY = _claim(
    "Malgré l'arrêt des subsides et le tarif Prosumer, une installation "
    "solaire reste un placement rentable en Wallonie.",
    status="UNSUPPORTED", risk="HIGH", category="SUBSIDY", region="BE-WAL",
    regionally=True)

# Le rival étayé de la phrase B (paires 4 et 5) — il porte les deux chiffres.
CLAIM_FAMILY_5000 = _claim(
    "Soit de quoi couvrir la consommation moyenne annuelle d'une famille de 4 "
    "personnes : 5000 kWh.",
    status="SUPPORTED", risk="LOW", category="GENERAL", region="BE-WAL",
    dated=False)

# L'affirmation contestée de la phrase B : le bloc de calcul de la CWaPE.
CLAIM_CWAPE_CALCULATION = _claim(
    "Puissance électrique nette développable de l'installation de production : "
    "5 kWe Production : 1.000 kWh par kWe Consommation annuelle : 7.000 kWh "
    "Autoconsommation : 50 % Production annuelle : (1.000 kWh X 5 kWe) = "
    "5.000 kWh Autoconsommation annuelle : 50 % X 5.000 kWh = 2.500 kWh",
    status="PARTIALLY_SUPPORTED", risk="HIGH", category="GRID_RULE",
    region="BE-WAL", regionally=True)

# Les chiffres de rentabilité que le paquet porte RÉELLEMENT.
CLAIM_ROI_5_TO_7_SPECIALIST = _claim(
    "On estime aujourd'hui sa rentabilisation en 5 à 7 ans, permettant de "
    "produire gratuitement de l'électricité pour le ménage.",
    status="SUPPORTED", risk="LOW", category="GENERAL", region="BE",
    dated=False)   # SPECIALIST, non datée

CLAIM_ROI_7_TO_11_OFFICIAL = _claim(
    "En fonction de ces paramètres, un retour sur investissement est estimé "
    "entre 7 et 11 ans pour une installation de 0,8 kWc.",
    status="PARTIALLY_SUPPORTED", risk="HIGH", category="ROI", region="BE-WAL",
    regionally=True, dated=False)

CLAIM_YIELD_7_3_TO_8_4_OFFICIAL = _claim(
    "La rentabilité atteinte par les petites installations photovoltaïques "
    "est aujourd'hui comprise entre 7,3% et 8,4%.",
    status="SUPPORTED", risk="HIGH", category="ROI", region="BE-WAL",
    regionally=True, dated=True)   # energie.wallonie.be, UNDATED_CURRENT

CLAIM_REVERSE_METER_2030 = _claim(
    "Les installations mises en service avant le 31 décembre 2023 conservent "
    "le compteur qui tourne à l'envers jusqu'au 31 décembre 2030.",
    status="SUPPORTED", risk="HIGH", category="GRID_RULE", region="BE-WAL",
    regionally=True, dated=True)

PUBLISHED_CLAIMS = [
    CLAIM_PROSUMER_MECHANISM, CLAIM_ROI_UNDER_7,
    CLAIM_PROFITABLE_WITHOUT_SUBSIDY, CLAIM_FAMILY_5000,
    CLAIM_CWAPE_CALCULATION, CLAIM_ROI_5_TO_7_SPECIALIST,
    CLAIM_ROI_7_TO_11_OFFICIAL, CLAIM_YIELD_7_3_TO_8_4_OFFICIAL,
    CLAIM_REVERSE_METER_2030,
]

# ── La version révisée : ce que les sources permettent d'écrire ──────────────

REVISED_SENTENCE_A = (
    "En Wallonie, la rentabilité des petites installations photovoltaïques "
    "est comprise entre 7,3% et 8,4% selon le portail wallon de l'énergie, et "
    "le retour sur investissement varie selon la taille de l'installation et "
    "le taux d'autoconsommation.")

REVISED_SENTENCE_C = (
    "En Wallonie, les installations mises en service avant le 31 décembre "
    "2023 conservent le compteur qui tourne à l'envers jusqu'au 31 décembre "
    "2030.")

REVISED_BODY = "\n\n".join([
    "# Rentabilité des panneaux solaires en Belgique : ce que disent les sources",
    "## Les Notions de Base des Panneaux Solaires",
    "Les panneaux solaires photovoltaïques convertissent la lumière du soleil "
    "en électricité. En Wallonie, une installation typique peut couvrir la "
    "consommation annuelle d'une famille de 4 personnes, soit environ 5000 kWh.",
    "## Quelle rentabilité attendre ?",
    REVISED_SENTENCE_A,
    "## Le compteur qui tourne à l'envers",
    REVISED_SENTENCE_C,
])
