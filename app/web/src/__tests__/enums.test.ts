import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  COURSE_LEVELS,
  LANGUAGE_LEVELS,
  MEDIA_TYPES,
  QUESTION_TYPES,
  QUIZ_CATEGORIES,
  USER_ROLES,
} from "@/api/types";

/**
 * Guards the hand-written TS mirror against drift in the Python source of
 * truth. There is no OpenAPI schema to generate from (openapi_url=None), so
 * this reads the enum definitions directly.
 */
const ENUMS_PY = join(__dirname, "../../../shared/quiz_shared/enums.py");

function pythonEnumValues(source: string, className: string): string[] {
  const body = new RegExp(
    `class ${className}\\(str, Enum\\):([\\s\\S]*?)(?=\\nclass |\\s*$)`,
  ).exec(source);
  if (!body?.[1]) throw new Error(`enum ${className} not found in enums.py`);
  return [...body[1].matchAll(/=\s*"([^"]+)"/g)].map((m) => m[1]!);
}

describe("TS enums mirror quiz_shared/enums.py", () => {
  const source = readFileSync(ENUMS_PY, "utf8");

  const cases: readonly [string, readonly string[]][] = [
    ["QuestionType", QUESTION_TYPES],
    ["MediaType", MEDIA_TYPES],
    ["LanguageLevel", LANGUAGE_LEVELS],
    ["CourseLevel", COURSE_LEVELS],
    ["QuizCategory", QUIZ_CATEGORIES],
    ["UserRole", USER_ROLES],
  ];

  it.each(cases)("%s covers every Python member", (className, tsValues) => {
    expect([...tsValues].sort()).toEqual(
      pythonEnumValues(source, className).sort(),
    );
  });
});
