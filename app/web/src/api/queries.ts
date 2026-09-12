/**
 * TanStack Query hooks, one per endpoint. Handles loading/error state and,
 * for the admin grades screen, polling — plain `refetchInterval` rather than
 * a hand-rolled interval loop.
 */

import { useQuery } from "@tanstack/react-query";

import * as api from "./client";
import { QuizApiError } from "./errors";
import { type CourseLevel } from "./types";

/** Admin screens render a dedicated locked state for 403, so never retry it. */
function retryUnlessClientError(failureCount: number, error: unknown): boolean {
  if (
    error instanceof QuizApiError &&
    error.status >= 400 &&
    error.status < 500
  ) {
    return false;
  }
  return failureCount < 2;
}

export const queryKeys = {
  quizzes: ["quizzes"] as const,
  me: ["me"] as const,
  adminAttempts: (quizId: string, level: CourseLevel | "") =>
    ["admin", "attempts", quizId, level] as const,
  adminStats: (quizId: string, level: CourseLevel | "") =>
    ["admin", "question-stats", quizId, level] as const,
};

export function useQuizzes() {
  return useQuery({
    queryKey: queryKeys.quizzes,
    queryFn: api.listQuizzes,
    retry: retryUnlessClientError,
  });
}

export function useCurrentUser(enabled = true) {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: api.me,
    enabled,
    retry: retryUnlessClientError,
    staleTime: 5 * 60 * 1000,
  });
}

/** How often the admin grades screen refetches while a quiz is in progress. */
export const GRADES_POLL_MS = 10_000;

export function useAdminAttempts(quizId: string, level: CourseLevel | "") {
  return useQuery({
    queryKey: queryKeys.adminAttempts(quizId, level),
    queryFn: () => api.adminListAttempts(quizId, level),
    refetchInterval: GRADES_POLL_MS,
    retry: retryUnlessClientError,
  });
}

export function useAdminQuestionStats(quizId: string, level: CourseLevel | "") {
  return useQuery({
    queryKey: queryKeys.adminStats(quizId, level),
    queryFn: () => api.adminQuestionStats(quizId, level),
    refetchInterval: GRADES_POLL_MS,
    retry: retryUnlessClientError,
  });
}
