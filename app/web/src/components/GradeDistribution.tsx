import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  LinearScale,
  Tooltip,
  type Chart,
  type Plugin,
  type TooltipItem,
} from "chart.js";
import { Bar } from "react-chartjs-2";

import { t } from "@/i18n/pt-BR";
import { formatScore } from "@/lib/format";
import { type BoxStats } from "@/lib/boxplot";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

// One measure (score) faceted by cohort, so a single brand hue rather than a
// categorical palette — the levels are positions on an axis, not separate
// series. That also means no legend is needed; the card title names the measure.
const BOX_FILL = "#FDEEE3"; // primary-light, recessive
const BOX_LINE = "#E8622C"; // primary, carries identity
const MEDIAN_INK = "#181411"; // foreground ink
const GRID = "#E5E3E0";
const AXIS_INK = "#6B7280";

/**
 * The median rule is an ink token, not a second orange.
 *
 * The Flet chart drew it in PRIMARY_DARK over a PRIMARY box outline, which is
 * only ΔE 7.5 apart in normal vision (validated) — the key readout was nearly
 * invisible against its own box. Foreground ink is ΔE 49.3 from the outline.
 */
const boxWhiskerPlugin: Plugin<"bar"> = {
  id: "boxWhiskers",
  afterDatasetsDraw(chart: Chart<"bar">) {
    const stats = (chart.options as { boxStats?: BoxStats[] }).boxStats;
    if (!stats) return;

    const { ctx } = chart;
    const meta = chart.getDatasetMeta(0);
    const yScale = chart.scales.y;
    if (!yScale) return;

    ctx.save();

    stats.forEach((box, i) => {
      const bar = meta.data[i] as { x: number; width: number } | undefined;
      if (!bar) return;

      const { x } = bar;
      const halfWidth = bar.width / 2;
      const capWidth = halfWidth * 0.5;

      ctx.strokeStyle = BOX_LINE;
      ctx.lineWidth = 2;

      // Vertical whisker line, drawn from the box edges outward.
      ctx.beginPath();
      ctx.moveTo(x, yScale.getPixelForValue(box.whiskerHigh));
      ctx.lineTo(x, yScale.getPixelForValue(box.q3));
      ctx.moveTo(x, yScale.getPixelForValue(box.q1));
      ctx.lineTo(x, yScale.getPixelForValue(box.whiskerLow));
      ctx.stroke();

      // Caps.
      for (const value of [box.whiskerHigh, box.whiskerLow]) {
        const y = yScale.getPixelForValue(value);
        ctx.beginPath();
        ctx.moveTo(x - capWidth, y);
        ctx.lineTo(x + capWidth, y);
        ctx.stroke();
      }

      // Median: 2px ink rule spanning the box.
      const medianY = yScale.getPixelForValue(box.median);
      ctx.strokeStyle = MEDIAN_INK;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x - halfWidth, medianY);
      ctx.lineTo(x + halfWidth, medianY);
      ctx.stroke();

      // Outliers as hollow dots, so they read as individual students.
      ctx.strokeStyle = BOX_LINE;
      ctx.fillStyle = "#FFFFFF";
      ctx.lineWidth = 1.5;
      for (const value of box.outliers) {
        ctx.beginPath();
        ctx.arc(x, yScale.getPixelForValue(value), 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    });

    ctx.restore();
  },
};

export function GradeDistribution({ stats }: { stats: BoxStats[] }) {
  return (
    <div className="space-y-4">
      <div className="h-[320px]">
        <Bar
          plugins={[boxWhiskerPlugin]}
          data={{
            labels: stats.map((s) => s.label),
            datasets: [
              {
                // Floating bars give the interquartile box its geometry, real
                // hover targets, and the category scale for free.
                label: t.score,
                data: stats.map((s) => [s.q1, s.q3] as [number, number]),
                backgroundColor: BOX_FILL,
                borderColor: BOX_LINE,
                borderWidth: 2,
                borderRadius: 4,
                borderSkipped: false,
                // A 2px-ish surface gap between adjacent boxes.
                categoryPercentage: 0.6,
                barPercentage: 0.75,
                maxBarThickness: 90,
              },
            ],
          }}
          options={
            {
              responsive: true,
              maintainAspectRatio: false,
              // Read back by the plugin above.
              boxStats: stats,
              scales: {
                x: {
                  grid: { display: false },
                  border: { color: GRID },
                  ticks: { color: AXIS_INK, font: { weight: 600 } },
                },
                y: {
                  beginAtZero: true,
                  title: { display: true, text: t.score, color: AXIS_INK },
                  grid: { color: GRID },
                  border: { display: false },
                  ticks: { color: AXIS_INK },
                },
              },
              plugins: {
                legend: { display: false },
                tooltip: {
                  displayColors: false,
                  backgroundColor: "#FFFFFF",
                  titleColor: MEDIAN_INK,
                  bodyColor: AXIS_INK,
                  borderColor: GRID,
                  borderWidth: 1,
                  padding: 10,
                  callbacks: {
                    title: (items: TooltipItem<"bar">[]) =>
                      items[0] ? `${t.classLevel}: ${items[0].label}` : "",
                    label: (item: TooltipItem<"bar">) => {
                      const box = stats[item.dataIndex];
                      if (!box) return "";
                      return [
                        `n = ${box.count}`,
                        `máx ${formatScore(box.max)}`,
                        `Q3 ${formatScore(box.q3)}`,
                        `mediana ${formatScore(box.median)}`,
                        `Q1 ${formatScore(box.q1)}`,
                        `mín ${formatScore(box.min)}`,
                      ];
                    },
                  },
                },
              },
            } as never
          }
        />
      </div>

      {/* The chart's numbers, reachable without hovering — and without colour. */}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
          {t.showTable}
        </summary>
        <div className="w-full overflow-x-auto pt-3">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-2 py-2 text-left">{t.classLevel}</th>
                <th className="px-2 py-2 text-right">n</th>
                <th className="px-2 py-2 text-right">{t.colMin}</th>
                <th className="px-2 py-2 text-right">Q1</th>
                <th className="px-2 py-2 text-right">{t.colMedian}</th>
                <th className="px-2 py-2 text-right">Q3</th>
                <th className="px-2 py-2 text-right">{t.colMax}</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((s) => (
                <tr
                  key={s.label}
                  className="border-b border-border last:border-0"
                >
                  <td className="px-2 py-2 font-medium">{s.label}</td>
                  <td className="px-2 py-2 text-right">{s.count}</td>
                  <td className="px-2 py-2 text-right">{formatScore(s.min)}</td>
                  <td className="px-2 py-2 text-right">{formatScore(s.q1)}</td>
                  <td className="px-2 py-2 text-right font-semibold">
                    {formatScore(s.median)}
                  </td>
                  <td className="px-2 py-2 text-right">{formatScore(s.q3)}</td>
                  <td className="px-2 py-2 text-right">{formatScore(s.max)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
