import { describe, expect, it } from "vitest";

import { boxStats, percentile } from "@/lib/boxplot";

describe("percentile", () => {
  it("interpolates linearly, matching numpy's default", () => {
    const sorted = [1, 2, 3, 4];
    expect(percentile(sorted, 0)).toBe(1);
    expect(percentile(sorted, 50)).toBe(2.5);
    expect(percentile(sorted, 100)).toBe(4);
    expect(percentile(sorted, 25)).toBeCloseTo(1.75);
    expect(percentile(sorted, 75)).toBeCloseTo(3.25);
  });

  it("handles a single value", () => {
    expect(percentile([7], 50)).toBe(7);
  });
});

describe("boxStats", () => {
  it("returns null for an empty cohort so it can be filtered out", () => {
    expect(boxStats("B1", [])).toBeNull();
  });

  it("computes the five-number summary", () => {
    const box = boxStats("B1", [2, 4, 6, 8])!;
    expect(box.min).toBe(2);
    expect(box.q1).toBeCloseTo(3.5);
    expect(box.median).toBe(5);
    expect(box.q3).toBeCloseTo(6.5);
    expect(box.max).toBe(8);
    expect(box.outliers).toEqual([]);
  });

  it("pulls whiskers to the 1.5 IQR fences and flags outliers", () => {
    const box = boxStats("B2", [5, 5, 5, 5, 10])!;
    expect(box.outliers).toContain(10);
    expect(box.whiskerHigh).toBe(5);
  });

  it("counts the cohort", () => {
    expect(boxStats("B3", [1, 2, 3])!.count).toBe(3);
  });
});
