/**
 * TypeScript mirror of `app/shared/quiz_shared/{schemas,enums}.py`.
 *
 * That Python package is the source of truth, imported by the FastAPI
 * backend. Keep this file field-for-field in sync with it: `UUID` and
 * `datetime` both serialize to JSON strings.
 *
 * These types are hand-written rather than generated because the app disables
 * its OpenAPI schema (`openapi_url=None` in app/backend/main.py).
 */

// ---------------------------------------------------------------- enums

export const QUESTION_TYPES = [
  "multiple_choice",
  "multiple_selection",
  "true_false",
  "short_text",
] as const;
export type QuestionType = (typeof QUESTION_TYPES)[number];

export const MEDIA_TYPES = ["text", "image", "audio", "video"] as const;
export type MediaType = (typeof MEDIA_TYPES)[number];

/** A quiz's CEFR difficulty. Distinct from {@link CourseLevel}. */
export const LANGUAGE_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;
export type LanguageLevel = (typeof LANGUAGE_LEVELS)[number];

/**
 * A student's class/turma. Overlaps {@link LanguageLevel} on the literals
 * "B1"/"B2" but means something different — cohort, not difficulty. The admin
 * level filter and the grade chart group by this one.
 */
export const COURSE_LEVELS = ["B1", "B2", "B3", "B4"] as const;
export type CourseLevel = (typeof COURSE_LEVELS)[number];

export const QUIZ_CATEGORIES = [
  "reading",
  "listening",
  "vocabulary_grammar",
] as const;
export type QuizCategory = (typeof QUIZ_CATEGORIES)[number];

export const USER_ROLES = ["student", "admin"] as const;
export type UserRole = (typeof USER_ROLES)[number];

// ---------------------------------------------------------------- read models

export interface MediaRead {
  id: string;
  question_id: string;
  type: MediaType;
  url: string | null;
  caption: string | null;
  position: number;
}

export interface QuizMediaRead {
  id: string;
  quiz_id: string;
  type: MediaType;
  url: string | null;
  caption: string | null;
  position: number;
}

export interface QuestionRead {
  id: string;
  type: QuestionType;
  prompt: string;
  suggested_score: number;
  /** Shaped per `type`; see `questionConfig` in ./config.ts. */
  config: Record<string, unknown>;
  created_at: string;
  media: MediaRead[];
}

export interface QuizRead {
  id: string;
  title: string;
  description: string | null;
  category: QuizCategory;
  level: LanguageLevel;
  created_at: string;
  updated_at: string;
  /** Already ordered by the quiz_questions.position column. */
  question_ids: string[];
  /** Context shared by the whole quiz (reading passage, listening clip). */
  media: QuizMediaRead[];
}

export interface AnswerRead {
  id: string;
  attempt_id: string;
  question_id: string;
  response: Record<string, unknown>;
  /** Graded server-side and returned immediately. Not surfaced mid-quiz. */
  is_correct: boolean | null;
  points_awarded: number;
  answered_at: string;
}

export interface AttemptRead {
  id: string;
  quiz_id: string;
  user_id: string;
  started_at: string;
  finished_at: string | null;
  /**
   * Normalized onto a 0-10 scale server-side (GRADE_SCALE in
   * app/backend/app/core/grading.py), not raw points. `null` until finished.
   */
  score: number | null;
  /** 10.0, or 0.0 for a quiz with no gradable points — guard the divide. */
  max_score: number;
}

export interface UserRead {
  id: string;
  email: string;
  level: CourseLevel;
  role: UserRole;
  created_at: string;
  updated_at: string;
}

export interface TokenRead {
  /**
   * An opaque BetterAuth session-cookie string relayed from the Programa
   * Incluir monorepo — NOT a JWT. Never try to decode it or read an expiry
   * from it; expiry only ever surfaces as a 401.
   */
  access_token: string;
  token_type: string;
}

export interface AdminAttemptRow {
  attempt_id: string;
  user_id: string;
  email: string;
  level: CourseLevel;
  score: number | null;
  max_score: number;
  finished: boolean;
  finished_at: string | null;
}

export interface QuestionStatRow {
  question_id: string;
  prompt: string;
  correct_count: number;
  incorrect_count: number;
  unanswered_count: number;
}
