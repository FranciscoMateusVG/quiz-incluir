import { BarChart3, LogOut } from "lucide-react";
import { Link } from "react-router";

import { type UserRead } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n/pt-BR";

/**
 * The shared top bar: brand logo, title, an admin link for admins, and an
 * avatar initial. Ported from `app/frontend/widgets/navbar.py`.
 *
 * The sign-out button is new — the Flet app had a `logout()` controller method
 * with no UI ever calling it.
 */
export function Navbar({
  title = t.appTitle,
  user,
  onSignOut,
}: {
  title?: string;
  user?: UserRead | null;
  onSignOut?: () => void;
}) {
  const isAdmin = user?.role === "admin";
  const initial = user?.email?.[0]?.toUpperCase() ?? "?";

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4">
        <Link to="/quizzes" className="shrink-0">
          <img
            src="/logo.jpg"
            alt=""
            className="h-[38px] rounded-[10px] object-contain"
          />
        </Link>

        <h1 className="flex-1 truncate font-bold">{title}</h1>

        {isAdmin ? (
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="hidden sm:inline-flex"
          >
            <Link to="/admin/grades">
              <BarChart3 />
              {t.adminGradesLink}
            </Link>
          </Button>
        ) : null}

        {onSignOut ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={onSignOut}
            aria-label={t.signOut}
          >
            <LogOut />
          </Button>
        ) : null}

        <span
          aria-hidden
          className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary font-bold text-primary-foreground"
        >
          {initial}
        </span>
      </div>
    </header>
  );
}
