import { useWorkGuard } from "@/api/session";
import { useMutation } from "@tanstack/react-query";
import { FileText, Meh, Trophy } from "lucide-react";
import { Navigate, useNavigate } from "react-router";
import { toast } from "sonner";

import * as api from "@/api/client";
import { errorMessage } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/i18n/pt-BR";
import { formatScore, percentage } from "@/lib/format";
import { useAttemptStore } from "@/store/useAttemptStore";

const PASS_THRESHOLD = 50;

export function Results() {
  const navigate = useNavigate();
  const capture = useWorkGuard();
  const result = useAttemptStore((s) => s.result);
  const attemptId = useAttemptStore((s) => s.attemptId);
  const reset = useAttemptStore((s) => s.reset);

  const download = useMutation({
    mutationFn: async () => {
      const current = capture();
      if (!attemptId) throw new Error("no attempt");
      const blob = await api.downloadReportPdf(attemptId);
      current();

      // Replaces the Flet FilePicker service (services/files.py) with the
      // browser's own save path.
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `quiz-report-${attemptId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
    onError: (err: unknown) =>
      toast.error(`${t.couldNotDownloadReport}: ${errorMessage(err)}`),
  });

  if (!result) return <Navigate to="/quizzes" replace />;

  const score = result.score ?? 0;
  const maxScore = result.max_score ?? 0;
  const pct = percentage(score, maxScore);
  const passed = pct >= PASS_THRESHOLD;

  return (
    <div className="flex justify-center p-6">
      <Card className="w-full max-w-md space-y-2 p-8 text-center">
        {passed ? (
          <Trophy className="mx-auto size-16 text-primary" />
        ) : (
          <Meh className="mx-auto size-16 text-muted-foreground" />
        )}

        <h2 className="text-2xl font-bold">{t.quizCompleted}</h2>

        <p className="pt-2 text-[44px] font-bold leading-tight text-primary">
          {formatScore(score)} / {formatScore(maxScore)}
        </p>
        <p className="text-muted-700">{t.percentCorrect(pct)}</p>

        <div className="flex gap-3 pt-6">
          <Button
            className="flex-1"
            onClick={() => {
              reset();
              void navigate("/quizzes");
            }}
          >
            {t.takeAnotherQuiz}
          </Button>
          <Button
            variant="outline"
            className="flex-1"
            disabled={download.isPending}
            onClick={() => download.mutate()}
          >
            <FileText />
            {t.downloadPdf}
          </Button>
        </div>
      </Card>
    </div>
  );
}
