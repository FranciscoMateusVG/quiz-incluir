import { type LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  hint,
  iconClassName = "size-16",
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  iconClassName?: string;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 py-16">
      <Icon className={`${iconClassName} text-muted-foreground`} />
      <p className="text-center text-xl font-bold">{title}</p>
      {hint ? (
        <p className="text-center text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
