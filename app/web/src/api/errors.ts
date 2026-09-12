import { t } from "@/i18n/pt-BR";

/** Mirrors `app/frontend/services/exceptions.py::QuizApiError`. */
export class QuizApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    /** Seconds to wait before retrying, from a 429's `Retry-After` header. */
    readonly retryAfterSeconds?: number,
  ) {
    super(detail);
    this.name = "QuizApiError";
  }
}

export function isForbidden(error: unknown): boolean {
  return error instanceof QuizApiError && error.status === 403;
}

/**
 * A displayable message from an unknown thrown value.
 *
 * TanStack Query types its `error` as `{}` unless a global error type is
 * registered, so screens cannot reach `.message` directly.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof QuizApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return String(error);
}

/**
 * Portuguese message for a failed sign-in attempt.
 *
 * The backend's `detail` strings stay in English, matching how the rest of
 * this codebase handles API errors (see `AdminGrades`'s `isForbidden`
 * branch) — known cases get a proper Portuguese message client-side rather
 * than the raw string. This deliberately does NOT copy monorepo-incluir's
 * own habit of showing BetterAuth's raw English messages straight through a
 * Portuguese UI; that's a rough edge there, not a convention worth keeping.
 */
export function mapLoginError(error: unknown): string {
  if (!(error instanceof QuizApiError)) return t.loginErrorGeneric;

  switch (error.status) {
    case 401:
      return t.loginErrorInvalidCredentials;
    case 429:
      return error.retryAfterSeconds
        ? t.loginErrorRateLimited(error.retryAfterSeconds)
        : t.loginErrorRateLimitedGeneric;
    case 503:
      return t.loginErrorServiceUnavailable;
    case 422:
      return t.loginFieldsRequired;
    default:
      return t.loginErrorGeneric;
  }
}
