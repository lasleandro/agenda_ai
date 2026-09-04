"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CalendarCheck2,
  CalendarClock,
  CalendarDays,
  CalendarX2,
  Clock3,
  BriefcaseBusiness,
  RotateCcw,
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
  FinancialOperationalAnalyticsDetail,
  FinancialMetricBreakdown,
  MonthlyRevenuePoint,
  PlaceRateMatrixDetail,
} from "@/lib/types";

const MONTHLY_TREND_MONTHS = 6;
const MONTH_LABEL_FORMATTER = new Intl.DateTimeFormat("pt-BR", {
  month: "short",
  year: "2-digit",
});

type BreakdownKey = "place" | "part_of_day" | "weekday" | "time_category";

const BREAKDOWNS: {
  key: BreakdownKey;
  label: string;
  title: string;
  emptyMessage: string;
}[] = [
  {
    key: "place",
    label: "Por local",
    title: "Distribuição por local",
    emptyMessage: "Nenhuma capacidade configurada por local neste período.",
  },
  {
    key: "part_of_day",
    label: "Por período",
    title: "Distribuição por período do dia",
    emptyMessage: "Nenhuma capacidade configurada por período neste período.",
  },
  {
    key: "weekday",
    label: "Por semana",
    title: "Distribuição por dia da semana",
    emptyMessage: "Nenhuma capacidade configurada por dia neste período.",
  },
  {
    key: "time_category",
    label: "Regular × nobre",
    title: "Distribuição por categoria de horário",
    emptyMessage: "Nenhuma capacidade configurada por categoria neste período.",
  },
];

function dateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function bucketByMonth(
  dashboard: FinancialDashboardDetail
): MonthlyRevenuePoint[] {
  const totals = new Map<string, number>();
  for (const point of dashboard.time_series) {
    const month = point.date.slice(0, 7);
    totals.set(month, (totals.get(month) ?? 0) + point.projected_revenue_cents);
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

function formatHours(minutes: number) {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(
    minutes / 60
  );
}

function CustomerRankingList({
  title,
  description,
  rows,
  metric,
}: {
  title: string;
  description: string;
  rows: FinancialOperationalAnalyticsDetail["most_frequent_customers"];
  metric: (row: FinancialOperationalAnalyticsDetail["most_frequent_customers"][number]) => string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="py-3 text-sm text-muted-foreground">
            Ainda não há dados suficientes neste período.
          </p>
        ) : (
          <ol className="space-y-3">
            {rows.map((row, index) => (
              <li key={row.contact_id} className="flex items-center gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{row.contact_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {row.executed_count} executada(s) · {row.canceled_count} cancelada(s)
                  </p>
                </div>
                <span className="text-sm font-semibold">{metric(row)}</span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

function EventMetricCard({
  label,
  value,
  helper,
  icon: Icon,
  tone = "text-primary",
}: {
  label: string;
  value: string | number;
  helper: string;
  icon: typeof CalendarCheck2;
  tone?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium">{label}</p>
          <Icon className={`size-4 ${tone}`} aria-hidden="true" />
        </div>
        <p className="mt-3 text-2xl font-semibold tracking-tight">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
      </CardContent>
    </Card>
  );
}

export function FinancialDashboardSection({
  dashboard,
  dateFrom,
  dateTo,
  placeId,
  places,
  operationalAnalytics,
  refreshing,
  onPlaceChange,
}: {
  dashboard: FinancialDashboardDetail;
  dateFrom: string;
  dateTo: string;
  placeId: string;
  places: PlaceRateMatrixDetail[];
  operationalAnalytics: FinancialOperationalAnalyticsDetail;
  refreshing: boolean;
  onPlaceChange: (placeId: string) => void;
}) {
  const [monthlyTrend, setMonthlyTrend] = useState<MonthlyRevenuePoint[] | null>(
    null
  );
  const [trendError, setTrendError] = useState<string | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownKey>("place");

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
      placeId ? [placeId] : []
    )
      .then((result) => {
        if (active) {
          setTrendError(null);
          setMonthlyTrend(bucketByMonth(result));
        }
      })
      .catch((caught) => {
        if (active) {
          setTrendError(
            caught instanceof Error
              ? caught.message
              : "Não foi possível carregar a tendência mensal. Tente novamente."
          );
        }
      });
    return () => {
      active = false;
    };
  }, [placeId]);

  const selectedBreakdown = BREAKDOWNS.find((item) => item.key === breakdown)!;
  const breakdownRows: FinancialMetricBreakdown[] = useMemo(() => {
    switch (breakdown) {
      case "part_of_day":
        return dashboard.by_part_of_day;
      case "weekday":
        return dashboard.by_weekday;
      case "time_category":
        return dashboard.by_time_category;
      default:
        return dashboard.by_place;
    }
  }, [breakdown, dashboard]);

  const supportMetrics = [
    {
      label: "Ocupação",
      value: `${dashboard.occupancy_pct.toFixed(1)}%`,
      helper: `${formatHours(dashboard.booked_minutes)}h ocupadas`,
      icon: TrendingUp,
    },
    {
      label: "Horas livres",
      value: `${formatHours(dashboard.unused_minutes)}h`,
      helper: `${formatHours(dashboard.available_minutes)}h disponíveis`,
      icon: Clock3,
    },
    {
      label: "Horas-aluno",
      value: `${dashboard.participant_hours.toFixed(1)}h`,
      helper: "Carga agendada no período",
      icon: UsersRound,
    },
  ];
  const outcomeTiles = [
    {
      label: "Aulas agendadas",
      value: operationalAnalytics.class_outcomes.total_scheduled_count,
      helper: "Total de slots no período",
      icon: CalendarDays,
      tone: "text-primary",
    },
    {
      label: "Aulas por acontecer",
      value: operationalAnalytics.class_outcomes.upcoming_count,
      helper: "Ativas de hoje em diante",
      icon: CalendarClock,
      tone: "text-primary",
    },
    {
      label: "Aulas executadas",
      value: operationalAnalytics.class_outcomes.executed_count,
      helper: "Aulas ativas em data passada",
      icon: CalendarCheck2,
      tone: "text-emerald-600 dark:text-emerald-400",
    },
    {
      label: "Canceladas c/ reposição",
      value: operationalAnalytics.class_outcomes.canceled_with_makeup_count,
      helper: "Com crédito de reposição",
      icon: RotateCcw,
      tone: "text-amber-600 dark:text-amber-400",
    },
    {
      label: "Canceladas s/ reposição",
      value: operationalAnalytics.class_outcomes.canceled_without_makeup_count,
      helper: "Sem crédito registrado",
      icon: CalendarX2,
      tone: "text-destructive",
    },
  ];

  return (
    <div className="space-y-7" aria-busy={refreshing}>
      <section aria-labelledby="financial-overview-summary">
        <Card className="overflow-hidden border-primary/20">
          <CardContent className="p-0">
            <div className="grid lg:grid-cols-[1.25fr_1fr]">
              <div className="bg-primary/5 p-5 sm:p-6">
                <p
                  className="text-sm font-medium text-primary"
                  id="financial-overview-summary"
                >
                  Resumo do período
                </p>
                <p className="mt-3 text-sm text-muted-foreground">Receita agendada</p>
                <p className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">
                  {formatBrlFromCents(dashboard.projected_revenue_cents)}
                </p>
                <p className="mt-2 max-w-md text-sm text-muted-foreground">
                  Projeção das aulas na agenda com as regras de preço atuais.
                </p>
                {dashboard.unpriced_booking_count > 0 ? (
                  <p className="mt-4 inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-800 dark:text-amber-300">
                    {dashboard.unpriced_booking_count} agendamento(s) sem preço
                  </p>
                ) : (
                  <p className="mt-4 text-xs text-muted-foreground">
                    Todos os agendamentos deste período têm preço definido.
                  </p>
                )}
              </div>
              <div className="grid divide-y border-t lg:grid-cols-3 lg:divide-x lg:divide-y-0 lg:border-l lg:border-t-0">
                {supportMetrics.map(({ label, value, helper, icon: Icon }) => (
                  <div key={label} className="p-4 sm:p-5">
                    <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span>{label}</span>
                      <Icon className="size-4 text-primary" />
                    </div>
                    <p className="mt-3 text-xl font-semibold tracking-tight">{value}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="space-y-3" aria-labelledby="financial-overview-outcomes">
        <div>
          <h2 id="financial-overview-outcomes" className="text-base font-semibold tracking-tight">
            Agenda no período
          </h2>
          <p className="text-sm text-muted-foreground">
            Contagens de aulas no período selecionado; reposições seguem os créditos já registrados na agenda.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {outcomeTiles.map(({ label, value, helper, icon: Icon, tone }) => (
            <Card key={label}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium">{label}</p>
                  <Icon className={`size-4 ${tone}`} aria-hidden="true" />
                </div>
                <p className="mt-3 text-2xl font-semibold tracking-tight">{value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="financial-overview-events">
        <div>
          <h2 id="financial-overview-events" className="text-base font-semibold tracking-tight">
            Eventos no período
          </h2>
          <p className="text-sm text-muted-foreground">
            Eventos do instrutor são acompanhados separadamente das aulas.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <EventMetricCard
            label="Eventos agendados"
            value={operationalAnalytics.instructor_event_outcomes.scheduled_count}
            helper="Confirmados no período"
            icon={BriefcaseBusiness}
          />
          <EventMetricCard
            label="Eventos realizados"
            value={operationalAnalytics.instructor_event_outcomes.completed_count}
            helper="Confirmados em data passada"
            icon={CalendarCheck2}
          />
          <EventMetricCard
            label="Eventos cancelados"
            value={operationalAnalytics.instructor_event_outcomes.canceled_count}
            helper="Cancelamentos registrados"
            icon={CalendarX2}
            tone="text-destructive"
          />
          <EventMetricCard
            label="Receita de eventos"
            value={formatBrlFromCents(operationalAnalytics.instructor_event_outcomes.confirmed_income_cents)}
            helper="Eventos confirmados com valor"
            icon={TrendingUp}
          />
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="financial-overview-makeups">
        <div>
          <h2 id="financial-overview-makeups" className="text-base font-semibold tracking-tight">
            Reposições
          </h2>
          <p className="text-sm text-muted-foreground">
            Capacidade já comprometida para aulas que não geram uma nova receita.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <EventMetricCard
            label="Reposições agendadas"
            value={dashboard.makeup_booking_count}
            helper="Créditos de reposição resgatados"
            icon={RotateCcw}
            tone="text-amber-600 dark:text-amber-400"
          />
          <EventMetricCard
            label="Horas comprometidas"
            value={`${formatHours(dashboard.makeup_booked_minutes)}h`}
            helper="Tempo ocupado na agenda"
            icon={Clock3}
            tone="text-amber-600 dark:text-amber-400"
          />
          <EventMetricCard
            label="Receita potencial comprometida"
            value={formatBrlFromCents(dashboard.makeup_opportunity_cost_cents)}
            helper="Referência pelos preços atuais; não é perda garantida"
            icon={TrendingUp}
            tone="text-amber-600 dark:text-amber-400"
          />
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="financial-overview-performance">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2
              id="financial-overview-performance"
              className="text-base font-semibold tracking-tight"
            >
              Desempenho
            </h2>
            <p className="text-sm text-muted-foreground">
              Receita e ocupação entre {dateFrom.split("-").reverse().join("/")} e {dateTo.split("-").reverse().join("/")}.
            </p>
          </div>
          <label className="grid gap-1 text-xs font-medium">
            Local
            <select
              className="h-8 min-w-48 rounded-md border bg-background px-3 text-sm"
              value={placeId}
              disabled={refreshing}
              onChange={(event) => onPlaceChange(event.target.value)}
            >
              <option value="">Todos os locais</option>
              {places.map((place) => (
                <option key={place.place_id ?? ""} value={place.place_id ?? ""}>
                  {place.place_name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid gap-5 xl:grid-cols-[1.45fr_1fr]">
          <Card>
            <CardHeader>
              <CardTitle>Receita agendada no tempo</CardTitle>
              <CardDescription>Tendência diária do período selecionado.</CardDescription>
            </CardHeader>
            <CardContent>
              <RevenueLineChart points={dashboard.time_series} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Capacidade por local</CardTitle>
              <CardDescription>Ocupação e horas livres configuradas.</CardDescription>
            </CardHeader>
            <CardContent>
              <CapacityBars rows={dashboard.by_place} />
            </CardContent>
          </Card>
        </div>

        {dashboard.available_minutes === 0 && (
          <Card className="border-amber-500/40 bg-amber-500/5">
            <CardContent className="text-sm text-amber-950 dark:text-amber-100">
              Nenhuma capacidade foi encontrada. Configure a jornada e os horários
              reservados em Meus Locais para habilitar as projeções.
            </CardContent>
          </Card>
        )}
      </section>

      <section className="space-y-3" aria-labelledby="financial-overview-distribution">
        <div>
          <h2
            id="financial-overview-distribution"
            className="text-base font-semibold tracking-tight"
          >
            Distribuição da agenda
          </h2>
          <p className="text-sm text-muted-foreground">
            Veja como a capacidade e a receita agendada se distribuem neste período.
          </p>
        </div>
        <Card>
          <CardHeader className="gap-3">
            <div
              className="flex flex-wrap gap-1 rounded-lg bg-muted p-1"
              aria-label="Recorte da distribuição"
            >
              {BREAKDOWNS.map((item) => (
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
              <CardDescription>Ocupação, horas livres e receita agendada.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <CapacityBars
              rows={breakdownRows}
              emptyMessage={selectedBreakdown.emptyMessage}
            />
          </CardContent>
        </Card>
      </section>

      <section className="space-y-3" aria-labelledby="financial-overview-customers">
        <div>
          <h2 id="financial-overview-customers" className="text-base font-semibold tracking-tight">
            Clientes em destaque
          </h2>
          <p className="text-sm text-muted-foreground">
            Frequência e cancelamentos dentro do período selecionado.
          </p>
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          <CustomerRankingList
            title="Mais frequentes"
            description="Aulas ativas em datas passadas."
            rows={operationalAnalytics.most_frequent_customers}
            metric={(row) => `${row.executed_count} aula(s)`}
          />
          <CustomerRankingList
            title="Maior taxa de cancelamento"
            description="Exige ao menos três resultados no período."
            rows={operationalAnalytics.highest_cancellation_rate_customers}
            metric={(row) => `${row.cancellation_rate_pct.toFixed(1)}%`}
          />
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="financial-overview-trend">
        <div>
          <h2
            id="financial-overview-trend"
            className="text-base font-semibold tracking-tight"
          >
            Tendência de longo prazo
          </h2>
          <p className="text-sm text-muted-foreground">
            Independente do período selecionado acima.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Receita agendada por mês</CardTitle>
            <CardDescription>
              Últimos {MONTHLY_TREND_MONTHS} meses, incluindo o mês atual parcial.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {trendError ? (
              <p className="py-8 text-center text-sm text-destructive" role="alert">
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
      </section>

      <details className="rounded-xl border bg-muted/20 px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">
          Premissas e limitações do cálculo
        </summary>
        <div className="mt-3 space-y-2 text-muted-foreground">
          <p>{dashboard.assumptions.capacity_basis}</p>
          <p>{dashboard.assumptions.revenue_basis}</p>
          <p>
            Não considerados: {dashboard.assumptions.excluded_constraints.join("; ")}.
          </p>
        </div>
      </details>
    </div>
  );
}
