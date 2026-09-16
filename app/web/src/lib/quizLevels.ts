import { COURSE_LEVELS, type CourseLevel, type QuizRead } from "@/api/types";

export interface QuizLevelGroup {
  course_level: CourseLevel;
  quizzes: QuizRead[];
}

/**
 * Splits quizzes into per-course-level groups, one per distinct
 * `course_level` present, ordered by the canonical `COURSE_LEVELS` order
 * (B1-B4) rather than input order — unlike free-text `unit`, this is a small
 * fixed enum every quiz has a value for, so there is no "ungrouped" bucket.
 */
export function groupByCourseLevel(
  quizzes: readonly QuizRead[],
): QuizLevelGroup[] {
  const groupByKey = new Map<CourseLevel, QuizLevelGroup>();

  for (const quiz of quizzes) {
    let group = groupByKey.get(quiz.course_level);
    if (!group) {
      group = { course_level: quiz.course_level, quizzes: [] };
      groupByKey.set(quiz.course_level, group);
    }
    group.quizzes.push(quiz);
  }

  return COURSE_LEVELS.map((level) => groupByKey.get(level)).filter(
    (group): group is QuizLevelGroup => group !== undefined,
  );
}
