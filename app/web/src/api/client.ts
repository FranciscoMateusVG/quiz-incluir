/**
 * Typed HTTP client for the Quiz backend, porting
 * `app/frontend/services/api.py::QuizApiClient`.
 */

import { QuizApiError } from "./errors";
import { getToken } from "./token";
import {
  type AdminAttemptRow,
  type AnswerRead,
  type AttemptRead,
  type CourseLevel,
  type QuestionRead,
  type QuestionStatRow,
  type QuizRead,
  type TokenRead,
  type UserRead,
} from "./types";
import { type AnswerResponse } from "./config";

/** Same-origin in production, where FastAPI serves this bundle itself. */
const BASE_URL = (
  (import.meta.env.VITE_API_URL as string | undefined) ?? ""
).replace(/\/$/, "");

const API = `${BASE_URL}/api/v1`;

function headers(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

/**
 * Turn a response into data, or throw a {@link QuizApiError}.
 *
 * Mirrors `_handle()` in the Python client: prefer the JSON `detail` field for
 * the message and fall back to the raw body.
 *
 * The content-type check is not defensive boilerplate. The backend mounts this
 * SPA as a catch-all at `/`, and its collection routes are declared as
 * `@router.get("")` — so a stray trailing slash (`/api/v1/quizzes/`) misses the
 * API route, gets picked up by the SPA mount, and returns `index.html` with a
 * **200**. Parsing that as JSON would fail with a confusing syntax error, so
 * name the real problem instead.
 */
async function handle(resp: Response, path: string): Promise<unknown> {
  if (!resp.ok) {
    const body = await resp.text();
    let detail = body;
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed && typeof parsed === "object" && "detail" in parsed) {
        const d = parsed.detail;
        if (typeof d === "string") detail = d;
      }
    } catch {
      /* not JSON; keep the raw text */
    }
    // Only login's 429 sets this today, but reading it here rather than in
    // a one-off login()-specific branch means any future rate-limited
    // endpoint gets the same behavior for free.
    const retryAfter = resp.headers.get("retry-after");
    const retryAfterSeconds = retryAfter
      ? Number.parseInt(retryAfter, 10)
      : undefined;
    throw new QuizApiError(
      resp.status,
      detail || resp.statusText,
      Number.isFinite(retryAfterSeconds) ? retryAfterSeconds : undefined,
    );
  }

  if (resp.status === 204) return null;

  const contentType = resp.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new QuizApiError(
      resp.status,
      `Esperava JSON de ${path}, recebeu "${contentType}". ` +
        `Uma barra final faz a rota cair no SPA e retornar index.html.`,
    );
  }

  return resp.json();
}

async function get(path: string): Promise<unknown> {
  return handle(await fetch(`${API}${path}`, { headers: headers() }), path);
}

async function post(path: string, body?: unknown): Promise<unknown> {
  return handle(
    await fetch(`${API}${path}`, {
      method: "POST",
      headers: headers(),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
    path,
  );
}

// ---------------------------------------------------------------- auth

/**
 * `POST /auth/token` takes form encoding, not JSON.
 *
 * `identifier` is a CPF — every login screen in monorepo-incluir (including
 * its own public app) authenticates by CPF rather than email, and the quiz
 * backend now expects the same (see monorepo_auth.py::sign_in). Sent as-is,
 * with no client-side masking or check-digit validation, matching how the
 * monorepo's own standalone apps handle it: the server is authoritative.
 */
export async function login(
  identifier: string,
  password = "",
): Promise<TokenRead> {
  const resp = await fetch(`${API}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: identifier, password }),
  });
  return (await handle(resp, "/auth/token")) as TokenRead;
}

/**
 * Revoke the session server-side. Best-effort from the caller's point of
 * view: a network hiccup here must not block sign-out, so failures are
 * swallowed rather than thrown.
 */
export async function logout(): Promise<void> {
  try {
    await fetch(`${API}/auth/logout`, { method: "POST", headers: headers() });
  } catch {
    /* sign-out proceeds locally regardless */
  }
}

export async function me(): Promise<UserRead> {
  return (await get("/users/me")) as UserRead;
}

// ---------------------------------------------------------------- quizzes

export async function listQuizzes(): Promise<QuizRead[]> {
  return (await get("/quizzes")) as QuizRead[];
}

export async function getQuestion(questionId: string): Promise<QuestionRead> {
  return (await get(`/questions/${questionId}`)) as QuestionRead;
}

/**
 * Fetch a quiz's questions in `question_ids` order, concurrently rather than
 * in a loop. Every authenticated request costs an uncached outbound call to
 * the auth service, so a serial fetch would mean N round-trips for an
 * N-question quiz.
 */
export async function getQuestions(
  questionIds: string[],
): Promise<QuestionRead[]> {
  return Promise.all(questionIds.map(getQuestion));
}

// ---------------------------------------------------------------- attempts

export async function startAttempt(quizId: string): Promise<AttemptRead> {
  return (await post("/attempts", { quiz_id: quizId })) as AttemptRead;
}

export async function submitAnswer(
  attemptId: string,
  questionId: string,
  response: AnswerResponse,
): Promise<AnswerRead> {
  return (await post(`/attempts/${attemptId}/answers`, {
    question_id: questionId,
    response,
  })) as AnswerRead;
}

export async function finishAttempt(attemptId: string): Promise<AttemptRead> {
  return (await post(`/attempts/${attemptId}/finish`)) as AttemptRead;
}

/**
 * Fetch the report as a blob. The endpoint needs the auth header, so this
 * cannot be a plain link — the caller instead makes an object URL and clicks
 * a temporary anchor.
 */
export async function downloadReportPdf(attemptId: string): Promise<Blob> {
  const path = `/attempts/${attemptId}/report.pdf`;
  const resp = await fetch(`${API}${path}`, { headers: headers() });
  if (!resp.ok) {
    const body = await resp.text();
    let detail = body;
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed && typeof parsed === "object" && "detail" in parsed) {
        const d = parsed.detail;
        if (typeof d === "string") detail = d;
      }
    } catch {
      /* not JSON; keep the raw text */
    }
    throw new QuizApiError(resp.status, detail || resp.statusText);
  }
  return resp.blob();
}

// ---------------------------------------------------------------- admin

function levelQuery(level: CourseLevel | ""): string {
  return level ? `?level=${encodeURIComponent(level)}` : "";
}

export async function adminListAttempts(
  quizId: string,
  level: CourseLevel | "" = "",
): Promise<AdminAttemptRow[]> {
  return (await get(
    `/admin/quizzes/${quizId}/attempts${levelQuery(level)}`,
  )) as AdminAttemptRow[];
}

export async function adminQuestionStats(
  quizId: string,
  level: CourseLevel | "" = "",
): Promise<QuestionStatRow[]> {
  return (await get(
    `/admin/quizzes/${quizId}/question-stats${levelQuery(level)}`,
  )) as QuestionStatRow[];
}
