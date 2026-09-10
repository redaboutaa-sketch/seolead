/**
 * P2 — structured data, shared metadata and the answer-first discipline.
 *
 * The one rule every assertion here defends: structured data that asserts
 * things nobody supplied is fabrication with a schema. Builders return null
 * without their data, the landing's direct answer stays within its 50 words,
 * and the FAQ schema is a projection of the SAME data the visible FAQ renders.
 */
import { describe, expect, it, vi } from "vitest";

import {
  articleNode,
  faqNode,
  graph,
  organizationNode,
  serviceNode,
  webPageNode,
  websiteNode,
} from "@/lib/jsonld";
import { pageMetadata } from "@/lib/metadata";
import type { SiteConfigDTO } from "@/lib/types";

const ORG_EMPTY = {
  legal_name: null, bce_number: null,
  company_number: null, registration_number: null, activities: [],
  address: { street: null, postal_code: null, city: null, country: "BE" },
  phone: null, email: null, service_areas: [], logo_path: null,
  installer_partner: null, certifications: [], same_as: [],
  organization_schema_ready: false, local_business_schema_ready: false,
};

const CONFIG = {
  site_id: "solar_be",
  vertical: "SOLAR_BE",
  brand_name: "Mon Projet Solaire",
  brand_name_is_placeholder: false,
  domain: "monprojetsolaire.be",
  market: "BE",
  default_language: "fr",
  supported_languages: ["fr"],
  staging: true,
  indexable: false,
  locale_paths: { fr: "" },
  contact: {} as SiteConfigDTO["contact"],
  legal: {} as SiteConfigDTO["legal"],
  conversion: {} as SiteConfigDTO["conversion"],
  seo: {
    canonical_origin: "https://monprojetsolaire.be",
    allow_publication: true,
    default_title_suffix: "Mon Projet Solaire",
    default_meta_description: "desc",
    organization_schema: false,
    sitemap_enabled: true,
    allow_indexing: false,
  },
  offer: {
    version: "v0", status: "draft", pending_legal_review: true,
    publishable: false, facts: [], financing: {}, eligibility: {},
    geography: {}, mandatory_disclosures: [],
  },
  organization: ORG_EMPTY,
  routes: [{ path: "/", type: "HOME", locales: ["fr"] }],
} as unknown as SiteConfigDTO;

describe("organization schema readiness", () => {
  it("emits nothing while the identity registry is empty", () => {
    expect(organizationNode(CONFIG)).toBeNull();
  });

  it("carries the operator's real registration (SIREN, no invented BCE)", () => {
    const ready = {
      ...CONFIG,
      organization: {
        ...ORG_EMPTY, legal_name: "Beaver Data Group",
        company_number: "935097675", registration_number: "935097675",
        organization_schema_ready: true,
      },
    } as SiteConfigDTO;
    const node = organizationNode(ready)!;
    expect(node.legalName).toBe("Beaver Data Group");
    expect(node.identifier).toBe("935097675");
    // La marque reste le name public ; l'entité est legalName + identifier.
    expect(node.name).toBe("Mon Projet Solaire");
  });

  it("emits Organization once legal name and BCE exist", () => {
    const ready = {
      ...CONFIG,
      organization: {
        ...ORG_EMPTY, legal_name: "EXEMPLE SRL", bce_number: "0123.456.789",
        organization_schema_ready: true,
      },
    } as SiteConfigDTO;
    const node = organizationNode(ready)!;
    expect(node["@type"]).toBe("Organization");
    expect(node.legalName).toBe("EXEMPLE SRL");
    expect(node.address).toBeUndefined();
  });

  it("upgrades to LocalBusiness only with a place and a contact", () => {
    const ready = {
      ...CONFIG,
      organization: {
        ...ORG_EMPTY, legal_name: "EXEMPLE SRL", bce_number: "0123.456.789",
        phone: "+32 2 000 00 00",
        address: { street: "Rue A 1", postal_code: "1000", city: "Bruxelles",
                   country: "BE" },
        organization_schema_ready: true, local_business_schema_ready: true,
      },
    } as SiteConfigDTO;
    const node = organizationNode(ready)!;
    expect(node["@type"]).toBe("LocalBusiness");
    expect(node.telephone).toBe("+32 2 000 00 00");
  });
});

describe("graph assembly and stable ids", () => {
  it("drops null nodes and anchors ids on the canonical origin", () => {
    const doc = JSON.parse(
      graph(websiteNode(CONFIG), organizationNode(CONFIG))!,
    );
    expect(doc["@graph"]).toHaveLength(1);
    expect(doc["@graph"][0]["@id"]).toBe("https://monprojetsolaire.be/#website");
  });

  it("returns null with no emittable node at all", () => {
    const noOrigin = {
      ...CONFIG, seo: { ...CONFIG.seo, canonical_origin: null },
    } as SiteConfigDTO;
    expect(graph(websiteNode(noOrigin), organizationNode(noOrigin))).toBeNull();
  });

  it("faq nodes carry the page-scoped id and every entry", () => {
    const node = faqNode(CONFIG, "/", [
      { question: "Q1 ?", answer: "R1." },
      { question: "Q2 ?", answer: "R2." },
    ])!;
    expect(node["@id"]).toBe("https://monprojetsolaire.be/#faq");
    expect((node.mainEntity as unknown[]).length).toBe(2);
  });

  it("articles carry their real dates and never an author", () => {
    const node = articleNode(CONFIG, {
      title: "T", locale: "fr", slug: "t",
      published_at: "2026-08-30T18:00:00+00:00",
      updated_at: "2026-08-31T09:00:00+00:00",
    } as never, "/t")!;
    expect(node.datePublished).toBe("2026-08-30T18:00:00+00:00");
    expect(node.dateModified).toBe("2026-08-31T09:00:00+00:00");
    expect("author" in node).toBe(false);
  });

  it("the service node asserts the study service and no price", () => {
    const node = serviceNode(CONFIG, "/panneaux-solaires-sans-apport")!;
    expect(node["@type"]).toBe("Service");
    expect("offers" in node).toBe(false);
    expect("aggregateRating" in node).toBe(false);
  });
});

describe("shared page metadata", () => {
  it("builds canonical and og:url from the configured origin", () => {
    const meta = pageMetadata({
      config: CONFIG, title: "T", description: "D", path: "/x",
    });
    expect(meta.alternates?.canonical).toBe("https://monprojetsolaire.be/x");
    expect((meta.openGraph as { url?: string }).url).toBe(
      "https://monprojetsolaire.be/x");
    expect((meta.openGraph as { siteName?: string }).siteName).toBe(
      "Mon Projet Solaire");
  });

  it("emits no og:image when no real asset exists", () => {
    const meta = pageMetadata({ config: CONFIG, title: "T", path: "/x" });
    expect((meta.openGraph as { images?: unknown }).images).toBeUndefined();
  });

  it("noindex wins over everything, and non-indexable sites never index", () => {
    const meta = pageMetadata({
      config: CONFIG, title: "T", path: "/x", noindex: true,
    });
    expect((meta.robots as { index: boolean }).index).toBe(false);
    const siteOff = pageMetadata({ config: CONFIG, title: "T", path: "/x" });
    expect((siteOff.robots as { index: boolean }).index).toBe(false);
  });

  it("article dates travel only for articles", () => {
    const meta = pageMetadata({
      config: CONFIG, title: "T", path: "/x", type: "article",
      publishedTime: "2026-08-30T18:00:00+00:00",
    });
    expect((meta.openGraph as { publishedTime?: string }).publishedTime).toBe(
      "2026-08-30T18:00:00+00:00");
    const page = pageMetadata({
      config: CONFIG, title: "T", path: "/x",
      publishedTime: "2026-08-30T18:00:00+00:00",
    });
    expect((page.openGraph as { publishedTime?: string }).publishedTime)
      .toBeUndefined();
  });
});

describe("answer-first discipline", () => {
  it("the landing's direct answer holds within 50 words", async () => {
    const source = await import("node:fs/promises").then((fs) =>
      fs.readFile(
        new URL("../app/panneaux-solaires-sans-apport/page.tsx", import.meta.url),
        "utf-8",
      ));
    const match = source.match(
      /const DIRECT_ANSWER =\n((?:\s*"[^"]*"(?: \+)?\n?)+);/);
    expect(match, "DIRECT_ANSWER introuvable dans la landing").toBeTruthy();
    const text = [...(match?.[1] ?? "").matchAll(/"([^"]*)"/g)]
      .map((m) => m[1] ?? "")
      .join("");
    const words = text.trim().split(/\s+/).length;
    expect(words).toBeLessThanOrEqual(50);
    expect(words).toBeGreaterThan(20);
    expect(text).toMatch(/[Ss]elon|sous conditions/);
  });

  it("the home FAQ schema is a projection of the visible FAQ data", async () => {
    const { HOME_FAQ } = await import("@/components/home/Sections");
    expect(HOME_FAQ.length).toBeGreaterThanOrEqual(6);
    const financing = HOME_FAQ.filter(({ question }) =>
      /apport|autofinancer/.test(question));
    expect(financing).toHaveLength(2);
    for (const { answer } of financing) {
      expect(answer).toMatch(/[Ss]elon|peut/);
      // « sans que ce soit garanti » est le désaveu, pas la promesse — seule
      // la forme promissive est interdite ici.
      expect(answer).not.toMatch(/nous garantissons|est garanti|gratuit/i);
    }
    const selfFinancing = financing.find(({ question }) =>
      /autofinancer/.test(question))!;
    expect(selfFinancing.answer).toContain("sans que ce soit garanti");
  });
});

describe("llms.txt gate", () => {
  it("returns 404 while the site is not indexable", async () => {
    vi.doMock("@/lib/api", () => ({
      getSiteConfig: async () => CONFIG,
      listPublished: async () => [],
    }));
    const { GET } = await import("../app/llms.txt/route");
    const response = await GET();
    expect(response.status).toBe(404);
    const body = await response.text();
    expect(body).not.toContain("Accueil");
    vi.doUnmock("@/lib/api");
  });

  it("lists real pages when indexable, and hides the landing while the offer is locked", async () => {
    vi.doMock("@/lib/api", () => ({
      getSiteConfig: async () => ({
        ...CONFIG,
        staging: false,
        indexable: true,
        routes: [
          { path: "/", type: "HOME", locales: ["fr"] },
          { path: "/demande-etude", type: "CONVERSION", locales: ["fr"] },
          { path: "/panneaux-solaires-sans-apport", type: "LANDING_PAGE",
            locales: ["fr"] },
        ],
      }),
      listPublished: async () => [],
    }));
    vi.resetModules();
    const { GET } = await import("../app/llms.txt/route");
    const response = await GET();
    expect(response.status).toBe(200);
    const body = await response.text();
    expect(body).toContain("Mon Projet Solaire");
    expect(body).toContain("/demande-etude");
    expect(body).not.toContain("sans-apport");
    vi.doUnmock("@/lib/api");
  });
});

/* ── Un graphe ne référence jamais un nœud qu'il ne contient pas ────────── */

const READY = {
  ...CONFIG,
  organization: {
    ...ORG_EMPTY, legal_name: "Beaver Data Group",
    company_number: "935097675", registration_number: "935097675",
    organization_schema_ready: true,
  },
} as SiteConfigDTO;

const CONTENT = {
  slug: "prix-panneaux-solaires-belgique",
  locale: "fr",
  title: "Prix des panneaux solaires en Belgique",
  published_at: "2026-09-10T19:13:49.251481+00:00",
  updated_at: "2026-09-10T19:13:49.253942+00:00",
} as never;

/** Les `@id` cités par un graphe et que ce même graphe ne définit pas. */
function danglingReferences(document: string | null): string[] {
  if (!document) return [];
  const nodes = (JSON.parse(document)["@graph"] ?? []) as Record<string, unknown>[];
  const defined = new Set(nodes.map((n) => n["@id"]).filter(Boolean) as string[]);
  const referenced: string[] = [];
  const walk = (value: unknown): void => {
    if (Array.isArray(value)) return value.forEach(walk);
    if (!value || typeof value !== "object") return;
    const entries = Object.entries(value as Record<string, unknown>);
    const keys = entries.map(([k]) => k);
    // Une référence est un objet qui ne porte QUE `@id` : le nœud défini, lui,
    // porte aussi son `@type`.
    if (keys.length === 1 && keys[0] === "@id") {
      referenced.push(String((value as Record<string, unknown>)["@id"]));
      return;
    }
    entries.forEach(([, v]) => walk(v));
  };
  nodes.forEach(walk);
  return referenced.filter((id) => !defined.has(id));
}

describe("graph integrity — every @id a graph cites, it defines", () => {
  it("detects the dangling publisher an article page used to emit", () => {
    // Le défaut du 2026-09-10, tel qu'il était : `articleNode` et
    // `websiteNode` portaient tous deux `publisher: {@id: …/#organization}`,
    // et ce nœud n'était pas dans le graphe de la page article. Le détecteur
    // doit le voir, sinon le test suivant ne prouve rien.
    const incomplet = graph(
      websiteNode(READY),
      articleNode(READY, CONTENT, "/prix-panneaux-solaires-belgique"),
    );
    expect(danglingReferences(incomplet)).toContain(
      "https://monprojetsolaire.be/#organization",
    );
  });

  it("an article page graph resolves every reference it makes", () => {
    const complet = graph(
      websiteNode(READY),
      organizationNode(READY),
      articleNode(READY, CONTENT, "/prix-panneaux-solaires-belgique"),
    );
    expect(danglingReferences(complet)).toEqual([]);
  });

  it("a home page graph resolves every reference it makes", () => {
    const home = graph(
      websiteNode(READY),
      organizationNode(READY),
      faqNode(READY, "/", [{ question: "Est-ce gratuit ?", answer: "Oui." }]),
    );
    expect(danglingReferences(home)).toEqual([]);
  });

  it("a conversion page graph resolves every reference it makes", () => {
    const conversion = graph(
      websiteNode(READY),
      organizationNode(READY),
      webPageNode(READY, "/demande-etude", "Demander une estimation", "…"),
    );
    expect(danglingReferences(conversion)).toEqual([]);
  });

  it("emits no organization node, and no reference to one, while the registry is empty", () => {
    const sansIdentite = graph(
      websiteNode(CONFIG),
      organizationNode(CONFIG),
      articleNode(CONFIG, CONTENT, "/prix-panneaux-solaires-belgique"),
    );
    expect(danglingReferences(sansIdentite)).toEqual([]);
    expect(sansIdentite).not.toContain("#organization");
  });
});
