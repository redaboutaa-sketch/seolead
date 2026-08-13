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

## 3. Approve — a human act

```bash
seolead content approve <draft-id> --by "your name" --note "reviewed"
```

QA passing is not approval, and nothing in this system will approve on its own.

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
