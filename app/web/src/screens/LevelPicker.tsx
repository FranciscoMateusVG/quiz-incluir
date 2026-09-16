import { ChevronRight, Layers } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router";

import { errorMessage } from "@/api/errors";
import { useQuizzes } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { t } from "@/i18n/pt-BR";
import { cn } from "@/lib/cn";
import { groupByCourseLevel } from "@/lib/quizLevels";

export function LevelPicker() {
  const navigate = useNavigate();
  const { data: quizzes, isPending, error } = useQuizzes();

  const levels = useMemo(
    () => groupByCourseLevel(quizzes ?? []),
    [quizzes],
  );

  if (isPending) return <Spinner label={t.loadingQuizzes} />;
  if (error)
    return (
      <ErrorState
        message={`${t.couldNotLoadQuizzes}: ${errorMessage(error)}`}
      />
    );
  if (levels.length === 0) {
    return (
      <EmptyState icon={Layers} title={t.noLevels} hint={t.noLevelsHint} />
    );
  }

  return (
    <div className="space-y-5 p-5">
      <section className="rounded-[24px] bg-brand-gradient p-6 text-white">
        <p className="text-base text-white/70">{t.welcomeBack}</p>
        <h2 className="text-3xl font-bold">{t.chooseLevel}</h2>
        <p className="mt-1 text-sm text-white/70">{t.chooseLevelHint}</p>
      </section>

      <div
        className={cn(
          "grid gap-5",
          levels.length > 1 && "md:grid-cols-2 xl:grid-cols-3",
        )}
      >
        {levels.map(({ course_level, quizzes: levelQuizzes }) => (
          <button
            key={course_level}
            type="button"
            onClick={() => void navigate(`/levels/${course_level}`)}
            className={cn(
              "flex w-full min-w-0 items-center gap-4 rounded-card border border-border bg-surface p-5 text-left transition-colors",
              "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            )}
          >
            <span className="flex size-[60px] shrink-0 items-center justify-center rounded-full bg-primary-light text-primary-dark">
              <Layers className="size-6" />
            </span>

            <span className="min-w-0 flex-1 space-y-1.5">
              <span className="flex items-center gap-2">
                <span className="flex-1 truncate text-xl font-bold">
                  {t.levelLabel(course_level)}
                </span>
                <ChevronRight className="size-5 shrink-0 text-muted-foreground" />
              </span>

              <span className="inline-flex items-center gap-1.5 rounded-pill bg-primary-light px-2.5 py-1.5 text-xs font-medium text-primary-dark">
                {t.quizzesCount(levelQuizzes.length)}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
