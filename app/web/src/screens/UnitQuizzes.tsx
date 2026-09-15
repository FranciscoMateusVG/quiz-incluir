import { ArrowLeft, BookOpen } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams } from "react-router";

import { errorMessage } from "@/api/errors";
import { useQuizzes } from "@/api/queries";
import { type QuizCategory } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { QuizCard } from "@/components/QuizCard";
import { Spinner } from "@/components/Spinner";
import { useStartQuiz } from "@/hooks/useStartQuiz";
import { t } from "@/i18n/pt-BR";
import { cn } from "@/lib/cn";

/** Fixed section order, from `screens/picker.py`. */
const SECTIONS: readonly { key: QuizCategory; title: string }[] = [
  { key: "reading", title: t.sectionReading },
  { key: "listening", title: t.sectionListening },
  { key: "vocabulary_grammar", title: t.sectionVocabulary },
];

export function UnitQuizzes() {
  const { unit: encodedUnit } = useParams<{ unit: string }>();
  const unit = encodedUnit ? decodeURIComponent(encodedUnit) : "";
  const { data: quizzes, isPending, error } = useQuizzes();
  const start = useStartQuiz();

  const items = useMemo(
    () => (quizzes ?? []).filter((q) => q.unit === unit),
    [quizzes, unit],
  );

  if (isPending) return <Spinner label={t.loadingQuizzes} />;
  if (error)
    return (
      <ErrorState
        message={`${t.couldNotLoadQuizzes}: ${errorMessage(error)}`}
      />
    );

  return (
    <div className="space-y-5 p-5">
      <Link
        to="/units"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        {t.backToUnits}
      </Link>

      <section className="rounded-[24px] bg-brand-gradient p-6 text-white">
        <p className="text-base text-white/70">{t.unitLabel(unit)}</p>
        <h2 className="text-3xl font-bold">{t.chooseQuiz}</h2>
      </section>

      {items.length === 0 ? (
        <EmptyState icon={BookOpen} title={t.noQuizzes} hint={t.noQuizzesHint} />
      ) : (
        <div className="space-y-5">
          {SECTIONS.map(({ key, title }) => {
            const sectionItems = items.filter((q) => q.category === key);
            if (sectionItems.length === 0) return null;

            return (
              <section key={key} className="space-y-4">
                <h3 className="text-xl font-bold">{title}</h3>
                <div
                  className={cn(
                    "grid gap-5",
                    sectionItems.length > 1 && "md:grid-cols-2 xl:grid-cols-3",
                  )}
                >
                  {sectionItems.map((quiz) => (
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
