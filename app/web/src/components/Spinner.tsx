import { Loader2 } from "lucide-react";

import { cn } from "@/lib/cn";

/** Centered loading state, replacing Flet's ProgressRing + caption column. */
export function Spinner({
  label,
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-1 flex-col items-center justify-center gap-4 py-16",
        className,
      )}
    >
      <Loader2 className="size-8 animate-spin text-primary" />
      {label ? <p className="text-muted-foreground">{label}</p> : null}
    </div>
  );
}
