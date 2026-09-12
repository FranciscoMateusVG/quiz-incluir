/**
 * `question.config` and answer `response` shapes.
 *
 * `QuestionRead.config` is an untyped dict on the wire, shaped per
 * `question.type` (see app/backend/app/core/question_types.py). The backend
 * strips the answer-key fields for non-admin callers, so only the fields the
 * student UI needs are modelled here.
 *
 * Parsing degrades gracefully rather than throwing, mirroring the backend's
 * own `parse_config`, which returns None on malformed/legacy data so callers
 * can carry on.
 */

import { z } from "zod";

import { type QuestionType } from "./types";

/** Both choice types only need the option list to render. */
const optionsConfig = z.object({ options: z.array(z.string()) });

export type OptionsConfig = z.infer<typeof optionsConfig>;

export function parseOptions(config: Record<string, unknown>): string[] | null {
  const result = optionsConfig.safeParse(config);
  return result.success ? result.data.options : null;
}

// ---------------------------------------------------------------- responses

/**
 * The payload shapes `POST /attempts/{id}/answers` expects. These are graded
 * by `app/backend/app/core/question_types.py` and are not negotiable:
 *
 * - multiple choice compares the option **text**, not its index (the grader
 *   lowercases and strips both sides), so send the string.
 * - true/false compares with a strict `==` against a real boolean, so the
 *   string "true" scores zero.
 */
export type AnswerResponse =
  | { selected: string }
  | { selected: string[] }
  | { selected: boolean }
  | { text: string };

/**
 * The in-progress value an answer component holds. `null` means unanswered,
 * which is what gates the "answer first" toast.
 */
export type AnswerValue = string | string[] | boolean | null;

/** Build the wire payload for a value, or null when there is nothing to send. */
export function toResponse(
  type: QuestionType,
  value: AnswerValue,
): AnswerResponse | null {
  switch (type) {
    case "multiple_choice":
      return typeof value === "string" && value ? { selected: value } : null;
    case "multiple_selection":
      return Array.isArray(value) && value.length > 0
        ? { selected: value }
        : null;
    case "true_false":
      return typeof value === "boolean" ? { selected: value } : null;
    case "short_text": {
      const text = typeof value === "string" ? value.trim() : "";
      return text ? { text } : null;
    }
  }
}

/** Recover a component value from a previously submitted payload. */
export function fromResponse(
  type: QuestionType,
  response: Record<string, unknown> | undefined,
): AnswerValue {
  if (!response) return null;
  switch (type) {
    case "multiple_choice":
      return typeof response.selected === "string" ? response.selected : null;
    case "multiple_selection":
      return Array.isArray(response.selected)
        ? response.selected.filter((v): v is string => typeof v === "string")
        : null;
    case "true_false":
      return typeof response.selected === "boolean" ? response.selected : null;
    case "short_text":
      return typeof response.text === "string" ? response.text : null;
  }
}
