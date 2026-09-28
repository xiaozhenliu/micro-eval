import { execFileSync } from "node:child_process";
import { NextResponse } from "next/server";
import { isServerMode, getServerDataRoot } from "@/lib/server-mode";
import { resolveWorkspacePath, readWorkspaceMeta } from "@/lib/workspace-api";
import { validateWriteRequest, uvBin, sanitizeErrorDetail, sanitizePlanBuildDetail, redactDeclaredSecrets, parseCliRefusal } from "@/lib/server-validation";
import { INVALID_GIT_REF_REASON, INVALID_GIT_REF_HINT } from "@/lib/refusal-hints";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/** `replay_canonical.digest` is a SHA-256 hex string. */
const PLAN_DIGEST_RE = /^[a-f0-9]{64}$/;


export async function POST(request: Request, context: RouteContext) {
  if (!isServerMode()) return NextResponse.json({ error: "not found" }, { status: 404 });

  const validation = validateWriteRequest(request);
  if (validation instanceof NextResponse) return validation;
  const { member } = validation;

  const { id } = await context.params;
  const wsPath = resolveWorkspacePath(id);
  if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

  // Fast path; the authoritative check runs inside the CLI under the
  // workspace lock (round-5/round-7 reviews, 2026-09-12/13).
  const meta = readWorkspaceMeta(id);
  if (!meta) return NextResponse.json({ error: "workspace not found" }, { status: 404 });
  if (meta.status !== "active") {
    return NextResponse.json({ error: `workspace is ${meta.status}; only active workspaces can enqueue runs` }, { status: 409 });
  }

  // Optional body: the plan digest the member saw in the preview. It covers
  // task contents, configurations, guardrails and the workspace fingerprint;
  // the CLI refuses when the freshly built plan differs (round-7 review).
  let expectedDigest: string | null = null;
  try {
    const body: unknown = await request.json();
    if (body !== null && typeof body === "object" && Object.prototype.hasOwnProperty.call(body, "config_overrides")) {
      return NextResponse.json({ error: "config_overrides is not supported" }, { status: 400 });
    }
    const candidate = (body as { expected_plan_digest?: unknown } | null)?.expected_plan_digest;
    if (candidate !== undefined && candidate !== null) {
      if (typeof candidate !== "string" || !PLAN_DIGEST_RE.test(candidate)) {
        return NextResponse.json({ error: "invalid expected_plan_digest" }, { status: 400 });
      }
      expectedDigest = candidate;
    }
  } catch {
    // No or non-JSON body: enqueue without a preview digest.
  }

  // Plan build, digest comparison and queue insert happen in one CLI call
  // under the workspace lock (shared with archive/delete) and the config
  // lock (shared with the form editor), so nothing can change in between.
  const args = ["run", "micro-eval", "workspace", "enqueue", id, "--owner", member, "--data-root", getServerDataRoot()];
  if (expectedDigest !== null) args.push("--expected-plan-digest", expectedDigest);

  try {
    const stdout = execFileSync(uvBin(), args, { encoding: "utf-8", timeout: 45_000, maxBuffer: 16 * 1024 * 1024 });
    const result = JSON.parse(stdout.trim()) as Record<string, unknown>;
    return NextResponse.json(result, { status: 202 });
  } catch (err) {
    const refusal = parseCliRefusal(err);
    switch (refusal?.error) {
      case "queue_full":
        return NextResponse.json(refusal, { status: 429 });
      case "workspace_not_active":
        return NextResponse.json(
          { error: `workspace is ${String(refusal.status)}; only active workspaces can enqueue runs` },
          { status: 409 },
        );
      case "plan_changed":
        return NextResponse.json(
          { error: "configuration changed since the preview; review the new preview", plan_digest: refusal.plan_digest ?? null },
          { status: 409 },
        );
      case "workspace_not_found":
        return NextResponse.json({ error: "workspace not found" }, { status: 404 });
      case "plan_build_failed": {
        const body: Record<string, unknown> = {
          error: "failed to build run plan",
          detail: sanitizePlanBuildDetail(String(refusal.detail ?? "")),
        };
        // Only the known structured reason gets the route's own fixed hint;
        // an arbitrary backend hint or git stderr is never forwarded.
        if (refusal.reason === INVALID_GIT_REF_REASON) {
          body.reason = INVALID_GIT_REF_REASON;
          body.hint = INVALID_GIT_REF_HINT;
        }
        return NextResponse.json(body, { status: 502 });
      }
      case "workspace_unavailable":
        return NextResponse.json(
          { error: "workspace is unavailable", detail: redactDeclaredSecrets(sanitizeErrorDetail(String(refusal.detail ?? ""))) },
          { status: 503 },
        );
      default:
        break;
    }
    const detail = sanitizeErrorDetail(err instanceof Error ? err.message : String(err));
    return NextResponse.json({ error: "enqueue failed", detail }, { status: 502 });
  }
}
