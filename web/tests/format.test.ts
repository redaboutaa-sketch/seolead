import { describe, expect, it } from "vitest";

import {
  basisLabel,
  formatPrice,
  qualificationLabel,
  systemSizeLabel,
  vatIsUnknown,
  vatLabel,
} from "@/lib/format";
import type { PriceAnswer } from "@/lib/types";

function answer(overrides: Partial<PriceAnswer> = {}): PriceAnswer {
  return {
    claim: "Entre 4.000 € et 14.000 € TVAC pour une installation de 3 à 10 kWc.",
    category: "OBSERVED_PRICE_RANGE",
    qualification: "a figure this source reports",
    amounts: [4000, 14000],
    currency: "EUR",
    basis: "TOTAL",
    vat_status: "INCLUDED",
    system_size_kwp: [3, 10],
    battery_included: null,
    installation_included: true,
    is_range: true,
    ...overrides,
  };
}

describe("price formatting", () => {
  it("renders a range as a range", () => {
    expect(formatPrice(answer())).toContain("–");
    expect(formatPrice(answer())).toMatch(/4[\s  .]?000/);
  });

  it("renders a single figure without a range dash", () => {
    const single = formatPrice(answer({ amounts: [6500], is_range: false }));
    expect(single).not.toContain("–");
  });

  it("never invents a basis the source did not state", () => {
    expect(basisLabel(null)).toContain("non précisée");
    expect(basisLabel("UNKNOWN")).toContain("non précisée");
  });

  it("reports unknown VAT as unknown rather than assuming", () => {
    expect(vatIsUnknown(null)).toBe(true);
    expect(vatIsUnknown("UNKNOWN")).toBe(true);
    expect(vatIsUnknown("INCLUDED")).toBe(false);
    expect(vatLabel("UNKNOWN")).toContain("non précisée");
  });

  it("calls an average an average and an observation an observation", () => {
    expect(qualificationLabel("MARKET_AVERAGE")).toContain("moyenne");
    expect(qualificationLabel("OBSERVED_PRICE_RANGE")).not.toContain("moyenne");
    expect(qualificationLabel("VENDOR_PRICE")).not.toContain("moyenne");
    // The wording Phase 3.4 forbade must be unreachable from any category.
    for (const category of ["OBSERVED_PRICE_RANGE", "VENDOR_PRICE", "MARKET_PRICE", null]) {
      expect(qualificationLabel(category)).not.toMatch(/prix (moyen|belge)/i);
    }
  });

  it("formats a system size band", () => {
    expect(systemSizeLabel([3, 10])).toBe("3–10 kWc");
    expect(systemSizeLabel([5])).toBe("5 kWc");
    expect(systemSizeLabel([])).toBeNull();
  });
});
