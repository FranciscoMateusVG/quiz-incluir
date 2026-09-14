import { lazy, Suspense, useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router";

import * as api from "@/api/client";
import {
  invalidateWork,
  useSessionEpoch,
  sessionEpoch,
  setAuthNotice,
} from "@/api/session";
import { type UserRead } from "@/api/types";
import { getToken, tokenRevision } from "@/api/token";
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
  const location = useLocation();
  const navigate = useNavigate();
  const epoch = useSessionEpoch();
  const key = `${location.pathname}:${epoch}`;
  const [validation, setValidation] = useState<{
    key: string;
    user?: UserRead;
    failed?: boolean;
  }>({ key: "" });
  const [leaving, setLeaving] = useState(false);
  const reset = useAttemptStore((s) => s.reset);
  useEffect(() => {
    let current = true;
    if (getToken() && !leaving)
      void api.me().then(
        (user) => {
          if (current && sessionEpoch() === epoch) setValidation({ key, user });
        },
        () => {
          if (current && sessionEpoch() === epoch)
            setValidation({ key, failed: true });
        },
      );
    return () => {
      current = false;
    };
  }, [key, epoch, leaving]);
  if (!getToken()) return <Navigate to="/" replace />;
  if (leaving) return <Spinner label="Encerrando sessão…" />;
  if (validation.key !== key) return <Spinner label="Verificando acesso…" />;
  if (validation.failed || !validation.user)
    return (
      <div role="alert" className="p-8">
        <p>Não foi possível verificar sua sessão. Tente novamente.</p>
        <button onClick={invalidateWork}>Tentar novamente</button>
      </div>
    );
  const user = validation.user;
  if (adminOnly && user.role !== "admin")
    return <Navigate to="/quizzes" replace />;
  const signOut = async () => {
    if (leaving) return;
    const token = getToken();
    setLeaving(true);
    invalidateWork();
    const expected = tokenRevision();
    let confirmed = false;
    try {
      await api.logout();
      confirmed = true;
    } catch {
      /* disclose unconfirmed revocation */
    }
    if (tokenRevision() !== expected || getToken() !== token) return;
    setAuthNotice(
      confirmed
        ? ""
        : "Você saiu do Quiz, mas não foi possível confirmar o encerramento da sessão no servidor.",
    );
    clearToken();
    reset();
    void navigate("/", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar title={title} user={user} onSignOut={() => void signOut()} />
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
