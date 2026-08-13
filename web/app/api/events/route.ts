import { NextResponse } from "next/server";

import { postEvent } from "@/lib/api";

/**
 * First-party funnel events. Fire-and-forget by design: analytics must never be
 * able to fail a page or block a form.
 */
export const dynamic = "force-dynamic";

const ALLOWED = new Set([
  "PAGE_VIEW", "CTA_CLICK", "FORM_STARTED", "FORM_STEP_COMPLETED",
  "FORM_SUBMITTED", "LEAD_CREATED",
]);

export async function POST(request: Request) {
  let payload: { event_type?: string } = {};
  try {
    payload = (await request.json()) as { event_type?: string };
  } catch {
    return NextResponse.json({ recorded: false }, { status: 400 });
  }
  if (!payload.event_type || !ALLOWED.has(payload.event_type)) {
    return NextResponse.json({ recorded: false }, { status: 422 });
  }
  await postEvent(payload);
  return NextResponse.json({ recorded: true }, { status: 202 });
}
