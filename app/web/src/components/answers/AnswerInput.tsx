/**
 * Answer inputs, one per question type.
 *
 * Ports the strategy pattern from
 * `app/frontend/widgets/answers/answer_factory.py`. Each variant is a
 * controlled input over an {@link AnswerValue}; converting that to the wire
 * payload lives in `api/config.ts` so the shapes stay in one place.
 *
 * The Flet version hand-rolled an `_option_row()` helper because its Radio and
 * Checkbox labels would not wrap, and it had to abandon a "tap anywhere on the
 * row" affordance because Flet freezes a component's control tree after
 * render. A <label> wrapping the control gives us both for free.
 */

import { type AnswerValue } from "@/api/config";
import { type QuestionRead } from "@/api/types";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { t } from "@/i18n/pt-BR";
import { parseOptions } from "@/api/config";

export interface AnswerInputProps {
  question: QuestionRead;
  value: AnswerValue;
  onChange: (value: AnswerValue) => void;
}

const ROW =
  "flex cursor-pointer items-center gap-3 rounded-input px-2 py-2 hover:bg-muted";

export function AnswerInput({ question, value, onChange }: AnswerInputProps) {
  switch (question.type) {
    case "multiple_choice":
      return (
        <MultipleChoice question={question} value={value} onChange={onChange} />
      );
    case "multiple_selection":
      return (
        <MultipleSelection
          question={question}
          value={value}
          onChange={onChange}
        />
      );
    case "true_false":
      return <TrueFalse value={value} onChange={onChange} />;
    case "short_text":
      return <ShortText value={value} onChange={onChange} />;
    default:
      return <p className="text-destructive">{t.unsupportedQuestionType}</p>;
  }
}

function MultipleChoice({ question, value, onChange }: AnswerInputProps) {
  const options = parseOptions(question.config);
  if (!options)
    return <p className="text-destructive">{t.unsupportedQuestionType}</p>;

  return (
    <RadioGroup
      value={typeof value === "string" ? value : ""}
      onValueChange={onChange}
      className="gap-1"
    >
      {options.map((option, i) => {
        const id = `${question.id}-opt-${i}`;
        return (
          <label key={id} htmlFor={id} className={ROW}>
            {/* The option text is the answer: grading compares strings, not
                indices (see api/config.ts). */}
            <RadioGroupItem id={id} value={option} />
            <span className="flex-1">{option}</span>
          </label>
        );
      })}
    </RadioGroup>
  );
}

function MultipleSelection({ question, value, onChange }: AnswerInputProps) {
  const options = parseOptions(question.config);
  if (!options)
    return <p className="text-destructive">{t.unsupportedQuestionType}</p>;

  const selected = Array.isArray(value) ? value : [];

  const toggle = (option: string, checked: boolean) => {
    // Rebuild in option order so the payload does not depend on click order.
    const next = new Set(selected);
    if (checked) next.add(option);
    else next.delete(option);
    onChange(options.filter((o) => next.has(o)));
  };

  return (
    <div className="grid gap-1">
      {options.map((option, i) => {
        const id = `${question.id}-chk-${i}`;
        return (
          <label key={id} htmlFor={id} className={ROW}>
            <Checkbox
              id={id}
              checked={selected.includes(option)}
              onCheckedChange={(checked) => toggle(option, checked === true)}
            />
            <span className="flex-1">{option}</span>
          </label>
        );
      })}
    </div>
  );
}

function TrueFalse({ value, onChange }: Omit<AnswerInputProps, "question">) {
  // Radix needs string values; the payload carries a real boolean, because the
  // grader compares with a strict == against config.answer.
  const asString = typeof value === "boolean" ? String(value) : "";

  return (
    <RadioGroup
      value={asString}
      onValueChange={(next) => onChange(next === "true")}
      className="flex flex-row gap-3"
    >
      {(["true", "false"] as const).map((option) => (
        <label key={option} htmlFor={`tf-${option}`} className={ROW}>
          <RadioGroupItem id={`tf-${option}`} value={option} />
          <span>{option === "true" ? t.trueLabel : t.falseLabel}</span>
        </label>
      ))}
    </RadioGroup>
  );
}

function ShortText({ value, onChange }: Omit<AnswerInputProps, "question">) {
  return (
    <Input
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={t.yourAnswer}
      aria-label={t.yourAnswer}
    />
  );
}
