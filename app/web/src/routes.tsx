import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";

import * as api from "@/api/client";
import { useCurrentUser } from "@/api/queries";
import { getToken } from "@/api/token";
import { Navbar } from "@/components/Navbar";
import { Spinner } from "@/components/Spinner";
import { LoginScreen } from "@/screens/LoginScreen";

// The admin dashboard pulls in chart.js, which students never need. Splitting
// it out keeps that weight off the student bundle.
const AdminQuizList = lazy(async () => ({
  default: (await import("@/screens/AdminQuizList")).AdminQuizList,
}));
const AdminGrades = lazy(async () => ({
  default: (await import("@/screens/AdminGrades")).AdminGrades,
}));
import { NotFound } from "@/screens/NotFound";
import { Question } from "@/screens/Question";
import { QuizPicker } from "@/screens/QuizPicker";
import { Results } from "@/screens/Results";
import { t } from "@/i18n/pt-BR";
import { clearToken } from "@/api/token";
import { useAttemptStore } from "@/store/useAttemptStore";

/**
 * Route guard, mirroring `app/frontend/widgets/auth_guard.py`: redirect away
 * rather than render. Authentication itself is deferred, so this currently
 * checks only that a token exists plus the role from GET /users/me.
 */
function RequireAuth({
  children,
  adminOnly = false,
  title,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
  title?: string;
}) {
  const hasToken = Boolean(getToken());
  const { data: user, isPending, error } = useCurrentUser(hasToken);
  const reset = useAttemptStore((s) => s.reset);

  if (!hasToken) return <Navigate to="/" replace />;
  if (isPending) return <Spinner />;
  // A rejected token is indistinguishable from no token for routing purposes.
  if (error || !user) return <Navigate to="/" replace />;
  if (adminOnly && user.role !== "admin")
    return <Navigate to="/quizzes" replace />;

  const signOut = () => {
    // Best-effort: revoke the session server-side, but don't let a slow or
    // failed request delay clearing local state and navigating away — the
    // token the SPA holds IS the real monorepo session, so this is what
    // actually invalidates it rather than just discarding the local copy.
    void api.logout();
    clearToken();
    reset();
    window.location.assign("/");
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar title={title} user={user} onSignOut={signOut} />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
        <Suspense fallback={<Spinner />}>{children}</Suspense>
      </main>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LoginScreen />} />

      <Route
        path="/quizzes"
        element={
          <RequireAuth>
            <QuizPicker />
          </RequireAuth>
        }
      />
      <Route
        path="/quiz/:index"
        element={
          <RequireAuth>
            <Question />
          </RequireAuth>
        }
      />
      <Route
        path="/results"
        element={
          <RequireAuth title={t.results}>
            <Results />
          </RequireAuth>
        }
      />

      {/* These own /admin/* in the SPA; SQLAdmin moved to /backoffice so a
          hard refresh on these paths reaches the SPA instead of its router. */}
      <Route
        path="/admin/grades"
        element={
          <RequireAuth adminOnly title={t.classGrades}>
            <AdminQuizList />
          </RequireAuth>
        }
      />
      <Route
        path="/admin/grades/:quizId"
        element={
          <RequireAuth adminOnly title={t.classGrades}>
            <AdminGrades />
          </RequireAuth>
        }
      />

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
