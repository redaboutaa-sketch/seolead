import { createHash } from "node:crypto";
import { NextResponse } from "next/server";

import { postLead } from "@/lib/api";

/**
 * Browser → this route → the factory API.
 *
 * The proxy exists so the internal key stays on the server. It also derives the
 * rate-limiting key here rather than trusting the client to send one: a bot that
 * chooses its own bucket is not rate-limited.
 *
 * The IP is hashed with a per-deployment salt and never stored — it exists for the
 * duration of the request, as a spam-bucket key, and nothing more.
 */
export const dynamic = "force-dynamic";

function clientKey(request: Request): string | null {
  const forwarded = request.headers.get("x-forwarded-for");
  const ip = forwarded?.split(",")[0]?.trim() || request.headers.get("x-real-ip");
  if (!ip) return null;
  const salt = process.env.SEOLEAD_CLIENT_KEY_SALT ?? "seolead-local";
  return createHash("sha256").update(`${salt}:${ip}`).digest("hex").slice(0, 32);
}

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Requête illisible." }, { status: 400 });
  }

  try {
    const result = await postLead(payload, clientKey(request));
    if (result.status >= 200 && result.status < 300) {
      return NextResponse.json(
        { lead_id: result.body?.lead_id, state: result.body?.state },
        { status: 201 },
      );
    }
    // The API's refusal messages name fields, never values, so they are safe to
    // show. Anything unexpected becomes a generic message rather than an echo.
    const detail = (result.body as { detail?: { message?: string } })?.detail;
    return NextResponse.json(
      { message: detail?.message ?? "Votre demande n'a pas pu être enregistrée." },
      { status: result.status === 422 ? 422 : 400 },
    );
  } catch {
    return NextResponse.json(
      { message: "Service momentanément indisponible." },
      { status: 503 },
    );
  }
}
