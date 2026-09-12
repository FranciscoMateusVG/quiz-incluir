import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import * as api from "@/api/client";
import { fromResponse, toResponse, type AnswerValue } from "@/api/config";
import { errorMessage } from "@/api/errors";
import { AnswerInput } from "@/components/answers/AnswerInput";
import { MediaBlock } from "@/components/MediaBlock";
import { ProgressDots } from "@/components/ProgressDots";
import { QuestionCard } from "@/components/QuestionCard";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n/pt-BR";
import { useAttemptStore } from "@/store/useAttemptStore";

export function Question() {
  const { index } = useParams();
  const navigate = useNavigate();

  const quiz = useAttemptStore((s) => s.quiz);
  const questions = useAttemptStore((s) => s.questions);
  const attemptId = useAttemptStore((s) => s.attemptId);
  const answers = useAttemptStore((s) => s.answers);
  const recordAnswer = useAttemptStore((s) => s.recordAnswer);
  const finishWith = useAttemptStore((s) => s.finishWith);

  const total = questions.length;
  const parsed = Number.parseInt(index ?? "0", 10);
  const current = Number.isNaN(parsed) ? 0 : parsed;

  const question = questions[current];

  // The answer for *this* question, seeded from whatever was submitted before
  // so going Back shows your previous choice (the Flet screen rehydrated the
  // widget the same way, via `widget.build(previous)`).
  const [value, setValue] = useState<AnswerValue>(null);

  useEffect(() => {
    if (!question) return;
    setValue(fromResponse(question.type, answers[question.id]));
  }, [question?.id]);

  const answeredIndices = useMemo(
    () =>
      new Set(
        questions.reduce<number[]>(
          (acc, q, i) => (q.id in answers ? [...acc, i] : acc),
          [],
        ),
      ),
    [questions, answers],
  );

  const submit = useMutation({
    mutationFn: async () => {
      if (!question || !attemptId) throw new Error("no active attempt");

      const response = toResponse(question.type, value);
      if (!response) return { skipped: true as const };

      await api.submitAnswer(attemptId, question.id, response);
      recordAnswer(question.id, response);

      if (current >= total - 1) {
        const result = await api.finishAttempt(attemptId);
        finishWith(result);
        return { skipped: false as const, finished: true as const };
      }
      return { skipped: false as const, finished: false as const };
    },
    onSuccess: (outcome) => {
      if (outcome.skipped) {
        toast.error(t.answerFirst);
        return;
      }
      if (outcome.finished) void navigate("/results");
      else void navigate(`/quiz/${current + 1}`);
    },
    onError: (err: unknown) =>
      toast.error(`${t.couldNotSaveAnswer}: ${errorMessage(err)}`),
  });

  // No attempt in this tab (fresh tab, cleared storage, a shared link): send
  // them to the picker rather than rendering a dead end, which is what the
  // Flet screen did with its "No question to display." fallback.
  if (!attemptId || total === 0) return <Navigate to="/quizzes" replace />;

  // Out-of-range index in the URL — clamp instead of erroring.
  if (!question) {
    const clamped = Math.min(Math.max(current, 0), total - 1);
    return <Navigate to={`/quiz/${clamped}`} replace />;
  }

  const isLast = current >= total - 1;

  return (
    <div className="space-y-4 p-5">
      <ProgressDots
        total={total}
        answered={answeredIndices}
        current={current}
      />

      <div className="h-2" />

      {/* Context shared by the whole quiz — the reading passage or listening
          clip. Deliberately shown on every question, not just the first, so it
          stays available for reference (question.py:90-93). */}
      {quiz ? <MediaBlock media={quiz.media} /> : null}

      <QuestionCard question={question} />

      <AnswerInput question={question} value={value} onChange={setValue} />

      <div className="flex gap-3">
        <Button
          variant="outline"
          className="flex-1"
          disabled={current === 0 || submit.isPending}
          onClick={() => void navigate(`/quiz/${current - 1}`)}
        >
          <ArrowLeft />
          {t.back}
        </Button>

        <Button
          className="flex-1"
          disabled={submit.isPending}
          onClick={() => submit.mutate()}
        >
          {isLast ? t.finish : t.next}
          {isLast ? <Check /> : <ArrowRight />}
        </Button>
      </div>
    </div>
  );
}
