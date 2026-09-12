import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgressDots } from "@/components/ProgressDots";

describe("ProgressDots", () => {
  it("renders one dot per question, numbered from 1", () => {
    render(<ProgressDots total={3} answered={new Set()} current={0} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("marks the current step for assistive tech", () => {
    render(<ProgressDots total={3} answered={new Set()} current={1} />);
    expect(screen.getByText("2")).toHaveAttribute("aria-current", "step");
  });

  it("treats an answered question as done even when it is ahead of the cursor", () => {
    render(<ProgressDots total={3} answered={new Set([2])} current={0} />);
    // done => success fill, per progress_indicator.py's `i < current or i in answers`
    expect(screen.getByText("3").className).toContain("bg-success");
  });

  it("leaves pending questions outlined", () => {
    render(<ProgressDots total={2} answered={new Set()} current={0} />);
    expect(screen.getByText("2").className).toContain("border-border");
  });
});
