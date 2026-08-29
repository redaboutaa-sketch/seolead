import { describe, expect, it } from "vitest";

import { localizedText } from "@/lib/site";

/**
 * The fallback chain is the mechanism under test: a locale override wins, a
 * missing override falls back to the base text, and a missing base yields
 * undefined rather than an empty string pretending to be a label.
 */
describe("localizedText", () => {
  const field = {
    label: "Code postal",
    help: "4 chiffres, ex. 1000",
    i18n: { nl: { label: "[NL — À TRADUIRE PAR UN NATIF] Code postal" } },
  };

  it("returns the locale override when one exists", () => {
    expect(localizedText(field, "nl", "label")).toBe(
      "[NL — À TRADUIRE PAR UN NATIF] Code postal",
    );
  });

  it("falls back to the base text for a key the locale does not override", () => {
    expect(localizedText(field, "nl", "help")).toBe("4 chiffres, ex. 1000");
  });

  it("falls back to the base text for a locale with no overrides at all", () => {
    expect(localizedText(field, "de", "label")).toBe("Code postal");
  });

  it("serves the base locale from the base text", () => {
    expect(localizedText(field, "fr", "label")).toBe("Code postal");
  });

  it("yields undefined when neither override nor base exists", () => {
    expect(localizedText({ label: "x" }, "nl", "description")).toBeUndefined();
  });
});
