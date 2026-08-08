"use client";

import { useEffect, useState } from "react";
import {
  CalendarRange,
  Clock3,
  CircleDollarSign,
  TrendingUp,
  UsersRound,
} from "lucide-react";
import {
  CapacityBars,
  MonthlyRevenueBarChart,
  RevenueLineChart,
} from "./analytics-charts";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fetchFinancialDashboard } from "@/lib/api";
import { formatBrlFromCents } from "@/lib/financial-utils";
import type {
  FinancialDashboardDetail,
  MonthlyRevenuePoint,
  PlaceRateMatrixDetail,
} from "@/lib/types";

const MONTHLY_TREND_MONTHS = 6;
const MONTH_LABEL_FORMATTER = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "2-digit",
});

interface DashboardFilters {
  dateFrom: string;
  dateTo: string;
  placeId: string;
}

function dateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function lastNDays(days: number) {
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - (days - 1));
  return { dateFrom: dateInputValue(from), dateTo: dateInputValue(today) };
}

function monthRange(year: number, month: number) {
  return {
    dateFrom: dateInputValue(new Date(year, month, 1)),
    dateTo: dateInputValue(new Date(year, month + 1, 0)),
  };
}

function lastNClosedMonths(count: number) {
  const today = new Date();
  return Array.from({ length: count }, (_, index) => {
    const reference = new Date(today.getFullYear(), today.getMonth() - index, 1);
    return {
      year: reference.getFullYear(),
      month: reference.getMonth(),
      label: MONTH_LABEL_FORMATTER.format(reference),
    };
  });
}

function bucketByMonth(
  dashboard: FinancialDashboardDetail
): MonthlyRevenuePoint[] {
  const totals = new Map<string, number>();
  for (const point of dashboard.time_series) {
    const month = point.date.slice(0, 7);
    totals.set(
      month,
      (totals.get(month) ?? 0) + point.projected_revenue_cents
    );
  }
  return Array.from(totals.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, projected_revenue_cents]) => {
      const [year, monthIndex] = month.split("-").map(Number);
      return {
        month,
        label: MONTH_LABEL_FORMATTER.format(new Date(year, monthIndex - 1, 1)),
        projected_revenue_cents,
      };
    });
}

export function FinancialDashboardSection({
  dashboard,
  filters,
  places,
  refreshing,
  onApplyFilters,
}: {
  dashboard: FinancialDashboardDetail;
  filters: DashboardFilters;
  places: PlaceRateMatrixDetail[];
  refreshing: boolean;
  onApplyFilters: (filters: DashboardFilters) => void;
}) {
  const [monthlyTrend, setMonthlyTrend] = useState<
    MonthlyRevenuePoint[] | null
  >(null);
  const [trendError, setTrendError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const today = new Date();
    const from = new Date(
      today.getFullYear(),
      today.getMonth() - (MONTHLY_TREND_MONTHS - 1),
      1
    );
    fetchFinancialDashboard(
      dateInputValue(from),
      dateInputValue(today),
      filters.placeId ? [filters.placeId] : []
    )
      .then((result) => {
        if (active) setMonthlyTrend(bucketByMonth(result));
      })
      .catch((caught) => {
        if (active) {
          setTrendError(
            caught instanceof Error
              ? caught.message
              : "Falha ao carregar tendência mensal"
          );
        }
      });
    return () => {
      active = false;
    };
  }, [filters.placeId]);

  function submitFilters(formData: FormData) {
    onApplyFilters({
      dateFrom: String(formData.get("dateFrom")),
      dateTo: String(formData.get("dateTo")),
      placeId: String(formData.get("placeId") ?? ""),
    });
  }

  function applyPreset(range: { dateFrom: string; dateTo: string }) {
    onApplyFilters({ ...range, placeId: filters.placeId });
  }

  function applyClosedMonth(value: string) {
    if (!value) return;
    const [year, month] = value.split("-").map(Number);
    applyPreset(monthRange(year, month - 1));
  }

  const days15 = lastNDays(15);
  const days30 = lastNDays(30);
  const isDays15Active =
    filters.dateFrom === days15.dateFrom && filters.dateTo === days15.dateTo;
  const isDays30Active =
    filters.dateFrom === days30.dateFrom && filters.dateTo === days30.dateTo;
  const activeClosedMonth = (() => {
    const [year, month] = filters.dateFrom.split("-").map(Number);
    if (!year || !month) return "";
    const range = monthRange(year, month - 1);
    return range.dateFrom === filters.dateFrom && range.dateTo === filters.dateTo
      ? `${year}-${month}`
      : "";
  })();

  const metrics = [
    {
      label: "Receita agendada",
      value: formatBrlFromCents(dashboard.projected_revenue_cents),
      helper: `${dashboard.unpriced_booking_count} agendamento(s) sem preço`,
      icon: CircleDollarSign,
    },
    {
      label: "Ocupação",
      value: `${dashboard.occupancy_pct.toFixed(1)}%`,
      helper: `${(dashboard.booked_minutes / 60).toFixed(1)}h ocupadas`,
      icon: TrendingUp,
    },
    {
      label: "Aberturas",
      value: `${(dashboard.unused_minutes / 60).toFixed(1)}h`,
      helper: `${(dashboard.available_minutes / 60).toFixed(1)}h disponíveis`,
      icon: Clock3,
    },
    {
      label: "Horas-aluno",
      value: `${dashboard.participant_hours.toFixed(1)}h`,
      helper: "Carga agendada no período",
      icon: UsersRound,
    },
  ];

  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant={isDays15Active ? "default" : "outline"}
              size="sm"
              aria-pressed={isDays15Active}
              onClick={() => applyPreset(days15)}
              disabled={refreshing}
            >
              Últimos 15 dias
            </Button>
            <Button
              type="button"
              variant={isDays30Active ? "default" : "outline"}
              size="sm"
              aria-pressed={isDays30Active}
              onClick={() => applyPreset(days30)}
              disabled={refreshing}
            >
              Últimos 30 dias
            </Button>
            <label className="grid gap-1 text-xs font-medium">
              <span className="sr-only">Mês fechado</span>
              <select
                className={`h-7 rounded-md border px-2 text-xs ${
                  activeClosedMonth
                    ? "border-primary bg-primary/10 font-medium text-primary"
                    : "bg-background"
                }`}
                value={activeClosedMonth}
                disabled={refreshing}
                onChange={(event) => applyClosedMonth(event.target.value)}
              >
                <option value="" disabled>
                  Mês fechado...
                </option>
                {lastNClosedMonths(12).map(({ year, month, label }) => (
                  <option key={`${year}-${month}`} value={`${year}-${month + 1}`}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <form
            action={submitFilters}
            className="flex flex-wrap items-end gap-3"
          >
            <label className="grid gap-1 text-xs font-medium">
              De
              <input
                className="h-9 rounded-md border bg-background px-3 text-sm"
                type="date"
                name="dateFrom"
                defaultValue={filters.dateFrom}
                required
              />
            </label>
            <label className="grid gap-1 text-xs font-medium">
              Até
              <input
                className="h-9 rounded-md border bg-background px-3 text-sm"
                type="date"
                name="dateTo"
                defaultValue={filters.dateTo}
                required
              />
            </label>
            <label className="grid min-w-56 gap-1 text-xs font-medium">
              Local
              <select
                className="h-9 rounded-md border bg-background px-3 text-sm"
                name="placeId"
                defaultValue={filters.placeId}
              >
                <option value="">Todos os locais</option>
                {places.map((place) => (
                  <option key={place.place_id} value={place.place_id}>
                    {place.place_name}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" disabled={refreshing}>
              <CalendarRange className="size-4" />
              {refreshing ? "Atualizando..." : "Aplicar período"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(({ label, value, helper, icon: Icon }) => (
          <Card key={label}>
            <CardHeader className="flex-row items-center justify-between">
              <CardDescription>{label}</CardDescription>
              <Icon className="size-4 text-primary" />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold tracking-tight">{value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {dashboard.available_minutes === 0 && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="text-sm">
            Nenhuma capacidade foi encontrada. Configure a jornada e os
            horários reservados em Meus Locais para habilitar as projeções.
          </CardContent>
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Receita agendada no tempo</CardTitle>
            <CardDescription>
              Tendência diária com as regras de preço atuais.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <RevenueLineChart points={dashboard.time_series} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Aberturas por local</CardTitle>
            <CardDescription>
              Horas livres dentro da capacidade configurada.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CapacityBars rows={dashboard.by_place} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Por período do dia</CardTitle>
          </CardHeader>
          <CardContent>
            <CapacityBars rows={dashboard.by_part_of_day} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Por dia da semana</CardTitle>
          </CardHeader>
          <CardContent>
            <CapacityBars rows={dashboard.by_weekday} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Regular × nobre</CardTitle>
          </CardHeader>
          <CardContent>
            <CapacityBars rows={dashboard.by_time_category} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Potencial com 100% da capacidade</CardTitle>
          <CardDescription>
            Três referências usando as mesmas horas e os preços configurados.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {dashboard.capacity_presets.map((preset) => (
            <div
              key={preset.key}
              className="rounded-lg border bg-muted/20 p-4"
            >
              <p className="font-medium">{preset.label}</p>
              <p className="mt-3 text-xl font-semibold">
                {formatBrlFromCents(preset.projected_revenue_cents)}
              </p>
              <p className="text-xs text-muted-foreground">
                {preset.participant_hours.toFixed(1)} horas-aluno
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="space-y-3 border-t pt-5">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Tendência de longo prazo
          </h2>
          <p className="text-xs text-muted-foreground">
            Independente do período selecionado acima.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Tendência mensal de receita</CardTitle>
            <CardDescription>
              Últimos {MONTHLY_TREND_MONTHS} meses.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {trendError ? (
              <p className="py-8 text-center text-sm text-destructive">
                {trendError}
              </p>
            ) : monthlyTrend === null ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Carregando tendência...
              </p>
            ) : (
              <MonthlyRevenueBarChart points={monthlyTrend} />
            )}
          </CardContent>
        </Card>
      </div>

      <details className="rounded-lg border bg-muted/20 px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">
          Premissas e limitações do cálculo
        </summary>
        <div className="mt-3 space-y-2 text-muted-foreground">
          <p>{dashboard.assumptions.capacity_basis}</p>
          <p>{dashboard.assumptions.revenue_basis}</p>
          <p>
            Não considerados:{" "}
            {dashboard.assumptions.excluded_constraints.join("; ")}.
          </p>
        </div>
      </details>
    </div>
  );
}
