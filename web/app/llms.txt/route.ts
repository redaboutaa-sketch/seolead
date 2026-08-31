import { getSiteConfig, listPublished } from "@/lib/api";
import { contentPath, localizedPath } from "@/lib/site";

/**
 * `/llms.txt` — the site, summarised for an agent that reads before it crawls.
 *
 * Same philosophy as the sitemap, enforced the same way: this file is a
 * publication act. While the site is not indexable it returns 404 and exposes
 * nothing — staging content summarised for an LLM is staging content leaked.
 * And it only ever describes what is real: identity lines appear when the
 * organization registry carries them, offer lines when the offer registry is
 * publishable, content lines for PUBLISHED pages. Nothing here is a dump of
 * the site, and nothing here is invented for the reader.
 */
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const config = await getSiteConfig();
  if (!config?.indexable) {
    return new Response("Not found", { status: 404 });
  }

  const base = (config.seo.canonical_origin ?? "").replace(/\/$/, "");
  const locale = config.default_language;
  const lines: string[] = [];

  lines.push(`# ${config.brand_name}`);
  lines.push("");
  lines.push(
    "> Photovoltaïque résidentiel en Belgique : qualification de projet et " +
    "estimation personnalisée. Les montants publiés citent leur source ; " +
    "quand une source ne précise pas, le site le dit plutôt que de supposer.",
  );
  lines.push("");

  const org = config.organization;
  if (org.legal_name) {
    lines.push(`Entité légale : ${org.legal_name}` +
      (org.bce_number ? ` (BCE ${org.bce_number})` : ""));
  }
  if (org.service_areas.length) {
    lines.push(`Zone d'intervention : ${org.service_areas.join(", ")}`);
  } else {
    lines.push(`Marché : Belgique (${config.market})`);
  }
  lines.push("");

  lines.push("## Pages principales");
  lines.push(`- [Accueil](${base}${localizedPath(config, locale, "/")})`);
  const labels: Record<string, string> = {
    "/demande-etude": "Demander une estimation personnalisée",
    "/outils/estimation-solaire": "Cadrer votre projet (méthode)",
    "/panneaux-solaires-sans-apport":
      "Installer des panneaux solaires sans apport en Belgique",
    "/confidentialite": "Politique de confidentialité",
    "/conditions": "Conditions d'utilisation",
  };
  for (const route of config.routes) {
    const label = labels[route.path];
    if (!label) continue;
    if (route.path === "/panneaux-solaires-sans-apport" &&
        !config.offer?.publishable) continue;
    if (!route.locales.includes(locale)) continue;
    lines.push(`- [${label}](${base}${localizedPath(config, locale, route.path)})`);
  }
  lines.push("");

  const published = await listPublished(locale);
  if (published.length) {
    lines.push("## Contenus de référence");
    for (const item of published) {
      lines.push(`- [${item.title}](${base}${contentPath(config, item)})`);
    }
    lines.push("");
  }

  if (config.offer?.publishable && config.offer.facts.length) {
    lines.push("## Offre (faits validés)");
    for (const fact of config.offer.facts) {
      lines.push(`- ${fact.label} : ${String(fact.value)}` +
        (fact.unit ? ` ${fact.unit}` : ""));
    }
    lines.push("");
  }

  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
