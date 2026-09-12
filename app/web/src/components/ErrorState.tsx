import { AlertCircle, Lock } from "lucide-react";

/** Matches the Flet error state: a large icon over centered error-coloured text. */
export function ErrorState({
  message,
  locked = false,
}: {
  message: string;
  locked?: boolean;
}) {
  const Icon = locked ? Lock : AlertCircle;
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 py-16">
      <Icon className="size-12 text-destructive" />
      <p className="max-w-md text-center text-destructive">{message}</p>
    </div>
  );
}
