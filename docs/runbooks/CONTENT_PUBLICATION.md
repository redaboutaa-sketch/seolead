# Runbook — publishing a page

## 1. See what is waiting

```bash
seolead content list --status PENDING
```

Each item carries the gate: `factual_qa`, `seo_qa`, `approved`,
`no_external_links`, and the reasons for anything false.

## 2. Read it

```bash
seolead site preview-draft <draft-id>
```

or `http://localhost:3100/preview/draft/<draft-id>`.

Check specifically:

- every figure carries its basis and VAT status,
- nothing is described as a Belgian average unless the claim category says so,
- no outbound link,
- the CTA matches what the page can honestly offer.

## 3. Approve — a human act, on a render named by its fingerprint

```bash
seolead content fingerprint <draft-id>
seolead content approve <draft-id> --by "your name" --note "reviewed" \
    --fingerprint <sha256 from the line above>
```

QA passing is not approval, and nothing in this system will approve on its own.

**Plus d'approbation anticipée.** L'approbation porte sur un rendu identifié
par son empreinte, jamais sur une intention. L'empreinte est le SHA-256 de ce
que le visiteur lirait (titre, métas, sections, réponses prix, sources
rendues) ; la prévisualisation l'affiche (`fingerprint`), `content fingerprint`
la recalcule, et `content approve` refuse une empreinte qui n'est pas celle du
rendu tel qu'il est au moment de l'approbation. Toute modification ultérieure
du rendu (nouveau brouillon, re-jugement, nouvelles sources) change l'empreinte
et rend l'approbation caduque : la porte le dit, et il faut relire puis
ré-approuver. Une approbation donnée sur une version antérieure ne vaut rien
pour la suivante.

L'article `8a1f6e46` a été approuvé « rev 2 APPROVED » et publié le
2026-08-31 avec un « rentabilisée au bout de 5 ans » qu'aucune source ne
portait. C'est le cas d'épreuve de cette règle.

### Ce que la porte exige depuis le 2026-09-03

En plus des quatre conditions historiques (QA factuelle, QA SEO, approbation,
aucun lien sortant) :

- `advisory_qa` — aucune constatation de sévérité *high* du relecteur assisté
  sur SUBSIDY, ROI ou GRID_RULE ;
- `research_resolved` — chaque recherche autoritaire proposée par le
  planificateur a été lancée (`research authoritative-run --package <id>`)
  ou abandonnée avec une raison écrite
  (`research abandon-search --package <id> --query "…" --reason "…" --by …`) ;
- `approved_render` — l'approbation nomme l'empreinte du rendu courant.

## 3 bis. Refusé par les gardes ? Relancer le rédacteur, pas la recherche

```bash
seolead draft regenerate <brief-id>
```

Un brouillon refusé n'est pas une recherche refusée. Le paquet et le brief
existent ; cette commande demande un nouveau brouillon au rédacteur sur ce
même paquet, le juge par les mêmes gardes (factuelle, SEO, relecteur assisté
avec la liste des faits sourcés), et l'enregistre à côté des précédents avec
sa propre approbation `PENDING`. Elle ne crée pas de paquet : la résolution
des recherches proposées (`authoritative-run`, `abandon-search`) reste acquise.

`research authoritative-run --package <id>` ne lance que les recherches
encore dues ; `--all` relance tout le plan.

## 3 ter. Dater un document que la page ne date pas

Le bloc Sources affiche la date qu'une source énonce sur elle-même (ou sa
date de publication), sinon « non datée ». Un document daté sur sa couverture
mais dont la page ne porte aucune date lisible par le détecteur de fraîcheur
était affiché « non daté » : une valeur fausse affichée comme une mesure
(réserve du 2026-09-03 sur la fiche Bruxelles Environnement de 2013).

Une personne qui a lu la date sur le document la déclare dans
`config/sources/declared_dates.yaml`, avec sa provenance :

```yaml
documents:
  - url: https://document.environnement.brussels/…/fiche.pdf   # URL exacte de la preuve
    date: 2013            # AAAA, AAAA-MM ou AAAA-MM-JJ, rien d'autre
    declared_by: reda     # qui a lu la date
    declared_on: 2026-09-03
    basis: date imprimée sur la couverture du PDF
```

Une entrée sans `basis`, `declared_by` ou `declared_on` fait échouer le
chargement ; une date qui n'a pas la forme d'une date aussi. La date déclarée
ne remplace jamais une date énoncée par la page (celle-ci gagne) et voyage
jusqu'au visiteur avec sa base : la page dit « document daté de 2013 », pas
« consultée, datée du 2013 ». Le fichier est dans l'image API : rebuild, puis
nouveau brouillon ou re-jugement → nouvelle empreinte → relecture et
ré-approbation.

## 4. Stage

```bash
seolead content stage <draft-id> --site solar_be
```

Refuses with the reason if any gate condition fails. Produces a `STAGED` snapshot
with `noindex` forced on, and prints its preview path.

## 5. Publish — only after the launch decision

```bash
seolead content publish <content-id> --site solar_be
```

**This refuses while `config/sites/solar_be.yaml` has no domain, `staging: true`,
or `allow_indexing: false`.** That is intended: publishing is blocked until the
owner opens the launch gate.

## Rolling back

Publish a new version — the previous live row is archived automatically. Nothing
is deleted, so a page's history stays readable.
