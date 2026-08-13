# Runbook — leads

## List

```bash
seolead leads list --status PENDING_EXPORT
seolead leads list                    # all states
```

Email is masked and the phone is reported only as present or absent. An operator
listing leads wants counts, states and attribution; full contact details do not
belong in a command that gets run casually and pasted into a terminal log.

## What `PENDING_EXPORT` means

Captured, validated, stored locally, and **not sent anywhere**. The Prospect 360
boundary is closed (`docs/integrations/PROSPECT360_INGEST_CONTRACT.md`). Leads
accumulate here until that adapter exists and the owner approves the destination.

Until then, someone must read this list. A lead nobody looks at is a lost lead
whatever its state says.

## If a submission was rejected

The API returns 422 with a reason that names fields, never values:

| Message | Meaning |
|---|---|
| `honeypot field was filled` | automated submission |
| `submitted in Nms, under the 2500ms floor` | automated submission |
| `more than 5 submissions in 60 minutes` | rate limit |
| `consent to process the request is required` | consent box unchecked |
| `not a usable email address` | failed server-side validation |
| `missing required answer(s): …` | a required configured field was empty |

## Privacy

- No submitted value is written to the logs, on success or on rejection.
- The submitter's IP is hashed with a per-deployment salt for rate limiting and
  is never stored with the lead.
- Marketing consent is separate from processing consent and is stored with its
  version and timestamp.

## Changing the form

Edit `config/sites/solar_be.yaml` under `conversion.form_steps` and
`conversion.fields`. No migration and no code change: unknown keys are dropped
server-side, so an old cached form cannot inject a field that no longer exists.
