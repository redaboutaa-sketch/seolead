/**
 * Price formatting.
 *
 * Every function here refuses to invent. A missing basis renders as "base non
 * précisée", not as an assumed total; an unknown VAT status renders as unknown,
 * not as excluded. The Phase 3.4 evidence model went to some trouble to record
 * what the source did not say, and the display layer must not quietly fill it in.
 */
import type { PriceAnswer } from "./types";

const BASIS_LABELS: Record<string, string> = {
  TOTAL: "pour l'installation complète",
  PER_WP: "par watt-crête",
  PER_KWP: "par kWc",
  PER_M2: "par m²",
  PER_PANEL: "par panneau",
  PER_KWH: "par kWh",
  PER_YEAR: "par an",
  UNKNOWN: "base non précisée par la source",
};

const VAT_LABELS: Record<string, string> = {
  INCLUDED: "TVA comprise",
  EXCLUDED: "hors TVA",
  UNKNOWN: "TVA non précisée",
};

export function basisLabel(basis: string | null): string {
  return BASIS_LABELS[basis ?? "UNKNOWN"] ?? BASIS_LABELS.UNKNOWN!;
}

export function vatLabel(status: string | null): string {
  return VAT_LABELS[status ?? "UNKNOWN"] ?? VAT_LABELS.UNKNOWN!;
}

export function vatIsUnknown(status: string | null): boolean {
  return (status ?? "UNKNOWN") === "UNKNOWN";
}

export function formatAmount(value: number, currency: string | null): string {
  const formatted = new Intl.NumberFormat("fr-BE", {
    maximumFractionDigits: value < 10 ? 2 : 0,
  }).format(value);
  return currency === "EUR" || currency === null ? `${formatted} €` : `${formatted} ${currency}`;
}

export function formatPrice(answer: PriceAnswer): string {
  const amounts = answer.amounts ?? [];
  if (amounts.length === 0) return "—";
  if (amounts.length === 1 || !answer.is_range) {
    return formatAmount(amounts[0]!, answer.currency);
  }
  const low = amounts[0]!;
  const high = amounts[amounts.length - 1]!;
  return `${formatAmount(low, answer.currency)} – ${formatAmount(high, answer.currency)}`;
}

export function systemSizeLabel(sizes: number[]): string | null {
  if (!sizes || sizes.length === 0) return null;
  if (sizes.length === 1) return `${trimNumber(sizes[0]!)} kWc`;
  return `${trimNumber(sizes[0]!)}–${trimNumber(sizes[sizes.length - 1]!)} kWc`;
}

function trimNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(value).replace(/\.0+$/, "");
}

/**
 * How a figure may be described.
 *
 * `MARKET_AVERAGE` is the only category that may be called an average, and
 * nothing here ever produces the phrase "the price in Belgium". That wording was
 * the exact failure Phase 3.4 forbade.
 */
export function qualificationLabel(category: string | null): string {
  switch (category) {
    case "MARKET_AVERAGE":
      return "moyenne rapportée par une source";
    case "OBSERVED_PRICE_RANGE":
      return "fourchette observée dans une source";
    case "VENDOR_PRICE":
      return "prix affiché par un fournisseur";
    default:
      return "valeur relevée dans une source";
  }
}
