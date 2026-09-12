import { useMemo, useState } from "react";
import { useParams } from "react-router";

import {
  GRADES_POLL_MS,
  useAdminAttempts,
  useAdminQuestionStats,
} from "@/api/queries";
import { errorMessage, isForbidden } from "@/api/errors";
import { COURSE_LEVELS, type CourseLevel } from "@/api/types";
import { ErrorState } from "@/components/ErrorState";
import { GradeDistribution } from "@/components/GradeDistribution";
import { Spinner } from "@/components/Spinner";
import { Card, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { t } from "@/i18n/pt-BR";
import { boxStats } from "@/lib/boxplot";

/** Sentinel for "no filter"; Radix Select cannot hold an empty string value. */
const ALL = "all";

export function AdminGrades() {
  const { quizId = "" } = useParams();
  const [level, setLevel] = useState<CourseLevel | "">("");

  const attempts = useAdminAttempts(quizId, level);
  const stats = useAdminQuestionStats(quizId, level);

  const distribution = useMemo(() => {
    const rows = attempts.data ?? [];
    // Only finished, graded attempts have a score to plot.
    const scored = rows.filter((r) => r.finished && r.score !== null);

    return COURSE_LEVELS.map((lvl) =>
      boxStats(
        lvl,
        scored.filter((r) => r.level === lvl).map((r) => r.score!),
      ),
    ).filter((box): box is NonNullable<typeof box> => box !== null);
  }, [attempts.data]);

  const error = attempts.error ?? stats.error;

  if (isForbidden(error))
    return <ErrorState locked message={t.noAdminAccess} />;

  const header = (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">{t.grades}</h2>
        <div className="w-[220px]">
          <Select
            value={level || ALL}
            onValueChange={(next) =>
              setLevel(next === ALL ? "" : (next as CourseLevel))
            }
          >
            <SelectTrigger aria-label={t.classLevel}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t.allLevels}</SelectItem>
              {COURSE_LEVELS.map((lvl) => (
                <SelectItem key={lvl} value={lvl}>
                  {lvl}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {t.autoUpdates(GRADES_POLL_MS / 1000)}
      </p>
    </div>
  );

  // Only a first load blocks; poll refetches keep the current view on screen.
  if (attempts.isPending || stats.isPending) {
    return (
      <div className="space-y-5 p-5">
        {header}
        <Spinner label={t.loadingGrades} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-5 p-5">
        {header}
        <ErrorState
          message={`${t.couldNotLoadGrades}: ${errorMessage(error)}`}
        />
      </div>
    );
  }

  return (
    <div className="space-y-5 p-5">
      {header}

      <Card className="space-y-3">
        <CardTitle>{t.gradeDistribution}</CardTitle>
        {distribution.length > 0 ? (
          <GradeDistribution stats={distribution} />
        ) : (
          <p className="text-muted-foreground">{t.noFinishedAttempts}</p>
        )}
      </Card>

      <Card className="space-y-3">
        <CardTitle>{t.perQuestionBreakdown}</CardTitle>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t.colQuestion}</TableHead>
              <TableHead className="text-right">{t.colCorrect}</TableHead>
              <TableHead className="text-right">{t.colWrong}</TableHead>
              <TableHead className="text-right">{t.colUnanswered}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(stats.data ?? []).map((row) => (
              <TableRow key={row.question_id}>
                <TableCell
                  className="max-w-[28rem] truncate"
                  title={row.prompt}
                >
                  {row.prompt}
                </TableCell>
                <TableCell className="text-right">
                  {row.correct_count}
                </TableCell>
                <TableCell className="text-right">
                  {row.incorrect_count}
                </TableCell>
                <TableCell className="text-right">
                  {row.unanswered_count}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
