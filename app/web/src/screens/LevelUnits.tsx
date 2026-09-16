import { ArrowLeft, ChevronRight, Layers } from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { errorMessage } from "@/api/errors";
import { useQuizzes } from "@/api/queries";
import { type CourseLevel } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { t } from "@/i18n/pt-BR";
import { cn } from "@/lib/cn";
import { groupByUnit } from "@/lib/quizUnits";

export function LevelUnits() {
  const { level } = useParams<{ level: CourseLevel }>();
  const navigate = useNavigate();
  const { data: quizzes, isPending, error } = useQuizzes();

  const units = useMemo(
    () =>
      groupByUnit((quizzes ?? []).filter((q) => q.course_level === level))
        .groups,
    [quizzes, level],
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
        to="/levels"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        {t.backToLevels}
      </Link>

      <section className="rounded-[24px] bg-brand-gradient p-6 text-white">
        <p className="text-base text-white/70">
          {level ? t.levelLabel(level) : ""}
        </p>
        <h2 className="text-3xl font-bold">{t.chooseUnit}</h2>
        <p className="mt-1 text-sm text-white/70">{t.chooseUnitHint}</p>
      </section>

      {units.length === 0 ? (
        <EmptyState icon={Layers} title={t.noUnits} hint={t.noUnitsHint} />
      ) : (
        <div
          className={cn(
            "grid gap-5",
            units.length > 1 && "md:grid-cols-2 xl:grid-cols-3",
          )}
        >
          {units.map(({ unit, quizzes: unitQuizzes }) => (
            <button
              key={unit}
              type="button"
              onClick={() =>
                void navigate(`/levels/${level}/units/${encodeURIComponent(unit)}`)
              }
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
                    {unit}
                  </span>
                  <ChevronRight className="size-5 shrink-0 text-muted-foreground" />
                </span>

                <span className="inline-flex items-center gap-1.5 rounded-pill bg-primary-light px-2.5 py-1.5 text-xs font-medium text-primary-dark">
                  {t.quizzesCount(unitQuizzes.length)}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
