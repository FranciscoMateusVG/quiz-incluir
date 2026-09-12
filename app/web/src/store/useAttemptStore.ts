/**
 * The in-flight quiz attempt.
 *
 * Replaces the parts of `app/frontend/state/app_state.py` that describe an
 * attempt in progress. Two deliberate differences from the Flet original:
 *
 *  - `current_index` is gone. The URL owns it now (`/quiz/:index`), so the
 *    back button and a pasted link both mean something. The Flet screen
 *    declared `:index` but ignored it, driving off in-memory state instead.
 *  - It persists to sessionStorage, so refreshing mid-quiz keeps your answers
 *    instead of dumping you back at the picker.
 *
 * sessionStorage (not localStorage) keeps this tab-scoped and self-cleaning,
 * which suits a transient attempt.
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import {
  type AttemptRead,
  type QuestionRead,
  type QuizRead,
} from "@/api/types";

interface AttemptState {
  quiz: QuizRead | null;
  questions: QuestionRead[];
  attemptId: string | null;
  /** question id -> the response payload that was submitted for it */
  answers: Record<string, Record<string, unknown>>;
  finished: boolean;
  result: AttemptRead | null;

  start: (quiz: QuizRead, questions: QuestionRead[], attemptId: string) => void;
  recordAnswer: (questionId: string, response: Record<string, unknown>) => void;
  finishWith: (result: AttemptRead) => void;
  reset: () => void;
}

const EMPTY: Pick<
  AttemptState,
  "quiz" | "questions" | "attemptId" | "answers" | "finished" | "result"
> = {
  quiz: null,
  questions: [],
  attemptId: null,
  answers: {},
  finished: false,
  result: null,
};

export const useAttemptStore = create<AttemptState>()(
  persist(
    (set) => ({
      ...EMPTY,

      start: (quiz, questions, attemptId) =>
        set({ ...EMPTY, quiz, questions, attemptId }),

      // Whole-object replacement, as the Flet controller already did:
      // state.answers = {**state.answers, qid: response}
      recordAnswer: (questionId, response) =>
        set((state) => ({
          answers: { ...state.answers, [questionId]: response },
        })),

      finishWith: (result) => set({ finished: true, result }),

      reset: () => set({ ...EMPTY }),
    }),
    {
      name: "quiz.attempt",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

/** True once an attempt is loaded and answerable. */
export function hasActiveAttempt(state: AttemptState): boolean {
  return state.attemptId !== null && state.questions.length > 0;
}
