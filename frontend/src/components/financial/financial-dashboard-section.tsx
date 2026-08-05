"use client";

import {
  CalendarRange,
  Clock3,
  CircleDollarSign,
  TrendingUp,
  UsersRound,
} from "lucide-react";
import { CapacityBars, RevenueLineChart } from "./analytics-charts";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatBrlFromCents } from "@/lib/financial-utils";
import type {
  FinancialDashboardDetail,
  PlaceRateMatrixDetail,
} from "@/lib/types";

interface DashboardFilters {
  dateFrom: string;
  dateTo: string;
  placeId: string;
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
  function submitFilters(formData: FormData) {
    onApplyFilters({
      dateFrom: String(formData.get("dateFrom")),
      dateTo: String(formData.get("dateTo")),
      placeId: String(formData.get("placeId") ?? ""),
    });
  }

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
        <CardContent>
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
