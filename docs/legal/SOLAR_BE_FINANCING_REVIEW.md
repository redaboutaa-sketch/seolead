# SOLAR_BE — Pack de revue juridique : discours « financement / sans apport »

**Statut : EN ATTENTE DE REVUE. Ce document ne contient aucune conclusion
juridique.** Il rassemble, pour un avocat, (1) le modèle d'affaires tel qu'il
doit être décrit par le propriétaire, (2) les formulations EXACTES que le site
servira, (3) les questions auxquelles la revue doit répondre, (4) la matrice
de verdicts à remplir. Tant que cette revue n'a pas eu lieu,
`offer.pending_legal_review: true` maintient la landing financement
non-publiable et hors sitemap — c'est le mécanisme, pas une politesse.

Rappel du contexte réglementaire à examiner (identifié dans
`docs/seo/AUDIT_SEO_AEO_GEO_2026-08-31.md` §3, à confirmer par le juriste) :
la publicité pour le crédit à la consommation en Belgique est encadrée
(Code de droit économique, livre VII) et impose des mentions obligatoires ;
le rôle exact du site (annonceur ? intermédiaire de crédit ? apporteur
d'affaires ?) conditionne les obligations.

## 1. Modèle d'affaires — à remplir par le propriétaire AVANT la revue

| Question | Réponse propriétaire |
|---|---|
| Qui vend l'installation (entité contractante avec le client) ? | ______ |
| Qui octroie le financement (organisme, agrément) ? | ______ |
| Quel est le rôle contractuel du site / de la marque (génération de demandes d'étude ? intermédiation ? démarchage ?) | ______ |
| Le site ou l'entité perçoit-il une rémunération liée au financement (commission, apport) ? | ______ |
| Des frais de dossier existent-ils, à quel montant, perçus par qui ? | ______ |
| Le « montage sans apport » est-il un crédit à la consommation, un crédit affecté, une location, un tiers-investissement ? | ______ |
| Y a-t-il démarchage téléphonique après soumission du formulaire ? | ______ |

## 2. Formulations exactes actuellement servies (copie verbatim)

Le juriste juge CES textes, pas des paraphrases. Source :
`web/app/panneaux-solaires-sans-apport/page.tsx` (landing),
`web/components/home/Sections.tsx` (accueil), `config/sites/solar_be.yaml`
(méta par défaut). Tout verdict de la matrice §4 référence un identifiant L-x.

**Méta / balisage (visibles dans les résultats de recherche et cités par les
moteurs de réponse) :**

- **L-1** (title) : « Installer des panneaux solaires sans apport en Belgique »
- **L-2** (meta description) : « Selon votre situation, un projet
  photovoltaïque peut être financé sans mobiliser votre épargne. Ce que
  “sans apport” veut vraiment dire, quels frais peuvent rester, et comment
  comparer mensualité et économies. »
- **L-3** (réponse directe, également en JSON-LD) : « Oui, sous conditions :
  selon votre profil et le montage de financement retenu, une installation
  photovoltaïque peut être réalisée en Belgique sans mobiliser d'épargne au
  départ. Des frais peuvent rester à votre charge ; les conditions exactes
  sont établies lors de l'étude. »

**Corps de la landing :**

- **L-4** (hero) : « Un projet solaire n'exige pas toujours une épargne
  disponible. Selon votre situation, différentes solutions de financement
  peuvent être étudiées — et cette page explique ce que “sans apport” veut
  vraiment dire, sans rien promettre que votre étude ne confirmerait pas. »
- **L-5** (§2) : « Le principe est celui de tout financement : un organisme
  avance le coût de l'installation, et vous le remboursez par mensualités sur
  une durée convenue. » + « Les conditions précises — organisme, taux,
  durée — dépendent du montage retenu et de votre profil. Elles vous sont
  présentées noir sur blanc lors de l'étude, avant toute décision. »
- **L-6** (§3) : « “Sans apport” signifie une chose précise : le montage ne
  vous demande pas de mobiliser une épargne au départ pour couvrir le prix de
  l'installation. Cela ne signifie pas “sans engagement” — un financement
  reste un contrat — ni “sans aucun frais” : selon le montage, certains frais
  peuvent rester à votre charge. »
- **L-7** (§4, état SANS fait validé — servi aujourd'hui) : « Selon le
  montage, des frais de dossier peuvent être demandés. Leur montant exact
  dépend de l'offre applicable à votre situation et vous est communiqué lors
  de l'étude, avant tout engagement — jamais après. La demande d'étude
  elle-même ne donne lieu à aucun paiement. »
- **L-8** (§4, état AVEC fait validé — servi seulement si le registre est
  publiable) : « Dans le montage proposé, des frais de dossier de [valeur du
  registre] € sont à prévoir. Ils vous sont confirmés par écrit avant tout
  engagement. »
- **L-9** (§6) : « Selon la combinaison de ces paramètres, les économies
  peuvent couvrir une partie — parfois l'essentiel — de la mensualité. Aucun
  de ces cas n'est garanti d'avance : c'est un résultat d'étude, pas une
  promesse de page web. »
- **L-10** (FAQ) : « Pas nécessairement. Selon votre situation et le montage
  de financement retenu, le projet peut être réalisé sans mobiliser votre
  épargne au départ. Certains frais peuvent rester à votre charge ; ils vous
  sont confirmés avant tout engagement, pendant l'étude. »
- **L-11** (FAQ autofinancement) : « Elle peut s'en approcher, sans que ce
  soit garanti : si les économies d'électricité mensuelles atteignent ou
  dépassent la mensualité du financement, l'effort net devient faible ou
  nul. […] c'est précisément ce que l'étude chiffre. »
- **L-12** (FAQ frais) : « Cela dépend du montage. Certains montages
  prévoient des frais de dossier ; leur montant exact vous est communiqué
  lors de l'étude, avant tout engagement. Aucun paiement n'est demandé pour
  l'étude elle-même. »

**Page d'accueil :**

- **L-13** (hero) : « Pas d'épargne à mobiliser ? Selon votre situation,
  différentes solutions de financement peuvent être étudiées. » (lien vers la
  landing — lien affiché seulement quand la landing est servie)
- **L-14** (FAQ accueil) : « Pas nécessairement. Selon votre situation et le
  montage de financement retenu, le projet peut être réalisé sans mobiliser
  votre épargne au départ — certains frais peuvent rester à votre charge, et
  ils vous sont confirmés avant tout engagement. »
- **L-15** (FAQ accueil, autofinancement) : « Elle peut s'en approcher, sans
  que ce soit garanti : si les économies d'électricité mensuelles atteignent
  la mensualité du financement, l'effort net devient faible ou nul. […] »
- **L-16** (méta description par défaut du site) : « […] Selon votre
  situation, des solutions de financement peuvent être étudiées. »

## 3. Questions au juriste (réponses écrites attendues)

1. Le site, dans le rôle décrit en §1, relève-t-il des règles de publicité
   du crédit à la consommation (CDE livre VII) pour L-1 à L-16 ? Si oui,
   lesquelles de ces formulations constituent une « publicité » au sens du
   texte ?
2. Le mot « sans apport » en title/H1 (L-1), sans mention adjacente, est-il
   admissible tel quel, ou exige-t-il une mention obligatoire visible sur la
   même page — et laquelle, mot pour mot ?
3. Quelles mentions obligatoires (taux, exemple représentatif,
   « Attention, emprunter de l'argent coûte aussi de l'argent », autre)
   doivent figurer sur la landing, dans quel ordre et quelle proximité ? À
   livrer comme liste verbatim → `offer.legal.mandatory_disclosures`.
4. L'affichage conditionnel des frais de dossier (L-7 sans montant, L-8 avec
   montant validé) est-il conforme ? Le montant, une fois publié, engage-t-il
   à une durée de validité affichée (le registre porte `valid_from`/
   `valid_until` par fait) ?
5. Les formulations d'« autofinancement approché » (L-9, L-11, L-15)
   franchissent-elles la ligne de la promesse de rendement ou de l'incitation
   au crédit ? Faut-il un encadré de mise en garde ?
6. La comparaison mensualité/économies (formule affichée sans chiffres,
   landing §5) appelle-t-elle une mention sur le caractère estimatif ?
7. Si un `worked_example` réel est publié (production, mensualité, économie
   d'UNE installation), quelles conditions : anonymisation, mention
   « exemple non contractuel », exigences d'« exemple représentatif » ?
8. Le nom de l'organisme financier doit-il être cité dans la publicité, ou
   au contraire ne PAS l'être tant qu'aucun contrat d'intermédiation ne
   l'autorise ?
9. Le formulaire (étape « financing_interest » : « Souhaitez-vous étudier un
   financement ? ») fait-il du site un intermédiaire de crédit de fait ?
   Quelles conséquences sur les mentions du formulaire et le consentement ?
10. Les FAQ en JSON-LD (reprises telles quelles par Google/moteurs de
    réponse, HORS de leur contexte de page) posent-elles un problème
    spécifique : une réponse FAQ citée seule reste-t-elle conforme ?
11. La page d'accueil (L-13 à L-15) porte-t-elle les mêmes obligations que la
    landing, ou le renvoi vers la landing suffit-il ?
12. Y a-t-il un délai de rétractation ou une information précontractuelle à
    mentionner dès le site (avant l'étude) ?

## 4. Matrice de verdicts — à remplir par le réviseur

Une ligne par formulation. Verdict : APPROVED (telle quelle) / CONDITIONAL
(avec la reformulation et/ou mention indiquées) / FORBIDDEN (à retirer).
Une ligne CONDITIONAL sans reformulation écrite compte comme FORBIDDEN.

| ID | Verdict | Reformulation exigée (verbatim) | Mention obligatoire associée | Base légale invoquée | Date | Réviseur |
|---|---|---|---|---|---|---|
| L-1 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-2 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-3 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-4 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-5 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-6 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-7 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-8 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-9 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-10 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-11 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-12 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-13 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-14 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-15 | ______ | ______ | ______ | ______ | ______ | ______ |
| L-16 | ______ | ______ | ______ | ______ | ______ | ______ |

## 5. Ce que la revue déclenche techniquement

Une fois la matrice remplie et les reformulations appliquées :

1. `offer.legal.mandatory_disclosures` reçoit les mentions verbatim de Q3 —
   la landing les rend telles quelles (bloc « Mentions légales »).
2. `offer.legal.reviewed_at` + `offer.legal.reviewer` sont renseignés.
3. `offer.pending_legal_review` passe à `false`.
4. La publiabilité exige EN PLUS la validation propriétaire
   (`status: validated` + `owner_validated_at`) — les deux verrous sont
   indépendants, aucun des deux ne suffit seul.

Aucun de ces champs n'est rempli par le développeur de sa propre initiative.
