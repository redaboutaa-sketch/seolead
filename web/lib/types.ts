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
  updated_at: string | null;
  preview?: boolean;
}

export interface FormFieldOption {
  value: string;
  label: string;
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
}

export interface FormStep {
  key: string;
  title: string;
  description?: string;
  fields: string[];
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
    data_controller: string | null;
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
    default_title_suffix: string | null;
    default_meta_description: string | null;
    organization_schema: boolean;
    sitemap_enabled: boolean;
    allow_indexing: boolean;
  };
  routes: { path: string; type: string; locales: string[] }[];
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
  honeypot?: string | null;
  elapsed_ms?: number | null;
}
