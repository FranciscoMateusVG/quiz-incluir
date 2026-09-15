import { type QuizRead } from "@/api/types";

export interface QuizUnitGroup {
  unit: string;
  quizzes: QuizRead[];
}

/**
 * Splits quizzes into per-unit groups (every distinct non-null `unit`, even
 * ones with a single quiz) plus a leftover list for quizzes with no unit at
 * all. Both preserve the input's relative order.
 */
export function groupByUnit(quizzes: readonly QuizRead[]): {
  groups: QuizUnitGroup[];
  ungrouped: QuizRead[];
} {
  const groups: QuizUnitGroup[] = [];
  const groupByKey = new Map<string, QuizUnitGroup>();
  const ungrouped: QuizRead[] = [];

  for (const quiz of quizzes) {
    if (!quiz.unit) {
      ungrouped.push(quiz);
      continue;
    }
    let group = groupByKey.get(quiz.unit);
    if (!group) {
      group = { unit: quiz.unit, quizzes: [] };
      groupByKey.set(quiz.unit, group);
      groups.push(group);
    }
    group.quizzes.push(quiz);
  }

  return { groups, ungrouped };
}
