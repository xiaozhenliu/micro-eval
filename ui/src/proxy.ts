import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Host header allowlist — CSRF defense layer 4 (anti DNS-rebinding).
 *
 * Next.js 16 renamed the `middleware` file convention to `proxy` (see
 * node_modules/next/dist/docs/.../file-conventions/proxy.md). This runs on the
 * Node.js runtime before every matched route, so `process.env` is available.
 *
 * Only `micro-eval serve` (team server) mode is in scope; local `micro-eval ui`
 * mode is single-user and explicitly out of scope per the security service
 * guidelines appendix, so we pass those requests through untouched.
 *
 * The allowlist is the localhost defaults (built from the bound port) plus any
 * `allowed_hosts` the admin configured in server.json, injected by `serve.py`
 * via MICRO_EVAL_BIND_PORT / MICRO_EVAL_ALLOWED_HOSTS. Building localhost
 * defaults here (rather than trusting the injected list alone) keeps the common
 * case working even if MICRO_EVAL_ALLOWED_HOSTS is empty — fail-open only for
 * loopback, never for arbitrary rebinding targets.
 */
function allowedHosts(): Set<string> {
  const port = process.env.MICRO_EVAL_BIND_PORT || "3000";
  const hosts = [
    `localhost:${port}`,
    `127.0.0.1:${port}`,
    `[::1]:${port}`,
  ];
  for (const h of (process.env.MICRO_EVAL_ALLOWED_HOSTS || "").split(",")) {
    const trimmed = h.trim().toLowerCase();
    if (trimmed) hosts.push(trimmed);
  }
  return new Set(hosts);
}

export function proxy(request: NextRequest) {
  if (process.env.MICRO_EVAL_SERVER_MODE !== "true") {
    return NextResponse.next();
  }
  const host = (request.headers.get("host") || "").toLowerCase();
  if (!allowedHosts().has(host)) {
    return NextResponse.json({ error: "host not allowed" }, { status: 400 });
  }
  return NextResponse.next();
}

export const config = {
  // Run on every route (pages + API) except Next internals and static assets;
  // API write routes are exactly what rebinding would target.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
