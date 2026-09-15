import { ChevronRight, HelpCircle } from "lucide-react";

import { type LanguageLevel, type QuizRead } from "@/api/types";
import { t } from "@/i18n/pt-BR";
import { cn } from "@/lib/cn";

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

export function QuizCard({
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
        // min-w-0: this button is a direct grid item in the picker's grid.
        // Without it, its nowrap (truncate) title sets the item's intrinsic
        // min-width, which blows out the grid track — and the page — wider
        // than the viewport on mobile for any long-titled quiz.
        "flex w-full min-w-0 items-center gap-4 rounded-card border border-border bg-surface p-5 text-left transition-colors",
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
