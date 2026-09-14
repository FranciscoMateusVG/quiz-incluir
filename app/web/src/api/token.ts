import { invalidateWork } from "./session";

/**
 * Single source of truth for the API token.
 *
 * The token is an opaque BetterAuth session-cookie string, not a JWT — it
 * cannot be inspected for an expiry, so staleness only shows up as a 401.
 *
 * sessionStorage rather than localStorage: it is scoped to the tab and
 * cleared when the tab closes, a safer default for a credential we cannot
 * expire ourselves.
 */

const KEY = "quiz.token";

/** Fallback for private-mode browsers where sessionStorage throws. */
let memoryToken: string | null = null;
let revision = 0;
export const tokenRevision = () => revision;

export function getToken(): string | null {
  try {
    return window.sessionStorage.getItem(KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

export function setToken(token: string): void {
  revision++;
  try {
    window.sessionStorage.removeItem("quiz.attempt");
  } catch {
    /* unavailable storage */
  }
  memoryToken = token;
  try {
    window.sessionStorage.setItem(KEY, token);
  } catch {
    /* memory-only is an acceptable degradation */
  }
  invalidateWork();
}

export function clearToken(): void {
  revision++;
  memoryToken = null;
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* nothing to clean up */
  }
  invalidateWork();
}

/**
 * A dev-only seed so the app is usable before sign-in exists. Vite inlines
 * `import.meta.env.DEV` as a literal, so this branch is dropped from the
 * production bundle entirely.
 */
export function seedDevToken(): void {
  if (!import.meta.env.DEV) return;
  const fromEnv = import.meta.env.VITE_DEV_TOKEN as string | undefined;
  if (fromEnv && !getToken()) setToken(fromEnv);
}
