import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { QuizApiError } from "@/api/errors";
import { getToken, clearToken } from "@/api/token";
import { LoginScreen } from "@/screens/LoginScreen";

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <LoginScreen />
    </MemoryRouter>,
  );
}

describe("LoginScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearToken();
  });

  it("renders CPF and password fields", () => {
    renderScreen();
    expect(screen.getByLabelText("CPF")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
  });

  it("shows a validation message on empty submit without calling login", async () => {
    const loginSpy = vi.spyOn(api, "login");
    renderScreen();

    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(
      await screen.findByText("Informe seu CPF e sua senha."),
    ).toBeInTheDocument();
    expect(loginSpy).not.toHaveBeenCalled();
  });

  it("stores the token and navigates to /quizzes on success", async () => {
    vi.spyOn(api, "login").mockResolvedValueOnce({
      access_token: "session=abc",
      token_type: "bearer",
    });

    renderScreen();
    await userEvent.type(screen.getByLabelText("CPF"), "12345678900");
    await userEvent.type(screen.getByLabelText("Senha"), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => expect(getToken()).toBe("session=abc"));
  });

  it("shows the mapped error and does not store a token on failure", async () => {
    vi.spyOn(api, "login").mockRejectedValueOnce(
      new QuizApiError(401, "Invalid credentials"),
    );

    renderScreen();
    await userEvent.type(screen.getByLabelText("CPF"), "12345678900");
    await userEvent.type(screen.getByLabelText("Senha"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(
      await screen.findByText("CPF ou senha inválidos."),
    ).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});
