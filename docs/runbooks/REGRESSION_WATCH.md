# Runbook — veille de régression nocturne

## Ce qu'elle répond

Deux questions, chaque nuit, sur chaque page publiée :

- **Porte** — le brouillon derrière cette page passerait-il la porte
  d'aujourd'hui ?
- **Dérive** — ce que la page sert est-il encore ce que les règles
  d'aujourd'hui rendraient du même brouillon ?

## Pourquoi elle existe

Une page publiée est un instantané **gelé** ; les règles, elles, avancent. Sept
correctifs ont été fusionnés entre le 1er et le 13 septembre 2026, et aucun n'a
touché ce qui était déjà en ligne.

Le cas d'épreuve : `/prix-panneaux-solaires-belgique` a affiché
« 1 € – 12 € par watt-crête » pour une source qui dit 1 à 1,2 €, et
« 10 000 € » pour une source qui dit 6 000 à 10 000 €, **du 13 août au 10
septembre**. Les deux ont été trouvés à la main, par hasard, en lisant un DTO
pour autre chose. Cette veille est ce qui les aurait nommés le lendemain.

## Lancer à la main

```bash
cd /opt/seolead
docker compose -f docker-compose.yml -f infra/traefik/docker-compose.public.yml \
    exec -T seolead_api seolead site watch
```

Sortie : `"status": "CLEAN"` ou `"status": "REGRESSIONS"` avec un constat par
page fautive — `kind` vaut `GATE`, `DRIFT` ou `ORPHAN`, et `detail` dit quoi
faire. `checked` compte les pages re-jugées ; `unwatched` liste celles qui
n'ont pas de brouillon derrière elles (pages écrites à la main : rien à
re-juger, et les compter comme des constats noierait les vrais).

## Installer la veille nocturne

```bash
crontab -e
# puis :
17 3 * * * /opt/seolead/scripts/regression_watch.sh >> /var/log/seolead-watch.log 2>&1
```

Le **code de sortie est l'alerte** : `0` tout va bien et cron reste muet ; `1`
au moins une page a régressé ; `2` l'API n'est pas démarrée, donc la veille
n'a rien pu conclure — un état qu'il faut distinguer de « tout va bien ».

## Que faire d'un constat

| `kind` | Ce que cela veut dire | Le geste |
|---|---|---|
| `DRIFT` | La page sert un rendu que les règles d'aujourd'hui ne produiraient plus | Relire le preview, `content fingerprint`, ré-approuver, `stage`, `publish` — section 3 quater de `CONTENT_PUBLICATION.md` |
| `GATE` | Le brouillon ne passerait plus la porte | Lire `detail` : recherches non résolues, approbation sans empreinte, garde en échec. Corriger la cause, puis republier |
| `ORPHAN` | La page est en ligne mais son brouillon n'existe plus | Rien ne peut être re-jugé ni recalculé : décider de republier depuis un nouveau brouillon, ou d'archiver la page |

## Ce qu'elle ne fait pas, et pourquoi

Elle n'écrit rien, ne publie rien, n'approuve rien, ne lève aucun
`pending_legal_review` et n'appelle aucun fournisseur — donc elle ne coûte
rien et ne peut rien casser.

Corriger reste un acte humain qui passe par la porte. L'article du 31 août a
coûté cher pour établir qu'une approbation nomme un rendu par son empreinte ;
une veille qui s'autoriserait à republier démonterait exactement ce garde-fou.
Elle dit, elle ne corrige pas.
