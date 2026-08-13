# n8n workflow contracts (documented, not deployed)

**No n8n workflow has been created, imported or enabled.** These are the contracts
a future automation must satisfy. Application correctness does not depend on any
of them: every step below has a CLI equivalent an operator runs by hand today.

## 1. Content: approved → published

```
trigger:  a draft reaches Approval.state = APPROVED
  │
  ├─► stage      POST /internal/v1/… (or `seolead content stage <draft-id>`)
  │              refuses unless the gate passes; result is STAGED, noindex
  │
  ├─► notify     owner receives the preview URL and the gate summary
  │
  ├─► WAIT       owner publish approval — a human decision, never a timer
  │
  ├─► publish    `seolead content publish <content-id>`
  │              refuses while the site is staging or has no domain
  │
  ├─► sitemap    regenerate (automatic: /sitemap.xml is computed per request)
  │
  └─► notify     published URL
```

The `WAIT` step is not optional and must not be replaced by a delay. An automation
that publishes on a timer has removed the human from a decision the whole design
exists to preserve.

## 2. Leads: pending → exported

```
trigger:  CapturedLead.state = PENDING_EXPORT
  │
  ├─► claim      state → EXPORTING (guards against double export)
  │
  ├─► deliver    Prospect360LeadDestination — DOES NOT EXIST YET
  │              see docs/integrations/PROSPECT360_INGEST_CONTRACT.md
  │
  ├─► on ACK     state → EXPORTED, record the remote identifier
  │
  └─► on error   state → EXPORT_FAILED, backoff, retry
                 after N failures: notify, do not silently drop
```

Must be idempotent on `lead.id`. A retry that creates a second prospect is worse
than a retry that fails.

## Why nothing is deployed

Two reasons. The lead workflow has no destination to call. And the content
workflow's only non-manual value is convenience — the gate, the refusals and the
audit trail are all in the application, where they cannot be edited by anyone with
access to an n8n canvas.
