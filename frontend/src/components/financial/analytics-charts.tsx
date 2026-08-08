"use client";

import type {
  FinancialMetricBreakdown,
  FinancialTimeSeriesPoint,
  MonthlyRevenuePoint,
} from "@/lib/types";
import { formatBrlFromCents } from "@/lib/financial-utils";

function compactCurrency(cents: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(cents / 100);
}

export function RevenueLineChart({
  points,
  ariaLabel = "Série temporal de receita agendada",
}: {
  points: FinancialTimeSeriesPoint[];
  ariaLabel?: string;
}) {
  const width = 720;
  const height = 220;
  const padding = 28;
  const maxValue = Math.max(
    1,
    ...points.map((point) => point.projected_revenue_cents)
  );
  const coordinates = points.map((point, index) => {
    const x =
      points.length === 1
        ? width / 2
        : padding + (index / (points.length - 1)) * (width - padding * 2);
    const y =
      height -
      padding -
      (point.projected_revenue_cents / maxValue) * (height - padding * 2);
    return { ...point, x, y };
  });
  const path = coordinates
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");

  return (
    <div>
      <svg
        className="h-56 w-full overflow-visible"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
      >
        {[0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = height - padding - ratio * (height - padding * 2);
          return (
            <g key={ratio}>
              <line
                x1={padding}
                x2={width - padding}
                y1={y}
                y2={y}
                className="stroke-border"
                strokeDasharray="4 5"
              />
              <text
                x={padding}
                y={y - 5}
                className="fill-muted-foreground text-[10px]"
              >
                {compactCurrency(maxValue * ratio)}
              </text>
            </g>
          );
        })}
        <path
          d={path}
          fill="none"
          className="stroke-primary"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {coordinates.map((point) => (
          <circle
            key={point.date}
            cx={point.x}
            cy={point.y}
            r="4"
            className="fill-primary stroke-background"
            strokeWidth="2"
          >
            <title>
              {point.date}: {formatBrlFromCents(point.projected_revenue_cents)}
            </title>
          </circle>
        ))}
      </svg>
      {points.length > 0 && (
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{points[0].date.split("-").reverse().join("/")}</span>
          <span>
            {points[points.length - 1].date.split("-").reverse().join("/")}
          </span>
        </div>
      )}
    </div>
  );
}

export function MonthlyRevenueBarChart({
  points,
  ariaLabel = "Tendência mensal de receita agendada",
}: {
  points: MonthlyRevenuePoint[];
  ariaLabel?: string;
}) {
  if (points.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Sem dados suficientes para calcular a tendência.
      </p>
    );
  }

  const width = 720;
  const height = 220;
  const padding = 28;
  const maxValue = Math.max(
    1,
    ...points.map((point) => point.projected_revenue_cents)
  );
  const barGap = 12;
  const barWidth =
    (width - padding * 2 - barGap * (points.length - 1)) / points.length;

  return (
    <div>
      <svg
        className="h-56 w-full overflow-visible"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
      >
        {[0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = height - padding - ratio * (height - padding * 2);
          return (
            <g key={ratio}>
              <line
                x1={padding}
                x2={width - padding}
                y1={y}
                y2={y}
                className="stroke-border"
                strokeDasharray="4 5"
              />
              <text
                x={padding}
                y={y - 5}
                className="fill-muted-foreground text-[10px]"
              >
                {compactCurrency(maxValue * ratio)}
              </text>
            </g>
          );
        })}
        {points.map((point, index) => {
          const barHeight =
            (point.projected_revenue_cents / maxValue) * (height - padding * 2);
          const x = padding + index * (barWidth + barGap);
          const y = height - padding - barHeight;
          const previous = index > 0 ? points[index - 1] : null;
          const pctChange =
            previous && previous.projected_revenue_cents > 0
              ? ((point.projected_revenue_cents -
                  previous.projected_revenue_cents) /
                  previous.projected_revenue_cents) *
                100
              : null;
          return (
            <g key={point.month}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(0, barHeight)}
                rx={4}
                className={
                  index === points.length - 1
                    ? "fill-primary"
                    : "fill-primary/50"
                }
              >
                <title>
                  {point.label}: {formatBrlFromCents(point.projected_revenue_cents)}
                  {pctChange !== null
                    ? ` (${pctChange >= 0 ? "+" : ""}${pctChange.toFixed(1)}% vs. mês anterior)`
                    : ""}
                </title>
              </rect>
              {index === points.length - 1 && pctChange !== null && (
                <text
                  x={x + barWidth / 2}
                  y={Math.max(12, y - 6)}
                  textAnchor="middle"
                  className={
                    pctChange >= 0
                      ? "fill-emerald-600 text-[10px] font-medium"
                      : "fill-destructive text-[10px] font-medium"
                  }
                >
                  {pctChange >= 0 ? "+" : ""}
                  {pctChange.toFixed(1)}%
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between text-xs text-muted-foreground">
        {points.map((point) => (
          <span key={point.month}>{point.label}</span>
        ))}
      </div>
    </div>
  );
}

export function CapacityBars({
  rows,
  emptyMessage = "Nenhuma capacidade configurada neste recorte.",
}: {
  rows: FinancialMetricBreakdown[];
  emptyMessage?: string;
}) {
  if (rows.every((row) => row.available_minutes === 0)) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        {emptyMessage}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {rows.map((row) => (
        <div key={row.key} className="space-y-1.5">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="truncate font-medium">{row.label}</span>
            <span className="shrink-0 text-muted-foreground">
              {(row.unused_minutes / 60).toFixed(1)}h livres ·{" "}
              {row.occupancy_pct.toFixed(1)}%
            </span>
          </div>
          <div
            className="h-2.5 overflow-hidden rounded-full bg-muted"
            title={`${row.label}: ${row.occupancy_pct}% ocupado`}
          >
            <div
              className="h-full rounded-full bg-primary transition-[width]"
              style={{ width: `${Math.min(100, row.occupancy_pct)}%` }}
            />
          </div>
          <div className="text-right text-[11px] text-muted-foreground">
            {formatBrlFromCents(row.projected_revenue_cents)} agendados
          </div>
        </div>
      ))}
    </div>
  );
}
