import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import * as api from "@/api/client";
import { errorMessage } from "@/api/errors";
import { useWorkGuard } from "@/api/session";
import { type QuizRead } from "@/api/types";
import { t } from "@/i18n/pt-BR";
import { useAttemptStore } from "@/store/useAttemptStore";

/** Fetches a quiz's questions, starts an attempt, and navigates into it. */
export function useStartQuiz() {
  const navigate = useNavigate();
  const capture = useWorkGuard();
  const startAttempt = useAttemptStore((s) => s.start);

  return useMutation({
    mutationFn: async (quiz: QuizRead) => {
      const current = capture();
      // Guard before creating the attempt. The Flet controller called
      // POST /attempts first and only then checked for questions, leaving an
      // orphan attempt behind for every empty quiz.
      if (quiz.question_ids.length === 0) throw new Error(t.quizHasNoQuestions);

      const questions = await api.getQuestions(quiz.question_ids);
      current();
      const attempt = await api.startAttempt(quiz.id);
      current();
      return { quiz, questions, attempt, current };
    },
    onSuccess: ({ quiz, questions, attempt, current }) => {
      try {
        current();
      } catch {
        return;
      }
      startAttempt(quiz, questions, attempt.id);
      void navigate("/quiz/0");
    },
    onError: (err: unknown) =>
      toast.error(`${t.couldNotStartQuiz}: ${errorMessage(err)}`),
  });
}
