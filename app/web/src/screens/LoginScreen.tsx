import { GraduationCap } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import * as api from "@/api/client";
import { mapLoginError } from "@/api/errors";
import { setToken } from "@/api/token";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n/pt-BR";

/**
 * Sign-in, matching monorepo-incluir's own login screens: CPF + password,
 * no masking or format validation client-side (the server is authoritative
 * there — see `api/client.ts::login`), "Entrar" / "Entrando..." copy taken
 * straight from those screens.
 *
 * No sign-up link: this backend has no signup endpoint, since accounts are
 * provisioned by the monorepo, not by this app. No working forgot-password
 * flow either — that lives entirely in the monorepo's own apps/frontend
 * (email delivery, reset tokens); this screen just points there.
 */
export function LoginScreen() {
  const navigate = useNavigate();
  const [cpf, setCpf] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedCpf = cpf.trim();
    if (!trimmedCpf || !password) {
      setError(t.loginFieldsRequired);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const result = await api.login(trimmedCpf, password);
      setToken(result.access_token);
      void navigate("/quizzes");
    } catch (err) {
      setError(mapLoginError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md space-y-6 p-10">
        <div className="flex flex-col items-center gap-4 text-center">
          <span className="flex size-20 items-center justify-center rounded-full bg-primary">
            <GraduationCap className="size-10 text-primary-foreground" />
          </span>
          <div>
            <h1 className="text-3xl font-bold">{t.appTitle}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {t.loginSubtitle}
            </p>
          </div>
        </div>

        <form onSubmit={(e) => void submit(e)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="cpf">{t.cpfLabel}</Label>
            <Input
              id="cpf"
              value={cpf}
              onChange={(e) => {
                setCpf(e.target.value);
                setError("");
              }}
              inputMode="numeric"
              autoComplete="username"
              placeholder={t.cpfPlaceholder}
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">{t.passwordLabel}</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError("");
              }}
              autoComplete="current-password"
              placeholder={t.passwordPlaceholder}
            />
          </div>

          {error ? (
            <p className="rounded-input bg-destructive-light px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? t.signingIn : t.signIn}
          </Button>
        </form>

        <p className="text-center text-xs text-muted-foreground">
          {t.loginAccountHint}
        </p>
      </Card>
    </div>
  );
}
