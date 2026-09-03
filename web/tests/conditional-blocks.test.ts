/**
 * Conditional template blocks (tranche structurelle, 2026-09-03).
 *
 * The published article 8a1f6e46 had no price evidence and no rendered source,
 * and under it the template still said « Les fourchettes ci-dessus viennent de
 * sources publiées » and « Chaque montant affiché provient d'une source publiée
 * et consultée ». Both sentences were true of the template and false of the
 * page. The rule now: a block renders only what it has.
 *
 * Each case below is run twice — on the shape of the page as published (no
 * answers, no sources) and on the revised shape (sources present). A guard
 * that passes on both proves nothing.
 */
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CtaBlock, TrustSection, ctaBody } from "@/components/Cta";
import { SourcesBlock, sourceLine } from "@/components/Sources";
import type { SourceRef } from "@/lib/types";

const PUBLISHED_SOURCES: SourceRef[] = [];
const OFFICIAL: SourceRef = {
  name: "energie.wallonie.be",
  tier: "OFFICIAL",
  authority_type: "REGIONAL_ENERGY_ADMINISTRATION",
  region: "BE-WAL",
  date: null,
  freshness: "UNDATED_CURRENT",
  figures: ["7,3%", "8,4%"],
};
const SPECIALIST: SourceRef = {
  name: "un-installateur.be",
  tier: "SPECIALIST",
  authority_type: null,
  region: "BE",
  date: "2024-03-01",
  freshness: "OBSERVED",
  figures: ["4 personnes", "5000 kWh"],
};
const REVISED_SOURCES: SourceRef[] = [OFFICIAL, SPECIALIST];

describe("SourcesBlock — renders only what it has", () => {
  it("renders nothing on the page as published (no source to show)", () => {
    const html = renderToStaticMarkup(
      createElement(SourcesBlock, { sources: PUBLISHED_SOURCES }),
    );
    expect(html).toBe("");
    expect(renderToStaticMarkup(createElement(SourcesBlock, { sources: undefined })))
      .toBe("");
  });

  it("lists the sources, with the figures each carries, on the revised page", () => {
    const html = renderToStaticMarkup(
      createElement(SourcesBlock, { sources: REVISED_SOURCES }),
    );
    expect(html).toContain("Sources des chiffres de cette page");
    expect(html).toContain("energie.wallonie.be");
    expect(html).toContain("7,3%");
    expect(html).toContain("8,4%");
    expect(html).toContain("Wallonie");
  });

  it("names every source by its host, as text, and never links", () => {
    // Réserve 3 (2026-09-03) : « décrite sans être nommée » n'est pas
    // « source affichée ». A commercial or specialist source is named like
    // the others — as text, never as an anchor.
    const html = renderToStaticMarkup(
      createElement(SourcesBlock, { sources: REVISED_SOURCES }),
    );
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("http");
    expect(html).toContain("un-installateur.be");
    expect(sourceLine(SPECIALIST)).toMatch(/^un-installateur\.be \(source spécialisée/);
    expect(sourceLine(OFFICIAL)).toMatch(/^energie\.wallonie\.be/);
  });

  it("says when a source is undated instead of implying a date", () => {
    expect(sourceLine(OFFICIAL)).toContain("non datée");
    expect(sourceLine(SPECIALIST)).toContain("datée du 2024-03-01");
  });

  it("says a declared date as a date read on the document, not stated by the page", () => {
    // Réserve 2 : « non daté » on a document whose date is known is a false
    // value shown as a measurement. The declared date is shown with its basis.
    const declared: SourceRef = {
      ...OFFICIAL,
      name: "document.environnement.brussels",
      region: "BE-BRU",
      date: "2013",
      date_basis: "declared",
      freshness: "UNDATED",
    };
    expect(sourceLine(declared)).toContain("document daté de 2013");
    expect(sourceLine(declared)).not.toContain("non datée");
    expect(sourceLine(declared)).not.toContain("consultée, datée");
    expect(sourceLine({ ...declared, date_basis: "stated" })).toContain("consultée, datée du 2013");
  });
});

describe("TrustSection — the promise is made only when the sources are shown", () => {
  it("is absent on the page as published", () => {
    expect(renderToStaticMarkup(createElement(TrustSection, { hasSources: false })))
      .toBe("");
    // The default, too: a caller that forgets the prop gets no promise.
    expect(renderToStaticMarkup(createElement(TrustSection, {}))).toBe("");
  });

  it("is present on the revised page, with the sourcing promise", () => {
    const html = renderToStaticMarkup(
      createElement(TrustSection, { hasSources: true }),
    );
    expect(html).toContain("Chiffres sourcés");
    expect(html).toContain("source publiée");
  });
});

describe("CtaBlock — « les fourchettes ci-dessus » only above fourchettes", () => {
  it("does not describe price ranges on a page that showed none", () => {
    expect(ctaBody(false)).not.toContain("fourchettes ci-dessus");
    const html = renderToStaticMarkup(
      createElement(CtaBlock, { config: null, locale: "fr", hasPriceEvidence: false }),
    );
    expect(html).not.toContain("fourchettes ci-dessus");
    expect(html).toContain("Le prix de votre installation dépend");
  });

  it("describes them on a page that has a price block", () => {
    expect(ctaBody(true)).toContain("fourchettes ci-dessus");
    const html = renderToStaticMarkup(
      createElement(CtaBlock, { config: null, locale: "fr", hasPriceEvidence: true }),
    );
    expect(html).toContain("fourchettes ci-dessus");
  });

  it("defaults to the page-neutral sentence when the caller says nothing", () => {
    const html = renderToStaticMarkup(
      createElement(CtaBlock, { config: null, locale: "fr" }),
    );
    expect(html).not.toContain("fourchettes ci-dessus");
  });
});

describe("the content page wires the conditions from the DTO, not from constants", () => {
  it("derives hasPriceEvidence from the answers and hasSources from the sources", () => {
    const source = readFileSync(
      new URL("../app/[slug]/page.tsx", import.meta.url), "utf-8");
    expect(source).toContain("hasPriceEvidence={answers.length > 0}");
    expect(source).toContain("hasSources={sources.length > 0}");
    expect(source).toContain("<SourcesBlock sources={sources} />");
    expect(source).not.toMatch(/<TrustSection\s*\/>/);
  });
});
