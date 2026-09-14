import { useEffect } from "react";
import { invalidateWork, subscribeSession } from "@/api/session";
import { getToken } from "@/api/token";
import { useAttemptStore } from "@/store/useAttemptStore";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router";
import { Toaster } from "sonner";

import { AppRoutes } from "@/routes";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export function App() {
  useEffect(() => {
    let token = getToken();
    const unsubscribe = subscribeSession(() => {
      queryClient.clear();
      if (getToken() !== token) {
        useAttemptStore.getState().reset();
        token = getToken();
      }
    });
    const invalidate = () => invalidateWork();
    const events = ["offline", "online", "pagehide", "pageshow", "focus"];
    for (const name of events) window.addEventListener(name, invalidate);
    document.addEventListener("visibilitychange", invalidate);
    return () => {
      unsubscribe();
      for (const name of events) window.removeEventListener(name, invalidate);
      document.removeEventListener("visibilitychange", invalidate);
    };
  }, []);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
      {/* Replaces widgets/feedback.py::notify — same role, richer defaults. */}
      <Toaster position="top-center" richColors />
    </QueryClientProvider>
  );
}
