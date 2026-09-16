import { describe, expect, it } from "vitest";

import { type CourseLevel, type QuizRead } from "@/api/types";
import { groupByCourseLevel } from "@/lib/quizLevels";

function quiz(id: string, course_level: CourseLevel): QuizRead {
  return {
    id,
    title: id,
    description: null,
    category: "reading",
    level: "A1",
    course_level,
    unit: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    question_ids: [],
    media: [],
  };
}

describe("groupByCourseLevel", () => {
  it("returns no groups for an empty input", () => {
    expect(groupByCourseLevel([])).toEqual([]);
  });

  it("gives every distinct course level its own group, including one with a single quiz", () => {
    const a = quiz("a", "B1");
    const b = quiz("b", "B2");
    expect(groupByCourseLevel([a, b])).toEqual([
      { course_level: "B1", quizzes: [a] },
      { course_level: "B2", quizzes: [b] },
    ]);
  });

  it("collects quizzes sharing a course level into the same group, in order", () => {
    const a = quiz("a", "B1");
    const b = quiz("b", "B1");
    const c = quiz("c", "B1");
    expect(groupByCourseLevel([a, b, c])).toEqual([
      { course_level: "B1", quizzes: [a, b, c] },
    ]);
  });

  it("orders groups by canonical course level order, not input order", () => {
    const a = quiz("a", "B4");
    const b = quiz("b", "B1");
    const c = quiz("c", "B3");
    expect(groupByCourseLevel([a, b, c])).toEqual([
      { course_level: "B1", quizzes: [b] },
      { course_level: "B3", quizzes: [c] },
      { course_level: "B4", quizzes: [a] },
    ]);
  });
});
