# Runbook — DNS for monprojetsolaire.be

**Status at 2026-08-13: BLOCKED. The zone is not delegated.**

Checked from this VPS:

```
dig +short monprojetsolaire.be      A      → (empty)
dig +short www.monprojetsolaire.be  A      → (empty)
dig +short monprojetsolaire.be      AAAA   → (empty)
dig +short www.monprojetsolaire.be  AAAA   → (empty)
dig +short NS  monprojetsolaire.be         → (empty)
dig +short SOA monprojetsolaire.be         → (empty)
```

No NS and no SOA means the domain has no authoritative nameservers answering yet —
the registration exists but the zone is not published. Records cannot be created
until nameservers are assigned at the registrar.

---

## Records the owner must create

| Type | Name | Value | TTL |
|---|---|---|---|
| `A` | `@` (apex, `monprojetsolaire.be`) | `76.13.44.177` | 3600 |
| `A` | `www` | `76.13.44.177` | 3600 |
| `AAAA` | `@` | `2a02:4780:7:f4ca::1` | 3600 |
| `AAAA` | `www` | `2a02:4780:7:f4ca::1` | 3600 |

Both hostnames must resolve. `www` is not optional: Traefik requests a separate
certificate for it, and the www→apex redirect cannot work without one.

The `AAAA` records are recommended rather than strictly required. This host has a
global IPv6 address, and publishing only `A` records means IPv6-only clients — and
some Let's Encrypt validation paths — cannot reach the site. If you publish `AAAA`
records, they must point here too: a stale or wrong `AAAA` is worse than none,
because clients prefer IPv6 and will fail rather than fall back quickly.

**No `CNAME` on the apex.** `monprojetsolaire.be` must be an `A`/`AAAA` record;
a CNAME at a zone apex is invalid and breaks the zone's own NS and SOA records.

**No CAA record is required.** If you choose to add one, it must permit
`letsencrypt.org`, or certificate issuance will fail:

```
monprojetsolaire.be.  CAA  0 issue "letsencrypt.org"
```

---

## Before that: assign nameservers at the registrar

Because there is no SOA, the first step is not a record — it is delegation.

1. In the registrar's control panel for `monprojetsolaire.be`, set the
   nameservers to whichever DNS provider will host the zone (the registrar's own
   DNS is fine).
2. Wait for the delegation to propagate. `.be` delegations are typically visible
   within an hour, occasionally longer.
3. Confirm delegation before creating records:

```bash
dig +short NS monprojetsolaire.be      # must return nameservers
dig +short SOA monprojetsolaire.be     # must return a SOA
```

4. Then create the four records above.

---

## Verifying, before anyone asks for a certificate

```bash
dig +short monprojetsolaire.be A        # expect 76.13.44.177
dig +short www.monprojetsolaire.be A    # expect 76.13.44.177
dig +short monprojetsolaire.be AAAA     # expect 2a02:4780:7:f4ca::1
dig +short www.monprojetsolaire.be AAAA # expect 2a02:4780:7:f4ca::1
```

Check against a public resolver too, not only the local one — the local resolver
may be caching a negative answer:

```bash
dig +short @1.1.1.1 monprojetsolaire.be A
dig +short @8.8.8.8 www.monprojetsolaire.be A
```

**Do not apply the Traefik overlay until all four commands return this host.**

## Why the order matters

The running Traefik uses the **TLS-ALPN-01** challenge
(`--certificatesresolvers.letsencrypt.acme.tlschallenge=true`). The challenge is
answered on port 443 for the requested hostname, so it can only succeed if DNS
already points here.

Let's Encrypt applies rate limits to repeated failures — currently 5 failed
validations per account, per hostname, per hour. Applying the routing while DNS is
wrong burns that budget on both hostnames and can lock out issuance for an hour
just when the DNS finally becomes correct. That is the entire reason the routing
lives in a separate, non-applied overlay file.

## When DNS is ready

Continue with `docs/runbooks/MONPROJETSOLAIRE_DEPLOYMENT.md`.
