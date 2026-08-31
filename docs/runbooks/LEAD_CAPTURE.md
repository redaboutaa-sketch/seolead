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

The API returns 422. What the **visitor** sees and what **you** see are no
longer the same thing, and that is deliberate.

A refusal by the spam defences carries the code `SUBMISSION_REFUSED` and the
message *« Votre demande n'a pas pu être enregistrée. Merci de réessayer. »* —
nothing more. Naming the defence that fired tells a bot what to change, and told
the owner, on 2026-08-30, a word he could do nothing with. The reason lives in
the API log:

```bash
docker logs seolead_api 2>&1 | grep "lead submission rejected"
```

| Logged reason | Meaning |
|---|---|
| `honeypot field was filled` | the decoy field was not empty |
| `submitted in Nms, under the 2500ms floor` | submitted faster than a human reads |
| `more than 5 submissions in 60 minutes` | rate limit |

Validation refusals are still shown to the visitor, because they are things a
visitor can act on:

| Message | Meaning |
|---|---|
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
