import { type QuestionRead } from "@/api/types";
import { MediaBlock } from "@/components/MediaBlock";
import { Card } from "@/components/ui/card";

/** The prompt plus this question's own media (widgets/question_card.py). */
export function QuestionCard({ question }: { question: QuestionRead }) {
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-bold">{question.prompt}</h2>
      <MediaBlock media={question.media} />
    </Card>
  );
}
