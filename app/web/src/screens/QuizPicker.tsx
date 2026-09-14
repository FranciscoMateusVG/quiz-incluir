import { useWorkGuard } from "@/api/session";
import { useMutation } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronRight,
  HelpCircle,
  Search,
  SearchX,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import * as api from "@/api/client";
import { errorMessage } from "@/api/errors";
import { useQuizzes } from "@/api/queries";
import {
  type LanguageLevel,
  type QuizCategory,
  type QuizRead,
} from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n/pt-BR";
import { cn } from "@/lib/cn";
import { useAttemptStore } from "@/store/useAttemptStore";

/** Fixed section order, from `screens/picker.py`. */
const SECTIONS: readonly { key: QuizCategory; title: string }[] = [
  { key: "reading", title: t.sectionReading },
  { key: "listening", title: t.sectionListening },
  { key: "vocabulary_grammar", title: t.sectionVocabulary },
];

/** Level badge colours, from `_LEVEL_COLORS` in picker.py. */
const LEVEL_COLORS: Record<LanguageLevel, string> = {
  A1: "bg-[#E8F5E9] text-[#2E7D32]",
  A2: "bg-[#E8F5E9] text-[#2E7D32]",
  B1: "bg-[#E8F0FE] text-[#1A73E8]",
  B2: "bg-[#E8F0FE] text-[#1A73E8]",
  C1: "bg-[#F3E8FF] text-[#7C3AED]",
  C2: "bg-[#F3E8FF] text-[#7C3AED]",
};
const LEVEL_DEFAULT = "bg-[#EEF2FF] text-[#6C63FF]";

function levelColors(level: string | null): string {
  return (
    LEVEL_COLORS[(level ?? "").toUpperCase() as LanguageLevel] ?? LEVEL_DEFAULT
  );
}

export function QuizPicker() {
  const navigate = useNavigate();
  const capture = useWorkGuard();
  const [query, setQuery] = useState("");
  const { data: quizzes, isPending, error } = useQuizzes();
  const startAttempt = useAttemptStore((s) => s.start);

  const start = useMutation({
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

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return quizzes ?? [];
    return (quizzes ?? []).filter((q) =>
      `${q.title} ${q.description ?? ""}`.toLowerCase().includes(term),
    );
  }, [quizzes, query]);

  if (isPending) return <Spinner label={t.loadingQuizzes} />;
  if (error)
    return (
      <ErrorState
        message={`${t.couldNotLoadQuizzes}: ${errorMessage(error)}`}
      />
    );
  if (!quizzes?.length) {
    return (
      <EmptyState icon={BookOpen} title={t.noQuizzes} hint={t.noQuizzesHint} />
    );
  }

  return (
    <div className="space-y-5 p-5">
      <section className="rounded-[24px] bg-brand-gradient p-6 text-white">
        <p className="text-base text-white/70">{t.welcomeBack}</p>
        <h2 className="text-3xl font-bold">{t.chooseQuiz}</h2>
        <p className="mt-1 text-sm text-white/70">{t.keepBuilding}</p>
      </section>

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t.searchQuizzes}
          aria-label={t.searchQuizzes}
          className="pl-9"
        />
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={SearchX}
          title={t.noQuizzesMatch}
          hint={t.noQuizzesMatchHint}
          iconClassName="size-12"
        />
      ) : (
        <div className="space-y-5">
          {SECTIONS.map(({ key, title }) => {
            const items = filtered.filter((q) => q.category === key);
            if (items.length === 0) return null;

            return (
              <section key={key} className="space-y-4">
                <h3 className="text-xl font-bold">{title}</h3>
                <div
                  className={cn(
                    "grid gap-5",
                    items.length > 1 && "md:grid-cols-2 xl:grid-cols-3",
                  )}
                >
                  {items.map((quiz) => (
                    <QuizCard
                      key={quiz.id}
                      quiz={quiz}
                      disabled={start.isPending}
                      onSelect={() => start.mutate(quiz)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function QuizCard({
  quiz,
  onSelect,
  disabled,
}: {
  quiz: QuizRead;
  onSelect: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      className={cn(
        "flex w-full items-center gap-4 rounded-card border border-border bg-surface p-5 text-left transition-colors",
        "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "disabled:pointer-events-none disabled:opacity-60",
      )}
    >
      <span
        className={cn(
          "flex size-[60px] shrink-0 items-center justify-center rounded-full text-lg font-bold",
          levelColors(quiz.level),
        )}
      >
        {(quiz.level ?? "–").toUpperCase()}
      </span>

      <span className="min-w-0 flex-1 space-y-1.5">
        <span className="flex items-center gap-2">
          <span className="flex-1 truncate text-xl font-bold">
            {quiz.title}
          </span>
          <ChevronRight className="size-5 shrink-0 text-muted-foreground" />
        </span>

        <span className="line-clamp-2 block h-10 text-sm text-muted-700">
          {quiz.description ?? t.defaultQuizDescription}
        </span>

        <span className="inline-flex items-center gap-1.5 rounded-pill bg-primary-light px-2.5 py-1.5 text-xs font-medium text-primary-dark">
          <HelpCircle className="size-3.5" />
          {t.questionsCount(quiz.question_ids.length)}
        </span>
      </span>
    </button>
  );
}
