import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { App } from "@/App";
import { clearToken, getToken, setToken } from "@/api/token";

/**
 * App-level smoke test: proves the provider stack actually mounts — router,
 * query client, toaster and the index route together — rather than only the
 * leaf components rendering in isolation.
 */
describe("App", () => {
  beforeEach(() => {
    clearToken();
    window.history.pushState({}, "", "/");
  });

  it("mounts and renders the index route", () => {
    render(<App />);
    expect(screen.getByText("Incluir Quiz")).toBeInTheDocument();
  });

  it("renders the login form in Portuguese", () => {
    render(<App />);
    expect(screen.getByText("Entrar")).toBeInTheDocument();
    expect(screen.getByLabelText("CPF")).toBeInTheDocument();
  });

  it("redirects a protected route to the index when there is no token", () => {
    window.history.pushState({}, "", "/quizzes");
    render(<App />);
    // The guard bounces to "/", so the login screen is what renders.
    expect(screen.getByText("Entrar")).toBeInTheDocument();
  });

  it("renders the 404 screen for an unknown path", () => {
    window.history.pushState({}, "", "/no/such/page");
    render(<App />);
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByText("Página não encontrada")).toBeInTheDocument();
  });
});

describe("token storage", () => {
  beforeEach(() => clearToken());

  it("round-trips a token through sessionStorage", () => {
    expect(getToken()).toBeNull();
    setToken("abc=1; def=2");
    expect(getToken()).toBe("abc=1; def=2");
    clearToken();
    expect(getToken()).toBeNull();
  });
});
