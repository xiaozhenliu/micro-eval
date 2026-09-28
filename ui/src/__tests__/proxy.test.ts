/**
 * Host header allowlist proxy tests (GRO-173 / audit M1, CSRF layer 4).
 *
 * Covers the design spec §14.6 acceptance cases: an unknown Host header is
 * rejected, and a DNS-rebinding request (attacker domain in Host, resolving to
 * loopback) is rejected. Local `micro-eval ui` mode is out of scope and must
 * pass through.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { proxy, config } from "../proxy";

const ENV_KEYS = [
  "MICRO_EVAL_SERVER_MODE",
  "MICRO_EVAL_BIND_PORT",
  "MICRO_EVAL_ALLOWED_HOSTS",
] as const;

function requestWithHost(host: string | null): NextRequest {
  const headers = new Headers();
  if (host !== null) headers.set("host", host);
  return new NextRequest("http://localhost:3000/api/workspaces", { headers });
}

describe("proxy (Host header allowlist)", () => {
  let saved: Record<string, string | undefined>;

  beforeEach(() => {
    saved = {};
    for (const k of ENV_KEYS) saved[k] = process.env[k];
    delete process.env.MICRO_EVAL_SERVER_MODE;
    delete process.env.MICRO_EVAL_BIND_PORT;
    delete process.env.MICRO_EVAL_ALLOWED_HOSTS;
  });

  afterEach(() => {
    for (const k of ENV_KEYS) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  });

  describe("local (non-server) mode is out of scope", () => {
    it("passes through any host when server mode is off", () => {
      const res = proxy(requestWithHost("evil.example.com:3000"));
      expect(res.status).toBe(200);
    });
  });

  describe("server mode", () => {
    beforeEach(() => {
      process.env.MICRO_EVAL_SERVER_MODE = "true";
      process.env.MICRO_EVAL_BIND_PORT = "3000";
    });

    it.each(["localhost:3000", "127.0.0.1:3000", "[::1]:3000"])(
      "allows loopback default host %j",
      (host) => {
        expect(proxy(requestWithHost(host)).status).toBe(200);
      },
    );

    it("is case-insensitive on the host", () => {
      expect(proxy(requestWithHost("LOCALHOST:3000")).status).toBe(200);
    });

    it("allows an admin-configured host from MICRO_EVAL_ALLOWED_HOSTS", () => {
      process.env.MICRO_EVAL_ALLOWED_HOSTS = "eval.internal:3000, other:3000";
      expect(proxy(requestWithHost("eval.internal:3000")).status).toBe(200);
      expect(proxy(requestWithHost("other:3000")).status).toBe(200);
    });

    // test_host_header_allowlist_rejects_unknown
    it("rejects an unknown host with 400", async () => {
      const res = proxy(requestWithHost("attacker.example.com:3000"));
      expect(res.status).toBe(400);
      expect(await res.json()).toEqual({ error: "host not allowed" });
    });

    // test_host_header_dns_rebinding
    it("rejects a DNS-rebinding host (attacker domain, loopback IP) with 400", () => {
      // After rebinding, the browser still sends the attacker's domain as Host.
      expect(proxy(requestWithHost("rebind.attacker.test:3000")).status).toBe(400);
    });

    it("rejects loopback on a non-bound port", () => {
      expect(proxy(requestWithHost("localhost:9999")).status).toBe(400);
    });

    it("rejects a missing Host header", () => {
      expect(proxy(requestWithHost(null)).status).toBe(400);
    });

    it("rejects a trailing-dot host (no normalization)", () => {
      expect(proxy(requestWithHost("localhost.:3000")).status).toBe(400);
    });

    it("ignores X-Forwarded-Host (only the real Host header counts)", () => {
      const headers = new Headers();
      headers.set("host", "attacker.example.com:3000");
      headers.set("x-forwarded-host", "localhost:3000");
      const req = new NextRequest("http://localhost:3000/api/workspaces", {
        headers,
      });
      expect(proxy(req).status).toBe(400);
    });

    it("tolerates whitespace and empty entries in MICRO_EVAL_ALLOWED_HOSTS", () => {
      process.env.MICRO_EVAL_ALLOWED_HOSTS = " , eval.internal:3000 ,, ";
      expect(proxy(requestWithHost("eval.internal:3000")).status).toBe(200);
      // An empty configured entry must not turn an empty Host into an allow.
      expect(proxy(requestWithHost("")).status).toBe(400);
    });

    it("honours a custom bound port for the loopback defaults", () => {
      process.env.MICRO_EVAL_BIND_PORT = "8080";
      expect(proxy(requestWithHost("localhost:8080")).status).toBe(200);
      expect(proxy(requestWithHost("localhost:3000")).status).toBe(400);
    });
  });

  it("matcher excludes Next internals and static assets", () => {
    expect(config.matcher).toEqual([
      "/((?!_next/static|_next/image|favicon.ico).*)",
    ]);
  });
});
