import { describe, expect, it } from "vitest";

import { type QuizRead } from "@/api/types";
import { groupByUnit } from "@/lib/quizUnits";

function quiz(id: string, unit: string | null): QuizRead {
  return {
    id,
    title: id,
    description: null,
    category: "reading",
    level: "A1",
    course_level: "B1",
    unit,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    question_ids: [],
    media: [],
  };
}

describe("groupByUnit", () => {
  it("puts every quiz in ungrouped when none has a unit", () => {
    const quizzes = [quiz("a", null), quiz("b", null)];
    const { groups, ungrouped } = groupByUnit(quizzes);
    expect(groups).toEqual([]);
    expect(ungrouped).toEqual(quizzes);
  });

  it("gives every distinct unit its own group, including a unit with one quiz", () => {
    const a = quiz("a", "Unit 1");
    const b = quiz("b", "Unit 2");
    const { groups, ungrouped } = groupByUnit([a, b]);
    expect(groups).toEqual([
      { unit: "Unit 1", quizzes: [a] },
      { unit: "Unit 2", quizzes: [b] },
    ]);
    expect(ungrouped).toEqual([]);
  });

  it("collects quizzes sharing a unit into the same group, in order", () => {
    const a = quiz("a", "Unit 1");
    const b = quiz("b", "Unit 1");
    const c = quiz("c", "Unit 1");
    const { groups, ungrouped } = groupByUnit([a, b, c]);
    expect(groups).toEqual([{ unit: "Unit 1", quizzes: [a, b, c] }]);
    expect(ungrouped).toEqual([]);
  });

  it("mixes shared units, single-quiz units and no-unit quizzes, preserving order", () => {
    const a = quiz("a", "Unit 1");
    const b = quiz("b", null);
    const c = quiz("c", "Unit 1");
    const d = quiz("d", "Unit 2");
    const e = quiz("e", null);
    const { groups, ungrouped } = groupByUnit([a, b, c, d, e]);
    expect(groups).toEqual([
      { unit: "Unit 1", quizzes: [a, c] },
      { unit: "Unit 2", quizzes: [d] },
    ]);
    expect(ungrouped).toEqual([b, e]);
  });
});
