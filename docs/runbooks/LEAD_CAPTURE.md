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

## What the honeypot defect actually cost

Measured on the host on 2026-08-31, after the fix: **one** `lead submission
rejected` in the whole log, and it was the owner's own submission of the evening
before. No human request was lost. The defect cost exactly the test that
revealed it.

That number is the reason the fix is a fix and not a post-mortem — but it is
also why the count matters as a habit rather than as a one-off. A honeypot that
starts refusing humans does so silently, and the only place it shows is here:

```bash
docker logs seolead_api 2>&1 | grep -c "lead submission rejected"
docker logs seolead_api 2>&1 | grep "lead submission rejected" | tail -20
```

Nothing about a refusal is persisted — `capture_lead` logs and raises — so this
count lives only as long as the container's logs do. A rising count with no
matching spam is the signal to look at the decoy field again.

## Verifying one real submission

What a complete submission must leave behind: **one** `captured_lead` row and
**five** `lead_consent` rows. Five and not four: `consent_followup_contact` is
one checkbox whose validated text names two channels, so it emits a PHONE row
and a WHATSAPP row carrying the same answer, the same text and the same version.

| consent_key | purpose | channel | text_version |
|---|---|---|---|
| `consent_processing` | PROCESSING | — | `solar-be-consent-v1.0-2026-08-17` |
| `consent_followup_contact:PHONE` | FOLLOWUP_CONTACT | PHONE | `solar-be-followup-contact-v1.0-2026-08-30` |
| `consent_followup_contact:WHATSAPP` | FOLLOWUP_CONTACT | WHATSAPP | `solar-be-followup-contact-v1.0-2026-08-30` |
| `consent_marketing` | MARKETING | WHATSAPP | `solar-be-marketing-whatsapp-v1.0-2026-08-30` |
| `consent_partner_transfer` | PARTNER_TRANSFER | — | `solar-be-partner-transfer-v1.0-2026-08-30` |

The two follow-up keys carry their channel as a suffix, and that is not
decoration. `LeadConsent.consent_key` stores `case["key"]`, which for a
multi-channel case is `field_key:CHANNEL` — the form field key alone would
break the `(captured_lead_id, consent_key)` uniqueness the moment a case
emits two rows. A checklist written from the field key instead reports two
false misses; this one was.

**PROCESSING carries a 17/08 version, and that is correct.** Its text was not
touched by the validation of 2026-08-30 — the YAML says so in place — so it
still resolves through `legal.consent_version`. Four rows dated 30/08 and one
dated 17/08 is the expected shape; five rows dated 30/08 would mean a text had
been changed without anyone deciding to.

An unticked box is a row with `granted = false`. A refusal is a fact with legal
weight, and it is what lets an export say "marketing: not consented" instead of
guessing. A case the form never offered has no row at all.

### Verified once, on 2026-08-31

Lead `6b062901`, submitted from `/demande-etude` at 09:14:31 UTC: one
`captured_lead` in `PENDING_EXPORT`, five `lead_consent` rows, every purpose,
channel and version as tabulated above — PROCESSING on the 17/08 text, the four
others on the 30/08 ones. The legacy pair on `captured_lead` agrees with the
per-case rows (`consent_version` 17/08, `consent_marketing` true), which is the
guarantee export contract v1 rests on.

All five answers were `granted = true`, so the recorded-refusal path — a case
shown, declined, and written as a row rather than omitted — is covered by the
test suite and has still never been exercised by a real visitor.

```sql
SELECT c.consent_key, c.purpose, c.channel, c.granted, c.text_version,
       c.granted_at, c.source
FROM lead_consent c
JOIN captured_lead l ON l.id = c.captured_lead_id
ORDER BY l.created_at DESC, c.purpose, c.channel;
```

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
