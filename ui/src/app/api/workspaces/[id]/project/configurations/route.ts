import { NextResponse } from "next/server";
import { isServerMode } from "@/lib/server-mode";
import { resolveWritableWorkspace } from "@/lib/workspace-write";
import { validateWriteRequest, sanitizeErrorDetail } from "@/lib/server-validation";
import { ConfigurationInputSchema } from "@/lib/project-schema";
import { setConfiguration, ProjectApiError } from "@/lib/project-api";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/**
 * Upsert one configuration into eval.yaml by id (GRO-550). The validated
 * JSON body is sent to the CLI over stdin only; nothing user-authored ever
 * enters argv.
 */
export async function PUT(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id } = await context.params;
  const writable = resolveWritableWorkspace(id);
  if ("error" in writable) return NextResponse.json({ error: writable.error }, { status: writable.status });
  const { wsPath } = writable;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const parsed = ConfigurationInputSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid configuration", detail: parsed.error.message },
      { status: 400 },
    );
  }

  try {
    const draft = setConfiguration(wsPath, parsed.data, member);
    return NextResponse.json(draft);
  } catch (err) {
    if (err instanceof ProjectApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "failed to save configuration", detail }, { status: 502 });
  }
}
