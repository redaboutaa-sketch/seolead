# SEO technical foundation

## The publication gate, expressed three ways

| Surface | While not indexable | When launched |
|---|---|---|
| `robots.txt` | `User-Agent: * / Disallow: /` | allow, with `/preview/` and `/api/` disallowed |
| page `<meta robots>` | `noindex, nofollow, nocache` | `index, follow` |
| `sitemap.xml` | empty | PUBLISHED URLs only |

"Indexable" is three independent conditions — a domain is set, `staging` is false,
and `seo.allow_indexing` is true — because a single flag is one accidental commit
away from putting an unfinished site in the index, which is not a defect a later
fix undoes.

## Rendering

Content pages are server-rendered with ISR (`revalidate: 300`). The preview routes
are `force-dynamic` and never cached. First-load JS is ~103 kB shared; content
pages add under 1 kB because they ship no client component.

## Metadata

Per page: title, description, canonical path, robots, OpenGraph. `metadataBase` is
deliberately unset while there is no domain — Next would otherwise resolve
canonicals against localhost and emit URLs that are wrong the moment the real
domain arrives.

## Internationalisation

`fr` unprefixed, `nl` under `/nl`, declared in `locale_paths` rather than derived,
because the convention differs per site and guessing it changes every canonical.

`alternates()` emits hreflang only for locales that actually have the page. A
hreflang pointing at a 404 is a technical defect, not a nicety — which is why
French keywords are not machine-translated into Dutch and assumed to carry the
same intent. NL pages are an architecture capability, not an automatic output.

## Internal linking

`isKnownRoute()` refuses to render a link to a path the site config does not
declare. A link cannot ship pointing at a page that does not exist.

## Structured data

`BreadcrumbList` only. Not `Organization` (no real company data supplied), not
`LocalBusiness` (no address), not `AggregateRating` (no reviews). Structured data
that asserts things nobody supplied is fabrication with a schema attached.
