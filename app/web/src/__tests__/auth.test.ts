import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { QuizApiError, mapLoginError } from "@/api/errors";

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("login", () => {
  // A plain fn swapped onto globalThis.fetch and restored per test, rather
  // than vi.spyOn: two `describe` blocks in this file both mock the same
  // global, and re-spying an already-spied global (or using mockReset()
  // instead of a full restore) previously leaked one block's mock into the
  // other's tests.
  const originalFetch = globalThis.fetch;
  let fetchSpy: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("sends form-encoded username/password to /auth/token", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(200, { access_token: "cookie=1", token_type: "bearer" }),
    );

    await api.login("12345678900", "hunter2");

    const [url, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
    expect(url).toMatch(/\/auth\/token$/);
    expect(init.headers).toMatchObject({
      "Content-Type": "application/x-www-form-urlencoded",
    });
    expect((init.body as URLSearchParams).toString()).toBe(
      "username=12345678900&password=hunter2",
    );
  });

  it("surfaces the backend's real status on invalid credentials", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(401, { detail: "Invalid credentials" }),
    );

    await expect(api.login("12345678900", "wrong")).rejects.toMatchObject({
      status: 401,
      detail: "Invalid credentials",
    });
  });

  it("distinguishes a 503 (service unreachable) from a 401 (bad credentials)", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(503, {
        detail: "Could not reach the authentication service",
      }),
    );

    await expect(api.login("12345678900", "x")).rejects.toMatchObject({
      status: 503,
    });
  });

  it("extracts Retry-After from a 429 response", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        429,
        { detail: "Too many sign-in attempts" },
        { "retry-after": "7" },
      ),
    );

    await expect(api.login("12345678900", "x")).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: 7,
    });
  });

  it("leaves retryAfterSeconds undefined when there is no header", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(401, { detail: "Invalid credentials" }),
    );

    try {
      await api.login("12345678900", "x");
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(QuizApiError);
      expect((err as QuizApiError).retryAfterSeconds).toBeUndefined();
    }
  });
});

describe("logout", () => {
  const originalFetch = globalThis.fetch;
  let fetchSpy: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("posts to /auth/logout", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await api.logout();
    const [url, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
    expect(url).toMatch(/\/auth\/logout$/);
    expect(init.method).toBe("POST");
  });

  it("never throws, even if the request fails", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("network down"));
    await expect(api.logout()).resolves.toBeUndefined();
  });
});

describe("mapLoginError", () => {
  it("maps 401 to invalid-credentials copy", () => {
    expect(mapLoginError(new QuizApiError(401, "Invalid credentials"))).toMatch(
      /CPF ou senha inválidos/,
    );
  });

  it("maps 429 with a retry time when present", () => {
    expect(
      mapLoginError(new QuizApiError(429, "Too many sign-in attempts", 12)),
    ).toMatch(/12s/);
  });

  it("maps 429 without a retry time to a generic rate-limit message", () => {
    expect(
      mapLoginError(new QuizApiError(429, "Too many sign-in attempts")),
    ).toMatch(/Muitas tentativas/);
  });

  it("maps 503 to a service-unavailable message", () => {
    expect(
      mapLoginError(
        new QuizApiError(503, "Sign-in is temporarily unavailable"),
      ),
    ).toMatch(/indisponível/);
  });

  it("maps 422 to the required-fields message", () => {
    expect(
      mapLoginError(new QuizApiError(422, "cpf and password are required")),
    ).toMatch(/CPF e sua senha/);
  });

  it("falls back to a generic message for anything else", () => {
    expect(mapLoginError(new QuizApiError(500, "boom"))).toMatch(
      /Não foi possível entrar/,
    );
    expect(mapLoginError(new Error("not even a QuizApiError"))).toMatch(
      /Não foi possível entrar/,
    );
  });
});
