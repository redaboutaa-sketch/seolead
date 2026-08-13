# SEO technical foundation

## The publication gate, expressed three ways

| Surface | While not indexable | When launched |
|---|---|---|
| `robots.txt` | `User-Agent: * / Disallow: /` | allow, with `/preview/` and `/api/` disallowed |
| page `<meta robots>` | `noindex, nofollow, nocache` | `index, follow` |
| `X-Robots-Tag` header | `noindex, nofollow, noarchive, nosnippet` | absent |
| Traefik response header | same, added at the edge | removed with the overlay edit |
| `sitemap.xml` | empty | PUBLISHED URLs only |

The `X-Robots-Tag` header is **fail-closed**: it is emitted unless
`SEOLEAD_ALLOW_INDEXING=true` is set at build time. It covers every response
including static assets and error pages — responses the application's own meta tag
never reaches.

"Indexable" is three independent conditions — a domain is set, `staging` is false,
and `seo.allow_indexing` is true — because a single flag is one accidental commit
away from putting an unfinished site in the index, which is not a defect a later
fix undoes.

## Rendering

Content pages are server-rendered with ISR (`revalidate: 300`). The preview routes
are `force-dynamic` and never cached. First-load JS is ~103 kB shared; content
pages add under 1 kB because they ship no client component.

## Metadata and canonicals

Per page: title, description, canonical, robots, OpenGraph.

`metadataBase` comes from `SiteConfig.seo.canonical_origin`
(`https://monprojetsolaire.be`) — never from the host that served the request. The
staging host and the canonical host are different things, and resolving canonicals
against whichever hostname answered is how a page ends up telling a crawler it
really lives on `localhost:3100`.

The origin is validated at load time. A `canonical_origin` that is plain HTTP, ends
in a slash, contradicts `domain`, or contains `localhost`, `127.0.0.1`, a container
hostname, `.internal` or `.local` is rejected outright. With no origin configured,
canonicals fall back to relative paths — incomplete, but not a false statement
about where a page lives.

Canonicals are already correct **while the site is noindex**. Getting them right
before launch means no page ever carries a wrong one.

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
