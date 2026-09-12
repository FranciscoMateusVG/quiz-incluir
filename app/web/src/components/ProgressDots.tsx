import { cn } from "@/lib/cn";

/**
 * One numbered dot per question: green when answered, orange for the current
 * one, outlined while pending. Ported from
 * `app/frontend/widgets/progress_indicator.py`, including its `done` rule —
 * a question counts as done if it has an answer *or* sits before the cursor.
 *
 * Wraps on narrow screens, as the Flet Row did with wrap=True.
 */
export function ProgressDots({
  total,
  answered,
  current,
}: {
  total: number;
  answered: ReadonlySet<number>;
  current: number;
}) {
  return (
    <ol className="flex flex-wrap items-center justify-center gap-2">
      {Array.from({ length: total }, (_, i) => {
        const isCurrent = i === current;
        const done = i < current || answered.has(i);

        return (
          <li
            key={i}
            aria-current={isCurrent ? "step" : undefined}
            className={cn(
              "flex size-[30px] items-center justify-center rounded-step text-sm font-bold",
              isCurrent && "bg-primary text-primary-foreground",
              done && !isCurrent && "bg-success text-white",
              !done &&
                !isCurrent &&
                "border border-border bg-surface text-muted-foreground",
            )}
          >
            {i + 1}
          </li>
        );
      })}
    </ol>
  );
}
