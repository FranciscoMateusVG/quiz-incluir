/** Trim a trailing ".0" the way Python's `f"{value:g}"` does. */
export function formatScore(value: number): string {
  return Number.isInteger(value)
    ? String(value)
    : String(Number(value.toFixed(2)));
}

/**
 * Percentage of max, to one decimal place. `max_score` is 0.0 for a quiz with
 * no gradable points, so the divide has to be guarded.
 */
export function percentage(score: number, maxScore: number): number {
  if (!maxScore) return 0;
  return Math.round(((100 * score) / maxScore) * 10) / 10;
}

/** "vocabulary_grammar" -> "Vocabulary Grammar", matching the Flet admin list. */
export function titleizeCategory(category: string): string {
  return category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
