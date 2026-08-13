# Conversion funnel

## The offer

Primary CTA: **Obtenir mon estimation personnalisée** (`ESTIMATE_REQUEST`).
Secondary: **Être rappelé** (`CALLBACK_REQUEST`).

No countdown, no scarcity claim, no fabricated social proof. The page's whole
credibility rests on figures that are traceable to sources; manufactured urgency
beside them would undo the thing that makes the page worth reading.

## The form

Five steps, defined entirely in `config/sites/solar_be.yaml`. Nothing about solar
panels is compiled into the form component.

| Step | Asks | Why here |
|---|---|---|
| 1 project | owner status, postcode, property type | qualifies fast, costs the visitor nothing |
| 2 roof | roof type, orientation | shapes what is possible |
| 3 consumption | annual kWh, monthly bill, battery interest | all optional |
| 4 timing | project timeframe | the commercial signal |
| 5 contact | name, email, phone, consents | requested last |

Progressive disclosure is the point: a form that opens by demanding a phone number
converts worse and is a worse experience. The project questions come first and
visibly go somewhere.

## Validation

Client-side validation is a convenience for the visitor. Every rule is enforced
again server-side in `app/site/lead_capture.py`, because anything can POST to the
endpoint. Unknown qualification keys are dropped, choices outside their configured
options are dropped, numbers outside their bounds are dropped, and an unparseable
optional phone is dropped rather than failing the whole submission.

## Consent

Two separate checkboxes. Processing consent is required; marketing consent is
optional and declining it never rejects a lead. Neither is pre-checked.

Recorded per lead: `consent_version`, `consent_timestamp`, `consent_source`. A
bare `consented = true` cannot answer "to what?" a year later.

## Spam protection

`SpamProtectionProvider` with a heuristic implementation:

- a honeypot field no human sees,
- a 2 500 ms floor between form render and submit,
- an in-process per-client rate limit (5 per hour), keyed on a salted hash of the
  IP that is computed per request and never stored.

No CAPTCHA. A tracking-heavy challenge on a form that has received no spam would
cost real conversions to solve a problem that has not appeared. The port is there
so Turnstile is an adapter when it is needed.

## Events

`PAGE_VIEW`, `CTA_CLICK`, `FORM_STARTED`, `FORM_STEP_COMPLETED`, `FORM_SUBMITTED`,
`LEAD_CREATED`. First-party, coarse, bounded detail, no cross-site identity, no
advertising identifier, no GA4.
