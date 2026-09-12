import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { toResponse, type AnswerValue } from "@/api/config";
import { type QuestionRead, type QuestionType } from "@/api/types";
import { AnswerInput } from "@/components/answers/AnswerInput";

function question(
  type: QuestionType,
  config: Record<string, unknown> = {},
): QuestionRead {
  return {
    id: "q1",
    type,
    prompt: "Prompt?",
    suggested_score: 1,
    config,
    created_at: "2026-01-01T00:00:00+00:00",
    media: [],
  };
}

const OPTIONS = { options: ["Paris", "London", "Rome"] };

describe("AnswerInput", () => {
  it("renders multiple choice options and submits the option text", async () => {
    const onChange = vi.fn();
    render(
      <AnswerInput
        question={question("multiple_choice", OPTIONS)}
        value={null}
        onChange={onChange}
      />,
    );

    expect(screen.getByText("Paris")).toBeInTheDocument();
    expect(screen.getByText("Rome")).toBeInTheDocument();

    await userEvent.click(screen.getByText("London"));

    expect(onChange).toHaveBeenCalledWith("London");
    expect(toResponse("multiple_choice", "London")).toEqual({
      selected: "London",
    });
  });

  it("clicking the label text selects the option (Flet could not do this)", async () => {
    const onChange = vi.fn();
    render(
      <AnswerInput
        question={question("multiple_choice", OPTIONS)}
        value={null}
        onChange={onChange}
      />,
    );
    // The whole row is a <label>, so the text is a valid tap target.
    await userEvent.click(screen.getByText("Rome"));
    expect(onChange).toHaveBeenCalledWith("Rome");
  });

  it("keeps multiple-selection payloads in option order, not click order", async () => {
    let value: AnswerValue = [];
    const onChange = vi.fn((next: AnswerValue) => {
      value = next;
    });

    const { rerender } = render(
      <AnswerInput
        question={question("multiple_selection", OPTIONS)}
        value={value}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByText("Rome"));
    rerender(
      <AnswerInput
        question={question("multiple_selection", OPTIONS)}
        value={value}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByText("Paris"));

    expect(value).toEqual(["Paris", "Rome"]);
  });

  it("renders true/false in Portuguese but submits a real boolean", async () => {
    const onChange = vi.fn();
    render(
      <AnswerInput
        question={question("true_false")}
        value={null}
        onChange={onChange}
      />,
    );

    expect(screen.getByText("Verdadeiro")).toBeInTheDocument();
    expect(screen.getByText("Falso")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Falso"));

    expect(onChange).toHaveBeenCalledWith(false);
    expect(toResponse("true_false", false)).toEqual({ selected: false });
  });

  it("renders a text field for short text", async () => {
    const onChange = vi.fn();
    render(
      <AnswerInput
        question={question("short_text")}
        value=""
        onChange={onChange}
      />,
    );

    await userEvent.type(screen.getByLabelText("Sua resposta"), "is");
    expect(onChange).toHaveBeenCalled();
  });

  it("shows the unsupported message for an unknown type", () => {
    render(
      <AnswerInput
        question={question("sing_along" as QuestionType)}
        value={null}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Tipo de questão não suportado."),
    ).toBeInTheDocument();
  });

  it("degrades to the unsupported message when config has no options", () => {
    render(
      <AnswerInput
        question={question("multiple_choice", {})}
        value={null}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Tipo de questão não suportado."),
    ).toBeInTheDocument();
  });

  it("pre-fills a previously given answer", () => {
    render(
      <AnswerInput
        question={question("short_text")}
        value="already typed"
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Sua resposta")).toHaveValue("already typed");
  });
});
