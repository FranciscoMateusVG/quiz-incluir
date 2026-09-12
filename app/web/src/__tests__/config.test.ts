import { describe, expect, it } from "vitest";

import { fromResponse, parseOptions, toResponse } from "@/api/config";

describe("toResponse", () => {
  it("sends the option text for multiple choice, not an index", () => {
    // The backend grader compares option strings (lowercased/stripped), so an
    // index would silently score zero.
    expect(toResponse("multiple_choice", "Paris")).toEqual({
      selected: "Paris",
    });
  });

  it("sends a string array for multiple selection", () => {
    expect(toResponse("multiple_selection", ["a", "b"])).toEqual({
      selected: ["a", "b"],
    });
  });

  it("sends a real boolean for true/false", () => {
    // Strict == against config.answer on the backend: "true" would score zero.
    expect(toResponse("true_false", true)).toEqual({ selected: true });
    expect(toResponse("true_false", false)).toEqual({ selected: false });
  });

  it("keeps false as an answer rather than treating it as unanswered", () => {
    expect(toResponse("true_false", false)).not.toBeNull();
  });

  it("trims short text and uses the text key", () => {
    expect(toResponse("short_text", "  is  ")).toEqual({ text: "is" });
  });

  it("returns null for unanswered inputs", () => {
    expect(toResponse("multiple_choice", null)).toBeNull();
    expect(toResponse("multiple_choice", "")).toBeNull();
    expect(toResponse("multiple_selection", [])).toBeNull();
    expect(toResponse("true_false", null)).toBeNull();
    expect(toResponse("short_text", "   ")).toBeNull();
  });
});

describe("fromResponse", () => {
  it("round-trips every question type", () => {
    expect(fromResponse("multiple_choice", { selected: "Paris" })).toBe(
      "Paris",
    );
    expect(fromResponse("multiple_selection", { selected: ["a"] })).toEqual([
      "a",
    ]);
    expect(fromResponse("true_false", { selected: false })).toBe(false);
    expect(fromResponse("short_text", { text: "is" })).toBe("is");
  });

  it("returns null when there is no previous answer", () => {
    expect(fromResponse("multiple_choice", undefined)).toBeNull();
  });

  it("ignores a payload of the wrong shape", () => {
    expect(fromResponse("multiple_choice", { text: "oops" })).toBeNull();
    expect(fromResponse("true_false", { selected: "true" })).toBeNull();
  });
});

describe("parseOptions", () => {
  it("reads the option list", () => {
    expect(parseOptions({ options: ["a", "b"] })).toEqual(["a", "b"]);
  });

  it("degrades to null on malformed config instead of throwing", () => {
    // Mirrors the backend's parse_config returning None on bad data.
    expect(parseOptions({})).toBeNull();
    expect(parseOptions({ options: "nope" })).toBeNull();
  });
});
