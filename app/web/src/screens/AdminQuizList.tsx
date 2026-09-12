import { BookOpen, ChevronRight } from "lucide-react";
import { Link } from "react-router";

import { errorMessage } from "@/api/errors";
import { useQuizzes } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Spinner } from "@/components/Spinner";
import { t } from "@/i18n/pt-BR";
import { titleizeCategory } from "@/lib/format";

export function AdminQuizList() {
  const { data: quizzes, isPending, error } = useQuizzes();

  if (isPending) return <Spinner label={t.loadingQuizzes} />;
  if (error)
    return (
      <ErrorState
        message={`${t.couldNotLoadQuizzes}: ${errorMessage(error)}`}
      />
    );
  if (!quizzes?.length)
    return <EmptyState icon={BookOpen} title={t.noQuizzes} />;

  return (
    <div className="space-y-4 p-5">
      <h2 className="text-2xl font-bold">{t.classGrades}</h2>
      <p className="text-muted-foreground">{t.pickQuizForGrades}</p>

      <ul className="space-y-3">
        {quizzes.map((quiz) => (
          <li key={quiz.id}>
            <Link
              to={`/admin/grades/${quiz.id}`}
              className="flex items-center gap-3 rounded-card border border-border bg-surface p-4 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-bold">{quiz.title}</span>
                <span className="block text-[13px] text-muted-foreground">
                  {titleizeCategory(quiz.category)} · {quiz.level} ·{" "}
                  {t.questionsCount(quiz.question_ids.length)}
                </span>
              </span>
              <ChevronRight className="size-5 shrink-0 text-muted-foreground" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
