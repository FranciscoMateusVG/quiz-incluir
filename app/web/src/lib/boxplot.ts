/**
 * Five-number summaries for the grade-distribution chart.
 *
 * The Flet screen got these from matplotlib's `ax.boxplot`, rendered
 * server-side to a base64 PNG. Computing them here keeps the same statistics —
 * a standard Tukey box plot: quartiles by linear interpolation, whiskers to
 * the most extreme value within 1.5 IQR, anything beyond that an outlier.
 */

export interface BoxStats {
  label: string;
  count: number;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  /** Whisker ends: the extreme values still inside the 1.5 IQR fences. */
  whiskerLow: number;
  whiskerHigh: number;
  outliers: number[];
}

/** Percentile by linear interpolation, matching numpy's default. */
export function percentile(sorted: readonly number[], p: number): number {
  if (sorted.length === 0) return 0;
  if (sorted.length === 1) return sorted[0]!;

  const rank = (p / 100) * (sorted.length - 1);
  const low = Math.floor(rank);
  const high = Math.ceil(rank);
  const lowValue = sorted[low]!;
  if (low === high) return lowValue;
  return lowValue + (rank - low) * (sorted[high]! - lowValue);
}

export function boxStats(
  label: string,
  values: readonly number[],
): BoxStats | null {
  if (values.length === 0) return null;

  const sorted = [...values].sort((a, b) => a - b);
  const q1 = percentile(sorted, 25);
  const median = percentile(sorted, 50);
  const q3 = percentile(sorted, 75);
  const iqr = q3 - q1;
  const lowerFence = q1 - 1.5 * iqr;
  const upperFence = q3 + 1.5 * iqr;

  const inside = sorted.filter((v) => v >= lowerFence && v <= upperFence);
  const outliers = sorted.filter((v) => v < lowerFence || v > upperFence);

  return {
    label,
    count: sorted.length,
    min: sorted[0]!,
    q1,
    median,
    q3,
    max: sorted[sorted.length - 1]!,
    whiskerLow: inside.length ? inside[0]! : sorted[0]!,
    whiskerHigh: inside.length
      ? inside[inside.length - 1]!
      : sorted[sorted.length - 1]!,
    outliers,
  };
}
