"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { localizedText } from "@/lib/site";
import type { FormField, FormStep, SiteConfigDTO } from "@/lib/types";

/**
 * Configuration-driven multi-step qualification form.
 *
 * Nothing about solar panels is hard-coded here. Steps, fields, labels, options
 * and validation rules all arrive from the site config, so a second vertical gets
 * a form by editing YAML.
 *
 * Two accessibility decisions worth naming. Progress is announced through a live
 * region rather than shown only as a bar, because a screen-reader user otherwise
 * has no idea a step advanced. And validation errors are bound to their input
 * with `aria-describedby` and focus is moved to the first invalid field, because
 * an error message that only exists visually is not an error message.
 */

type Values = Record<string, string | boolean>;

/**
 * The form's own chrome, per locale. Field labels come from the site config
 * (with their own `i18n` blocks); these are the strings the component itself
 * owns. `fr` is the fallback for any locale absent here.
 *
 * The `nl` entries are PLACEHOLDERS, deliberately not translated: every one is
 * marked « À TRADUIRE PAR UN NATIF » and shows the French text after the
 * marker. Machine translation is refused on principle — an approximate label on
 * a qualification form costs leads and trust, and nobody proofreads a machine.
 */
interface UiStrings {
  consentRequired: string;
  fieldRequired: string;
  emailInvalid: string;
  postcodeInvalid: string;
  numberExpected: string;
  minValue: (bound: number) => string;
  maxValue: (bound: number) => string;
  stepLabel: (current: number, total: number) => string;
  defaultHeading: string;
  back: string;
  next: string;
  sending: string;
  optionalSuffix: string;
  doneTitle: string;
  doneMessage: string;
  failMessage: string;
  unreadableMessage: string;
}

const NL_TODO = "[NL — À TRADUIRE PAR UN NATIF] ";

const FR_STRINGS: UiStrings = {
  consentRequired: "Cette autorisation est nécessaire pour continuer.",
  fieldRequired: "Ce champ est nécessaire.",
  emailInvalid: "Cette adresse e-mail ne semble pas valide.",
  postcodeInvalid: "Code postal belge attendu (4 chiffres).",
  numberExpected: "Un nombre est attendu.",
  minValue: (bound) => `Valeur minimale : ${bound}.`,
  maxValue: (bound) => `Valeur maximale : ${bound}.`,
  stepLabel: (current, total) => `Étape ${current} sur ${total}`,
  defaultHeading: "Votre demande",
  back: "Retour",
  next: "Continuer",
  sending: "Envoi…",
  optionalSuffix: " (facultatif)",
  doneTitle: "Demande enregistrée",
  doneMessage:
    "Merci — votre demande est enregistrée. Nous revenons vers vous avec une estimation adaptée à votre situation.",
  failMessage:
    "Votre demande n'a pas pu être enregistrée. Vérifiez vos réponses et réessayez.",
  unreadableMessage: "Votre demande n'a pas pu être enregistrée.",
};

const UI_STRINGS: Record<string, UiStrings> = {
  fr: FR_STRINGS,
  nl: {
    consentRequired: `${NL_TODO}Cette autorisation est nécessaire pour continuer.`,
    fieldRequired: `${NL_TODO}Ce champ est nécessaire.`,
    emailInvalid: `${NL_TODO}Cette adresse e-mail ne semble pas valide.`,
    postcodeInvalid: `${NL_TODO}Code postal belge attendu (4 chiffres).`,
    numberExpected: `${NL_TODO}Un nombre est attendu.`,
    minValue: (bound) => `${NL_TODO}Valeur minimale : ${bound}.`,
    maxValue: (bound) => `${NL_TODO}Valeur maximale : ${bound}.`,
    stepLabel: (current, total) => `${NL_TODO}Étape ${current} sur ${total}`,
    defaultHeading: `${NL_TODO}Votre demande`,
    back: `${NL_TODO}Retour`,
    next: `${NL_TODO}Continuer`,
    sending: `${NL_TODO}Envoi…`,
    optionalSuffix: ` ${NL_TODO.trim()}(facultatif)`,
    doneTitle: `${NL_TODO}Demande enregistrée`,
    doneMessage: `${NL_TODO}Merci — votre demande est enregistrée. Nous revenons vers vous avec une estimation adaptée à votre situation.`,
    failMessage: `${NL_TODO}Votre demande n'a pas pu être enregistrée. Vérifiez vos réponses et réessayez.`,
    unreadableMessage: `${NL_TODO}Votre demande n'a pas pu être enregistrée.`,
  },
};

interface Props {
  config: SiteConfigDTO;
  locale: string;
  conversionType: string;
  attribution: Record<string, string | null>;
}

function fieldById(fields: FormField[], key: string): FormField | undefined {
  return fields.find((field) => field.key === key);
}

export function LeadForm({ config, locale, conversionType, attribution }: Props) {
  const steps: FormStep[] = useMemo(
    () => config.conversion.form_steps ?? [],
    [config.conversion.form_steps],
  );
  const fields: FormField[] = useMemo(
    () => config.conversion.fields ?? [],
    [config.conversion.fields],
  );

  const [stepIndex, setStepIndex] = useState(0);
  const [values, setValues] = useState<Values>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [message, setMessage] = useState<string>("");
  const startedAt = useRef<number>(Date.now());
  const startedReported = useRef(false);
  const headingRef = useRef<HTMLHeadingElement | null>(null);

  const t = UI_STRINGS[locale] ?? FR_STRINGS;

  const step = steps[stepIndex];
  const stepFields = useMemo(
    () => (step?.fields ?? []).map((key) => fieldById(fields, key)).filter(Boolean) as FormField[],
    [step, fields],
  );

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  useEffect(() => {
    // Move focus to the new step's heading so the change is announced and the
    // keyboard user is not left at the bottom of the previous step.
    if (stepIndex > 0) headingRef.current?.focus();
  }, [stepIndex]);

  function track(eventType: string, detail: Record<string, string> = {}) {
    void fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: eventType,
        page_path: typeof window === "undefined" ? null : window.location.pathname,
        locale,
        detail,
      }),
    }).catch(() => undefined);
  }

  function setValue(key: string, value: string | boolean) {
    if (!startedReported.current) {
      startedReported.current = true;
      track("FORM_STARTED", { form: config.conversion.form_id });
    }
    setValues((previous) => ({ ...previous, [key]: value }));
    setErrors((previous) => {
      if (!previous[key]) return previous;
      const next = { ...previous };
      delete next[key];
      return next;
    });
  }

  function validateStep(): boolean {
    const found: Record<string, string> = {};
    for (const field of stepFields) {
      const value = values[field.key];
      if (field.type === "consent") {
        if (field.required && value !== true) {
          found[field.key] = t.consentRequired;
        }
        continue;
      }
      const text = typeof value === "string" ? value.trim() : "";
      if (field.required && !text) {
        found[field.key] = t.fieldRequired;
        continue;
      }
      if (!text) continue;
      if (field.type === "email" && !/^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/.test(text)) {
        found[field.key] = t.emailInvalid;
      }
      if (field.type === "postcode" && field.pattern && !new RegExp(field.pattern).test(text)) {
        found[field.key] = t.postcodeInvalid;
      }
      if (field.type === "number") {
        const numeric = Number(text);
        if (Number.isNaN(numeric)) found[field.key] = t.numberExpected;
        else if (field.min !== undefined && numeric < field.min)
          found[field.key] = t.minValue(field.min);
        else if (field.max !== undefined && numeric > field.max)
          found[field.key] = t.maxValue(field.max);
      }
    }
    setErrors(found);
    if (Object.keys(found).length > 0) {
      const first = Object.keys(found)[0];
      if (first) document.getElementById(`field-${first}`)?.focus();
      return false;
    }
    return true;
  }

  function next() {
    if (!validateStep()) return;
    track("FORM_STEP_COMPLETED", { step: step?.key ?? String(stepIndex) });
    setStepIndex((index) => Math.min(index + 1, steps.length - 1));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    /*
     * Only the final step may submit.
     *
     * Without this guard, advancing from step 4 to step 5 submitted the form.
     * React reuses the same DOM button for "Continuer" and for the submit
     * action — same position, same element — and it flushes a discrete click
     * synchronously. So `next()` ran, the re-render retyped that very button
     * from `type="button"` to `type="submit"`, and the browser then applied the
     * submit default action to a click the visitor meant as "continue". The
     * visitor landed on the contact step already showing two red errors for
     * fields they had not been offered yet, and a spurious FORM_SUBMITTED event
     * was recorded.
     *
     * Nothing about the payload, the fields or the validation rules changes
     * here; this only refuses a submission the visitor never asked for.
     */
    if (stepIndex !== steps.length - 1) return;
    if (!validateStep()) return;
    setStatus("sending");
    track("FORM_SUBMITTED", { form: config.conversion.form_id });

    const contactKeys = new Set([
      "first_name", "last_name", "email", "phone", "postcode", "honeypot",
    ]);
    // Consent cases are excluded from qualification by their TYPE, not by a
    // hard-coded key list: a new case added in YAML must not leak into the
    // qualification blob because nobody updated a set here.
    const consentKeys = new Set(
      fields.filter((field) => field.type === "consent").map((field) => field.key),
    );
    const qualification: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(values)) {
      if (contactKeys.has(key) || consentKeys.has(key)) continue;
      if (value === "" || value === false) continue;
      qualification[key] = value;
    }

    // Every consent case the form defines, answered true or false. An untouched
    // checkbox is a refusal, and the server records it as one.
    const consents: Record<string, boolean> = {};
    for (const key of consentKeys) consents[key] = values[key] === true;

    const response = await fetch("/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversion_type: conversionType,
        email: String(values.email ?? ""),
        language: locale,
        first_name: (values.first_name as string) || null,
        last_name: (values.last_name as string) || null,
        phone: (values.phone as string) || null,
        postcode: (values.postcode as string) || null,
        qualification,
        consent_processing: values.consent_processing === true,
        consent_marketing: values.consent_marketing === true,
        consents,
        attribution,
        honeypot: (values.honeypot as string) || "",
        elapsed_ms: Date.now() - startedAt.current,
      }),
    }).catch(() => null);

    if (response && response.ok) {
      setStatus("done");
      setMessage(t.doneMessage);
      track("LEAD_CREATED", { form: config.conversion.form_id });
      return;
    }
    setStatus("error");
    const body = response ? await response.json().catch(() => ({})) : {};
    setMessage((body as { message?: string }).message ?? t.failMessage);
  }

  if (status === "done") {
    return (
      <div className="lead-form" role="status" aria-live="polite">
        <h2>{t.doneTitle}</h2>
        <p>{message}</p>
      </div>
    );
  }

  const isLast = stepIndex === steps.length - 1;
  const progress = steps.length > 0 ? ((stepIndex + 1) / steps.length) * 100 : 0;

  return (
    <form className="lead-form" onSubmit={submit} noValidate>
      <div className="form-progress">
        <div className="form-progress__bar">
          <div className="form-progress__fill" style={{ width: `${progress}%` }} />
        </div>
        <p className="form-progress__label" aria-live="polite">
          {t.stepLabel(stepIndex + 1, steps.length)}
          {step ? ` — ${localizedText(step, locale, "title")}` : ""}
        </p>
      </div>

      <h2 tabIndex={-1} ref={headingRef}>
        {(step && localizedText(step, locale, "title")) ?? t.defaultHeading}
      </h2>
      {step && localizedText(step, locale, "description") ? (
        <p>{localizedText(step, locale, "description")}</p>
      ) : null}

      {stepFields.map((field) => (
        <Field
          key={field.key}
          field={field}
          locale={locale}
          strings={t}
          value={values[field.key]}
          error={errors[field.key]}
          onChange={setValue}
        />
      ))}

      {/* Not visible, not focusable, not announced. Only a bot fills it. */}
      <div className="honeypot" aria-hidden="true">
        <label htmlFor="field-honeypot">Ne pas remplir</label>
        <input
          id="field-honeypot"
          name="company_website"
          tabIndex={-1}
          autoComplete="off"
          value={(values.honeypot as string) ?? ""}
          onChange={(event) => setValue("honeypot", event.target.value)}
        />
      </div>

      <div className="form-actions">
        {stepIndex > 0 ? (
          <button
            type="button"
            className="button button--ghost"
            onClick={() => setStepIndex((index) => Math.max(0, index - 1))}
          >
            {t.back}
          </button>
        ) : null}
        {isLast ? (
          <button
            key="submit"
            type="submit"
            className="button button--large"
            disabled={status === "sending"}
          >
            {status === "sending" ? t.sending : config.conversion.primary_cta_label}
          </button>
        ) : (
          <button key="next" type="button" className="button button--large" onClick={next}>
            {t.next}
          </button>
        )}
      </div>

      {status === "error" ? (
        <p className="form-status field__error" role="alert">
          {message}
        </p>
      ) : null}
    </form>
  );
}

function Field({
  field,
  locale,
  strings,
  value,
  error,
  onChange,
}: {
  field: FormField;
  locale: string;
  strings: UiStrings;
  value: string | boolean | undefined;
  error?: string;
  onChange: (key: string, value: string | boolean) => void;
}) {
  const id = `field-${field.key}`;
  const errorId = `${id}-error`;
  const helpId = `${id}-help`;
  const label = localizedText(field, locale, "label") ?? field.label;
  const help = localizedText(field, locale, "help");
  const describedBy = [help ? helpId : null, error ? errorId : null]
    .filter(Boolean)
    .join(" ");

  if (field.type === "consent") {
    return (
      <div className="field">
        <label className="consent" htmlFor={id}>
          <input
            id={id}
            type="checkbox"
            checked={value === true}
            aria-describedby={describedBy || undefined}
            aria-invalid={error ? true : undefined}
            onChange={(event) => onChange(field.key, event.target.checked)}
          />
          <span>
            {label}
            {field.required ? "" : strings.optionalSuffix}
          </span>
        </label>
        {error ? (
          <p className="field__error" id={errorId}>
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  if (field.type === "choice") {
    return (
      <div className="field">
        <fieldset aria-describedby={describedBy || undefined}>
          <legend>
            {label}
            {field.required ? "" : strings.optionalSuffix}
          </legend>
          <div className="choice-list">
            {(field.options ?? []).map((option) => (
              <label className="choice" key={option.value}>
                <input
                  type="radio"
                  name={field.key}
                  value={option.value}
                  checked={value === option.value}
                  onChange={() => onChange(field.key, option.value)}
                />
                <span>{localizedText(option, locale, "label") ?? option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {help ? (
          <p className="field__help" id={helpId}>
            {help}
          </p>
        ) : null}
        {error ? (
          <p className="field__error" id={errorId}>
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  const inputType =
    field.type === "email" ? "email" : field.type === "phone" ? "tel" : field.type === "number" ? "number" : "text";

  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {field.required ? "" : strings.optionalSuffix}
      </label>
      <input
        id={id}
        type={inputType}
        inputMode={field.type === "postcode" ? "numeric" : undefined}
        autoComplete={
          field.key === "email"
            ? "email"
            : field.key === "phone"
              ? "tel"
              : field.key === "first_name"
                ? "given-name"
                : field.key === "last_name"
                  ? "family-name"
                  : field.key === "postcode"
                    ? "postal-code"
                    : "off"
        }
        value={(value as string) ?? ""}
        aria-describedby={describedBy || undefined}
        aria-invalid={error ? true : undefined}
        aria-required={field.required || undefined}
        onChange={(event) => onChange(field.key, event.target.value)}
      />
      {help ? (
        <p className="field__help" id={helpId}>
          {help}
        </p>
      ) : null}
      {error ? (
        <p className="field__error" id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
