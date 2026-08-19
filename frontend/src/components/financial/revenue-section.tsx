"use client";

import { useEffect, useState } from "react";
import {
  CircleDollarSign,
  ClipboardCheck,
  ReceiptText,
  Trophy,
  UsersRound,
} from "lucide-react";
import { RevenueLineChart } from "./analytics-charts";
import { Badge } from "@/components/ui/badge";
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

const SOURCE_LABELS = {
  customer: "Cliente",
  group: "Grupo",
  place: "Local",
  generic: "Local padrão",
  tenant: "Padrão",
  unset: "Sem preço",
};

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MoneyBreakdown({
  title,
  rows,
}: {
  title: string;
  rows: RevenueSummaryBreakdown[];
}) {
  const maximum = Math.max(
    1,
    ...rows.map((row) => Math.max(0, row.total_cents))
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Sem receita reconhecida.
          </p>
        ) : (
          <div className="space-y-4">
            {rows.slice(0, 8).map((row) => (
              <div key={row.key} className="space-y-1.5">
                <div className="flex justify-between gap-3 text-xs">
                  <span className="truncate font-medium">{row.label}</span>
                  <span className="shrink-0">
                    {formatBrlFromCents(row.total_cents)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{
                      width: `${(Math.max(0, row.total_cents) / maximum) * 100}%`,
                    }}
                  />
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {row.occurrence_count} ocorrência(s)
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchRevenueSummary(dateFrom, dateTo)
      .then((revenue) => {
        if (!active) return;
        setSummary(revenue);
      })
      .catch((caught) => {
        if (!active) return;
        setError(
          caught instanceof Error
            ? caught.message
            : "Falha ao carregar a receita"
        );
      });
    return () => {
      active = false;
    };
  }, [dateFrom, dateTo]);

  if (error && !summary) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (!summary) {
    return <p className="text-sm text-muted-foreground">Carregando receita...</p>;
  }
  const chartPoints: FinancialTimeSeriesPoint[] = summary.time_series.map(
    (point) => ({
      date: point.date,
      available_minutes: 0,
      booked_minutes: 0,
      projected_revenue_cents: point.total_cents,
    })
  );
  const metrics = [
    {
      label: "Receita reconhecida",
      value: formatBrlFromCents(summary.total_cents),
      helper: summary.revenue_basis,
      icon: CircleDollarSign,
    },
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
      label: "Ocorrências",
      value: String(summary.occurrence_count),
      helper: `${summary.participant_count} presença(s) registradas`,
      icon: UsersRound,
    },
    {
      label: "Renda de eventos",
      value: formatBrlFromCents(summary.event_income_cents),
      helper: `${summary.event_count} evento(s) — arbitragem, workshops, clínicas`,
      icon: Trophy,
    },
  ];

  return (
    <div className="space-y-5">
      {error && (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="rounded-md border bg-muted/20 px-4 py-3 text-sm">
        Período de {dateFrom.split("-").reverse().join("/")} a{" "}
        {dateTo.split("-").reverse().join("/")}. Altere o período na aba Visão
        geral.
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(({ label, value, helper, icon: Icon }) => (
          <Card key={label}>
            <CardHeader className="flex-row items-center justify-between">
              <CardDescription>{label}</CardDescription>
              <Icon className="size-4 text-primary" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">{value}</p>
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                {helper}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Receita reconhecida no tempo</CardTitle>
          </CardHeader>
          <CardContent>
            <RevenueLineChart
              points={chartPoints}
              ariaLabel="Série temporal de receita reconhecida"
            />
          </CardContent>
        </Card>
        <MoneyBreakdown title="Por local" rows={summary.by_place} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <MoneyBreakdown title="Por cliente" rows={summary.by_customer} />
        <MoneyBreakdown title="Por grupo" rows={summary.by_group} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Histórico confirmado</CardTitle>
          <CardDescription>
            Valores e regras abaixo são snapshots e não mudam com a
            configuração atual.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summary.occurrences.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Nenhuma receita reconhecida no período.
            </p>
          ) : (
            <div className="divide-y">
              {summary.occurrences.map((occurrence) => (
                <details key={occurrence.id} className="py-3">
                  <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {occurrence.source_label}
                        </span>
                        <Badge variant="secondary">
                          {OUTCOME_LABELS[occurrence.outcome_status]}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {formatDateTime(occurrence.starts_at)} ·{" "}
                        {occurrence.place_name ?? "Sem local"}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">
                        {formatBrlFromCents(occurrence.total_cents)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {occurrence.billable_participant_count}/
                        {occurrence.participant_count} faturáveis
                      </p>
                    </div>
                  </summary>
                  <div className="mt-3 space-y-3 rounded-lg bg-muted/30 p-3">
                    {occurrence.participants.map((participant) => (
                      <div
                        key={participant.id}
                        className="rounded-md border bg-background p-3"
                      >
                        <div className="flex justify-between gap-3">
                          <div>
                            <p className="font-medium">
                              {participant.contact_name}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {OUTCOME_LABELS[participant.attendance_status]} ·{" "}
                              {participant.billable
                                ? "Faturável"
                                : participant.non_billable_reason === "courtesy"
                                  ? "Não faturável (cortesia)"
                                  : "Não faturável"}
                            </p>
                          </div>
                          <p className="font-medium">
                            {formatBrlFromCents(
                              participant.billed_amount_cents
                            )}
                          </p>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {participant.pricing_lines.map((line) => (
                            <Badge key={line.id} variant="outline">
                              {line.time_category === "prime"
                                ? "Nobre"
                                : "Regular"}{" "}
                              · {formatBrlFromCents(line.hourly_rate_cents)}/h ·{" "}
                              {SOURCE_LABELS[line.rate_source]}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                    <div className="flex justify-end gap-4 text-xs">
                      <span>
                        Subtotal:{" "}
                        {formatBrlFromCents(occurrence.subtotal_cents)}
                      </span>
                      <span>
                        Ajuste:{" "}
                        {formatBrlFromCents(occurrence.adjustment_cents)}
                      </span>
                    </div>
                  </div>
                </details>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
