import userEvent from "@testing-library/user-event";
import * as api from "@/api/client";
import { setAuthNotice } from "@/api/session";
import { type UserRead } from "@/api/types";
import { render, screen, act, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

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

describe("retained auth lifecycle", () => {
  beforeEach(() => {
    clearToken();
    window.history.pushState({}, "", "/quizzes");
  });
  afterEach(() => {
    vi.restoreAllMocks();
    setAuthNotice("");
  });
  const user = {
    id: "fixture-user",
    email: "fixture@example.invalid",
    role: "student",
    level: "B1",
    created_at: "2026-01-01Z",
    updated_at: "2026-01-01Z",
  } as UserRead;
  it("blocks retained content pending authority; outage preserves token but no private content", async () => {
    setToken("fixture=token");
    vi.spyOn(api, "me").mockRejectedValue(new Error("offline"));
    const quizzes = vi.spyOn(api, "listQuizzes").mockResolvedValue([]);
    render(<App />);
    expect(screen.getByText("Verificando acesso…")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "Não foi possível verificar sua sessão. Tente novamente.",
      ),
    ).toBeInTheDocument();
    expect(getToken()).toBe("fixture=token");
    expect(quizzes).not.toHaveBeenCalled();
  });
  it("focus invalidates protected UI and late revalidation cannot resurrect logged-out content", async () => {
    setToken("fixture=token");
    let resolve!: (u: UserRead) => void;
    const me = vi
      .spyOn(api, "me")
      .mockResolvedValueOnce(user)
      .mockImplementationOnce(
        () =>
          new Promise((r) => {
            resolve = r;
          }),
      );
    vi.spyOn(api, "listQuizzes").mockResolvedValue([]);
    render(<App />);
    await screen.findByRole("button", { name: /sair/i });
    act(() => window.dispatchEvent(new Event("focus")));
    expect(screen.getByText("Verificando acesso…")).toBeInTheDocument();
    await waitFor(() => expect(me).toHaveBeenCalledTimes(2));
    act(() => clearToken());
    await act(async () => resolve(user));
    expect(screen.getByRole("button", { name: "Entrar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sair/i })).toBeNull();
  });
  it("failed logout clears local access and explicitly warns revocation was not confirmed", async () => {
    setToken("fixture=token");
    vi.spyOn(api, "me").mockResolvedValue(user);
    vi.spyOn(api, "listQuizzes").mockResolvedValue([]);
    vi.spyOn(api, "logout").mockRejectedValue(new Error("unconfirmed"));
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /sair/i }));
    expect(
      await screen.findByText(/não foi possível confirmar o encerramento/),
    ).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});

it("detaching a quiz start between reads prevents the subsequent attempt mutation", async () => {
  let resolve!: (v: Awaited<ReturnType<typeof api.getQuestions>>) => void;
  clearToken();
  setToken("fixture=token");
  window.history.pushState({}, "", "/quizzes");
  vi.spyOn(api, "me").mockResolvedValue({
    id: "fixture",
    email: "fixture@example.invalid",
    role: "student",
  } as UserRead);
  vi.spyOn(api, "listQuizzes").mockResolvedValue([
    {
      id: "quiz-fixture",
      title: "Boundary Quiz",
      description: null,
      category: "reading",
      level: "A1",
      created_at: "2026-01-01Z",
      updated_at: "2026-01-01Z",
      question_ids: ["question-fixture"],
      media: [],
    },
  ]);
  const questions = vi.spyOn(api, "getQuestions").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const create = vi.spyOn(api, "startAttempt");
  const view = render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: /Boundary Quiz/ }),
  );
  await waitFor(() => expect(questions).toHaveBeenCalledOnce());
  view.unmount();
  await act(async () => resolve([]));
  expect(create).not.toHaveBeenCalled();
  vi.restoreAllMocks();
  clearToken();
});
