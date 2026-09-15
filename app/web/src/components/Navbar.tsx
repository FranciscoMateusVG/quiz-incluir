import { BarChart3, LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { type UserRead } from "@/api/types";
import { t } from "@/i18n/pt-BR";
import { cn } from "@/lib/cn";

/**
 * The shared top bar: brand logo, title, and an account menu (avatar
 * initial) holding the admin link and sign-out. Ported from
 * `app/frontend/widgets/navbar.py`.
 *
 * The account menu is new — the Flet app had a `logout()` controller method
 * with no UI ever calling it, and the admin link used to be its own
 * `sm:`-only button, which meant admins on mobile had no way to reach
 * `/admin/grades` at all. Folding both into one menu behind the avatar fixes
 * that instead of just hiding it differently.
 *
 * Hand-rolled rather than a Radix primitive: a single trigger doesn't
 * justify a new dependency, so this is a plain click-outside + Escape
 * pattern.
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
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const hasMenuItems = isAdmin || onSignOut;

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4">
        <Link to="/units" className="shrink-0">
          <img
            src="/logo.jpg"
            alt=""
            className="h-[38px] rounded-[10px] object-contain"
          />
        </Link>

        <h1 className="min-w-0 flex-1 truncate font-bold">{title}</h1>

        <div ref={menuRef} className="relative shrink-0">
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={open}
            aria-label={t.accountMenu}
            onClick={() => setOpen((v) => !v)}
            disabled={!hasMenuItems}
            className={cn(
              "flex size-9 items-center justify-center rounded-full bg-primary font-bold text-primary-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              "disabled:pointer-events-none",
            )}
          >
            {initial}
          </button>

          {open && hasMenuItems && (
            <div
              role="menu"
              className="absolute right-0 z-50 mt-2 min-w-[12rem] rounded-input border border-border bg-popover p-1 text-popover-foreground shadow-md"
            >
              {isAdmin && (
                <Link
                  role="menuitem"
                  to="/admin/grades"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 rounded-sm px-3 py-2 text-sm hover:bg-muted"
                >
                  <BarChart3 className="size-4" />
                  {t.adminGradesLink}
                </Link>
              )}
              {onSignOut && (
                <button
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    onSignOut();
                  }}
                  className="flex w-full items-center gap-2 rounded-sm px-3 py-2 text-left text-sm hover:bg-muted"
                >
                  <LogOut className="size-4" />
                  {t.signOut}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
