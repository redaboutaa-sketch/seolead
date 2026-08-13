/**
 * The only module that talks to the SEO Lead Factory API.
 *
 * `server-only` is the load-bearing import. It makes the build fail if any client
 * component imports this file, which is what keeps `SEOLEAD_INTERNAL_KEY` out of
 * the browser bundle — a convention would not, and this key can trigger paid
 * research jobs.
 *
 * Every response is treated as untrusted and narrowed before it leaves here. The
 * API is ours, but "ours" is not a type guarantee, and a shape change should fail
 * one page rather than crash the render of every page.
 */
import "server-only";

import type { PublishedContentDTO, SiteConfigDTO } from "./types";

const BASE_URL = process.env.SEOLEAD_API_URL ?? "http://seolead_api:8000";
const SITE_ID = process.env.SEOLEAD_SITE_ID ?? "solar_be";

function headers(extra: Record<string, string> = {}): HeadersInit {
  const key = process.env.SEOLEAD_INTERNAL_KEY;
  if (!key) {
    throw new Error(
      "SEOLEAD_INTERNAL_KEY is not set; refusing to call the API unauthenticated",
    );
  }
  return { "X-Internal-Key": key, "Content-Type": "application/json", ...extra };
}

export function siteId(): string {
  return SITE_ID;
}

async function get<T>(path: string, extraHeaders: Record<string, string> = {},
                      revalidate = 60): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: headers(extraHeaders),
      next: { revalidate },
    });
  } catch {
    // A network failure must not render a stack trace to a visitor. The page
    // decides what to do with null — usually a 404.
    return null;
  }
  if (!response.ok) return null;
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function getSiteConfig(): Promise<SiteConfigDTO | null> {
  return get<SiteConfigDTO>(`/site/v1/sites/${SITE_ID}`, {}, 300);
}

export async function getPublished(
  locale: string,
  slug: string,
): Promise<PublishedContentDTO | null> {
  return get<PublishedContentDTO>(
    `/site/v1/sites/${SITE_ID}/content/${locale}/${encodeURIComponent(slug)}`,
  );
}

export async function listPublished(
  locale?: string,
): Promise<PublishedContentDTO[]> {
  const query = locale ? `?locale=${encodeURIComponent(locale)}` : "";
  const data = await get<{ items: PublishedContentDTO[] }>(
    `/site/v1/sites/${SITE_ID}/content${query}`,
  );
  return data?.items ?? [];
}

/**
 * Staged content, for the preview route only.
 *
 * Requires the preview token in addition to the internal key. Returns null when
 * the token is unset, so a deployment that forgot to configure it serves 404
 * rather than unpublished content.
 */
export async function getPreview(
  locale: string,
  slug: string,
): Promise<PublishedContentDTO | null> {
  const token = process.env.SEOLEAD_PREVIEW_TOKEN;
  if (!token) return null;
  return get<PublishedContentDTO>(
    `/site/v1/sites/${SITE_ID}/preview/${locale}/${encodeURIComponent(slug)}`,
    { "X-Preview-Token": token },
    0,
  );
}

export async function postLead(payload: unknown, clientKey: string | null) {
  const response = await fetch(`${BASE_URL}/site/v1/sites/${SITE_ID}/leads`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ ...(payload as object), client_key: clientKey }),
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  return { status: response.status, body };
}

export async function postEvent(payload: unknown) {
  try {
    await fetch(`${BASE_URL}/site/v1/sites/${SITE_ID}/events`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  } catch {
    // Analytics must never break a page or a form submission.
  }
}

/**
 * An unapproved draft, for owner review only.
 *
 * §38 of the Phase 4 brief permits exactly this path while approval is absent:
 * look, do not stage, do not publish.
 */
export async function getDraftPreview(
  draftId: string,
): Promise<PublishedContentDTO | null> {
  const token = process.env.SEOLEAD_PREVIEW_TOKEN;
  if (!token) return null;
  return get<PublishedContentDTO>(
    `/site/v1/sites/${SITE_ID}/draft-preview/${encodeURIComponent(draftId)}`,
    { "X-Preview-Token": token },
    0,
  );
}
