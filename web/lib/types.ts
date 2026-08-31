/**
 * The publication-safe shapes the site is allowed to see.
 *
 * These mirror the API's DTO exactly and deliberately have no field for source
 * URLs, claim identifiers, QA notes or provider metadata. If a type has no field
 * for something, no component can render it by accident.
 */

export type InlineMark = "strong" | "em" | "code" | null;

export interface TextRun {
  text: string;
  mark: InlineMark;
}

export interface HeadingSection {
  type: "heading";
  level: number;
  text: string;
}

export interface ParagraphSection {
  type: "paragraph";
  runs: TextRun[];
  text: string;
}

export interface ListItem {
  runs: TextRun[];
  text: string;
}

export interface ListSection {
  type: "list" | "price_list";
  items: ListItem[];
}

export type Section = HeadingSection | ParagraphSection | ListSection;

/** A price figure with everything the source actually stated about it. */
export interface PriceAnswer {
  claim: string | null;
  category: string | null;
  qualification: string | null;
  amounts: number[];
  currency: string | null;
  basis: string | null;
  vat_status: string | null;
  system_size_kwp: number[];
  battery_included: boolean | null;
  installation_included: boolean | null;
  is_range: boolean | null;
}

export interface ObservedRange {
  low: number;
  high: number;
  currency: string | null;
  basis: string;
  vat_status: string;
  observation_count: number;
  wording: string;
}

export interface PriceEvidence {
  core_question?: string | null;
  core_answer_status?: string | null;
  answers?: PriceAnswer[];
  observed_range?: ObservedRange | null;
}

export interface PublishedContentDTO {
  slug: string;
  locale: string;
  type: string;
  search_intent: string | null;
  title: string;
  meta: {
    title: string;
    description: string | null;
    canonical_path: string | null;
    /** Absolute, built from the site's configured production origin. */
    canonical_url: string | null;
    noindex: boolean;
  };
  sections: Section[];
  price_evidence: PriceEvidence;
  cta: {
    primary: string;
    primary_label: string;
    secondary: string | null;
    secondary_label: string | null;
    brief_cta?: string | null;
  };
  version: number;
  state: string;
  published_at: string | null;
  updated_at: string | null;
  preview?: boolean;
}

/**
 * Per-locale text overrides, keyed by locale then by text key. The base fields
 * (label, help, title, description) are the default locale's text AND the
 * fallback: a missing i18n key must render the base text, never a blank.
 */
export type I18nOverrides = Record<
  string,
  { label?: string; help?: string; title?: string; description?: string }
>;

export interface FormFieldOption {
  value: string;
  label: string;
  i18n?: I18nOverrides;
}

export interface FormField {
  key: string;
  type: "text" | "email" | "phone" | "number" | "choice" | "postcode" | "consent";
  label: string;
  required?: boolean;
  options?: FormFieldOption[];
  help?: string;
  pattern?: string;
  min?: number;
  max?: number;
  max_length?: number;
  // Consent-case metadata (type "consent" only). The server resolves purpose,
  // channel and text version itself from the site config; these exist here so
  // the form can mark a pending case visually and never has to hard-code keys.
  consent_purpose?: string;
  consent_channel?: string;
  consent_version?: string;
  pending_legal_review?: boolean;
  i18n?: I18nOverrides;
}

export interface FormStep {
  key: string;
  title: string;
  description?: string;
  fields: string[];
  i18n?: I18nOverrides;
}

export interface SiteConfigDTO {
  site_id: string;
  vertical: string;
  brand_name: string;
  brand_name_is_placeholder: boolean;
  domain: string | null;
  market: string;
  default_language: string;
  supported_languages: string[];
  staging: boolean;
  indexable: boolean;
  locale_paths: Record<string, string>;
  contact: {
    email: string | null;
    phone: string | null;
    address: string | null;
    company_name: string | null;
    company_number: string | null;
    lead_destination_email: string | null;
  };
  legal: {
    privacy_policy_path: string | null;
    terms_path: string | null;
    cookie_policy_path: string | null;
    consent_version: string;
    privacy_policy_version: string | null;
    data_controller: string | null;
    privacy_contact_email: string | null;
    reviewed: boolean;
  };
  conversion: {
    primary_cta: string;
    primary_cta_label: string;
    secondary_cta: string | null;
    secondary_cta_label: string | null;
    form_id: string;
    form_steps: FormStep[];
    fields: FormField[];
    consent_required: boolean;
    marketing_consent_optional: boolean;
  };
  seo: {
    canonical_origin: string | null;
    default_title_suffix: string | null;
    default_meta_description: string | null;
    organization_schema: boolean;
    sitemap_enabled: boolean;
    allow_indexing: boolean;
    // Search-console ownership tokens — owner-supplied, null emits nothing.
    verification?: { google: string | null; bing: string | null };
  };
  // The first-party offer registry, already publication-gated by the API:
  // `facts` only ever carries owner-validated AND legally-cleared values, so
  // the renderer cannot show an unvalidated figure even by mistake.
  offer: OfferDTO;
  organization: OrganizationDTO;
  routes: { path: string; type: string; locales: string[] }[];
}

export interface OfferFactDTO {
  id: string;
  label: string;
  value: string | number | boolean | null;
  unit: string | null;
}

export interface OfferDTO {
  version: string;
  status: string;
  pending_legal_review: boolean;
  publishable: boolean;
  facts: OfferFactDTO[];
  financing: { provider?: string | null; conditions?: string[] };
  eligibility: { criteria?: string[] };
  geography: { service_areas?: string[] };
  mandatory_disclosures: string[];
}

export interface OrganizationDTO {
  legal_name: string | null;
  bce_number: string | null;
  address: {
    street: string | null;
    postal_code: string | null;
    city: string | null;
    country: string;
  };
  phone: string | null;
  email: string | null;
  service_areas: string[];
  logo_path: string | null;
  installer_partner: string | null;
  certifications: string[];
  same_as: string[];
  organization_schema_ready: boolean;
  local_business_schema_ready: boolean;
}

export interface LeadPayload {
  conversion_type: string;
  email: string;
  language: string;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  postcode?: string | null;
  qualification: Record<string, unknown>;
  consent_processing: boolean;
  consent_marketing: boolean;
  attribution: Record<string, unknown>;
  ref_token_2?: string | null;
  elapsed_ms?: number | null;
}
