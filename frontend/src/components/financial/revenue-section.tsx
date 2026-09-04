"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  CircleDollarSign,
  ClipboardCheck,
  ReceiptText,
  Trophy,
  UsersRound,
} from "lucide-react";
import { RevenueLineChart } from "./analytics-charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fetchRevenueSummary } from "@/lib/api";
import { formatBrlFromCents } from "@/lib/financial-utils";
import type {
  FinancialTimeSeriesPoint,
  RevenueSummaryBreakdown,
  RevenueSummaryDetail,
} from "@/lib/types";

const OUTCOME_LABELS = {
  attended: "Realizada",
  no_show: "Falta",
  cancelled: "Cancelada",
  mixed: "Mista",
};

// Labels RevenueRateSource, which is wider than FinancialValueSource (it keeps
// the legacy "generic"/"tenant" values for historical snapshots), so this can't
// share commercial-fields-card's map. The account-level default and the unset
// case must read the same in both, though — the user follows those two across
// screens to find where a price came from.
const SOURCE_LABELS = {
  customer: "Cliente",
  group: "Grupo",
  place: "Local",
  default: "Padrão da conta",
  generic: "Local padrão",
  tenant: "Padrão da conta",
  unset: "Não definido",
};

type BreakdownKey = "place" | "customer" | "group";

const BREAKDOWN_OPTIONS: { key: BreakdownKey; label: string; title: string }[] = [
  { key: "place", label: "Por local", title: "Receita por local" },
  { key: "customer", label: "Por cliente", title: "Receita por cliente" },
  { key: "group", label: "Por grupo", title: "Receita por grupo" },
];

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MoneyBreakdown({ rows }: { rows: RevenueSummaryBreakdown[] }) {
  const maximum = Math.max(1, ...rows.map((row) => Math.max(0, row.total_cents)));
  if (rows.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        Nenhuma receita confirmada neste período.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {rows.slice(0, 8).map((row) => (
        <div key={row.key} className="space-y-1.5">
          <div className="flex justify-between gap-3 text-sm">
            <span className="truncate font-medium">{row.label}</span>
            <span className="shrink-0">{formatBrlFromCents(row.total_cents)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-emerald-600 dark:bg-emerald-500"
              style={{ width: `${(Math.max(0, row.total_cents) / maximum) * 100}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {row.occurrence_count} ocorrência(s)
          </p>
        </div>
      ))}
    </div>
  );
}

export function RevenueSection({
  dateFrom,
  dateTo,
}: {
  dateFrom: string;
  dateTo: string;
}) {
  const [summary, setSummary] = useState<RevenueSummaryDetail | null>(null);
  const [summaryPeriod, setSummaryPeriod] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownKey>("place");
  const requestedPeriod = `${dateFrom}-${dateTo}`;

  useEffect(() => {
    let active = true;
    fetchRevenueSummary(dateFrom, dateTo)
      .then((revenue) => {
        if (!active) return;
        setError(null);
        setSummary(revenue);
        setSummaryPeriod(`${dateFrom}-${dateTo}`);
      })
      .catch((caught) => {
        if (!active) return;
        setError(
          caught instanceof Error ? caught.message : "Não foi possível carregar a receita. Tente novamente."
        );
      })
    return () => {
      active = false;
    };
  }, [dateFrom, dateTo]);

  const chartPoints: FinancialTimeSeriesPoint[] = useMemo(
    () =>
      (summary?.time_series ?? []).map((point) => ({
        date: point.date,
        available_minutes: 0,
        booked_minutes: 0,
        projected_revenue_cents: point.total_cents,
      })),
    [summary]
  );
  const selectedBreakdown = BREAKDOWN_OPTIONS.find(
    (item) => item.key === breakdown
  )!;
  const breakdownRows = (() => {
    if (!summary) return [];
    switch (breakdown) {
      case "customer":
        return summary.by_customer;
      case "group":
        return summary.by_group;
      default:
        return summary.by_place;
    }
  })();

  if (error && !summary) {
    return <p className="text-sm text-destructive" role="alert">{error}</p>;
  }
  if (!summary) {
    return (
      <div className="space-y-5">
        <div className="h-40 animate-pulse rounded-xl bg-muted" />
        <div className="h-72 animate-pulse rounded-xl bg-muted" />
      </div>
    );
  }

  const compositionMetrics = [
    {
      label: "Subtotal faturável",
      value: formatBrlFromCents(summary.subtotal_cents),
      helper: `${summary.billable_participant_count} participante(s) faturável(is)`,
      icon: ReceiptText,
    },
    {
      label: "Ajustes",
      value: formatBrlFromCents(summary.adjustment_cents),
      helper: "Separados do valor calculado",
      icon: ClipboardCheck,
    },
    {
      label: "Renda de eventos",
      value: formatBrlFromCents(summary.event_income_cents),
      helper: `${summary.event_count} evento(s) confirmado(s)`,
      icon: Trophy,
    },
    {
      label: "Ocorrências",
      value: String(summary.occurrence_count),
      helper: `${summary.participant_count} presença(s) registradas`,
      icon: UsersRound,
    },
  ];

  return (
    <div className="space-y-7" aria-busy={summaryPeriod !== requestedPeriod}>
      {error && (
        <p
          className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}

      <section aria-labelledby="realized-revenue-summary">
        <Card className="overflow-hidden border-emerald-600/25">
          <CardContent className="grid gap-0 p-0 lg:grid-cols-[1.1fr_1.4fr]">
            <div className="bg-emerald-500/8 p-5 sm:p-6">
              <div className="flex items-center gap-2 text-sm font-medium text-emerald-800 dark:text-emerald-300">
                <CircleDollarSign className="size-4" />
                <span id="realized-revenue-summary">Receita realizada</span>
              </div>
              <p className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                {formatBrlFromCents(summary.total_cents)}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                Receita de aulas confirmadas no período. {summary.revenue_basis}
              </p>
            </div>
            <div className="grid divide-y border-t sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:border-l lg:border-t-0">
              {compositionMetrics.map(({ label, value, helper, icon: Icon }) => (
                <div key={label} className="p-4 sm:p-5">
                  <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span>{label}</span>
                    <Icon className="size-4 text-emerald-700 dark:text-emerald-400" />
                  </div>
                  <p className="mt-2 text-lg font-semibold tracking-tight">{value}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.45fr_1fr]" aria-label="Evolução e detalhamento da receita">
        <Card>
          <CardHeader>
            <CardTitle>Receita realizada no tempo</CardTitle>
            <CardDescription>Valores confirmados no período selecionado.</CardDescription>
          </CardHeader>
          <CardContent>
            <RevenueLineChart
              points={chartPoints}
              ariaLabel="Evolução da receita confirmada no período"
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="gap-3">
            <div className="flex flex-wrap gap-1 rounded-lg bg-muted p-1" aria-label="Detalhamento da receita">
              {BREAKDOWN_OPTIONS.map((item) => (
                <Button
                  key={item.key}
                  type="button"
                  size="sm"
                  variant={breakdown === item.key ? "secondary" : "ghost"}
                  aria-pressed={breakdown === item.key}
                  onClick={() => setBreakdown(item.key)}
                >
                  {item.label}
                </Button>
              ))}
            </div>
            <div>
              <CardTitle>{selectedBreakdown.title}</CardTitle>
              <CardDescription>Aulas confirmadas no período.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <MoneyBreakdown rows={breakdownRows} />
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="recognized-revenue-history">
        <Card>
          <CardHeader>
            <CardTitle id="recognized-revenue-history">Histórico confirmado</CardTitle>
            <CardDescription>
              Valores e regras são snapshots e não mudam com a configuração atual.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {summary.occurrences.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Nenhuma receita confirmada neste período.
              </p>
            ) : (
              <div className="divide-y">
                {summary.occurrences.map((occurrence) => (
                  <details key={occurrence.id} className="group py-3">
                    <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 rounded-md px-1 py-1 outline-none transition-colors hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring">
                      <div className="flex min-w-0 items-start gap-2">
                        <ChevronDown className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{occurrence.source_label}</span>
                            <Badge variant="secondary">
                              {OUTCOME_LABELS[occurrence.outcome_status]}
                            </Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {formatDateTime(occurrence.starts_at)} · {occurrence.place_name ?? "Sem local"}
                          </p>
                        </div>
                      </div>
                      <div className="pl-6 text-right">
                        <p className="font-semibold">
                          {formatBrlFromCents(occurrence.total_cents)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {occurrence.billable_participant_count}/{occurrence.participant_count} faturáveis
                        </p>
                      </div>
                    </summary>
                    <div className="mt-3 space-y-3 rounded-lg bg-muted/30 p-3">
                      {occurrence.participants.map((participant) => (
                        <div key={participant.id} className="rounded-md border bg-background p-3">
                          <div className="flex justify-between gap-3">
                            <div>
                              <p className="font-medium">{participant.contact_name}</p>
                              <p className="text-xs text-muted-foreground">
                                {OUTCOME_LABELS[participant.attendance_status]} · {participant.billable
                                  ? "Faturável"
                                  : participant.non_billable_reason === "courtesy"
                                    ? "Não faturável (cortesia)"
                                    : "Não faturável"}
                              </p>
                            </div>
                            <p className="font-medium">
                              {formatBrlFromCents(participant.billed_amount_cents)}
                            </p>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {participant.pricing_lines.map((line) => (
                              <Badge key={line.id} variant="outline">
                                {line.time_category === "prime" ? "Nobre" : "Regular"} · {formatBrlFromCents(line.hourly_rate_cents)}/h · {SOURCE_LABELS[line.rate_source]}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ))}
                      <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span>Subtotal: {formatBrlFromCents(occurrence.subtotal_cents)}</span>
                        <span>Ajuste: {formatBrlFromCents(occurrence.adjustment_cents)}</span>
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
