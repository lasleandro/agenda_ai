import { CalendarCheck2, CircleDollarSign, CircleHelp, Gauge } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatBrlFromCents } from "@/lib/financial-utils";
import type {
  FinancialDashboardDetail,
  RevenueSummaryDetail,
} from "@/lib/types";

function formatHours(minutes: number) {
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: 1,
  }).format(minutes / 60);
}

function todayISO() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(
    today.getDate()
  ).padStart(2, "0")}`;
}

function scheduledToDateCents(dashboard: FinancialDashboardDetail) {
  const today = todayISO();
  return dashboard.time_series
    .filter((point) => point.date <= today)
    .reduce((sum, point) => sum + point.projected_revenue_cents, 0);
}

function fullCapacityCents(dashboard: FinancialDashboardDetail) {
  return (
    dashboard.capacity_presets.find((preset) => preset.key === "observed_demand")
      ?.projected_revenue_cents ?? null
  );
}

export function FinancialMonthSummary({
  monthDashboard,
  monthRevenueSummary,
}: {
  monthDashboard: FinancialDashboardDetail;
  monthRevenueSummary: RevenueSummaryDetail;
}) {
  const cards = [
    {
      label: "Receita estimada até hoje",
      value: formatBrlFromCents(scheduledToDateCents(monthDashboard)),
      icon: CalendarCheck2,
      helper: "Aulas da agenda até hoje, com os preços atuais",
      tooltip:
        "Estimativa operacional das aulas ativas na agenda em datas até hoje. Não significa receita reconhecida: o valor contábil só muda quando as ocorrências encerradas são confirmadas na aba Receita.",
      details: [
        {
          label: "Receita reconhecida",
          value: formatBrlFromCents(monthRevenueSummary.total_cents),
        },
        {
          label: "Eventos confirmados, à parte",
          value: formatBrlFromCents(monthRevenueSummary.event_income_cents),
        },
      ],
    },
    {
      label: "Aulas agendadas no mês",
      value: formatBrlFromCents(monthDashboard.projected_revenue_cents),
      icon: CircleDollarSign,
      helper: "Projeção com os preços atuais",
      details: [],
    },
    {
      label: "Capacidade total do mês",
      value: formatBrlFromCents(fullCapacityCents(monthDashboard)),
      icon: Gauge,
      helper: "Com o mix de participantes observado",
      tooltip:
        "Estimativa de receita com 100% dos minutos disponíveis ocupados. Usa o mix observado de 1 a 4 participantes e os preços atuais. Em locais definidos considera as permanências ativas; sem local definido considera o restante da jornada de trabalho.",
      details: monthDashboard.capacity_sources.map((source) => ({
        label: `${source.label} · ${formatHours(source.available_minutes)}h`,
        value: formatBrlFromCents(source.projected_revenue_cents),
      })),
    },
  ];

  return (
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-3">
      {cards.map(({ label, value, icon: Icon, helper, tooltip, details }) => (
        <Card key={label}>
          <CardHeader className="flex-row items-center justify-between">
            <CardDescription className="flex items-center gap-1.5">
              {label}
              {tooltip && (
                <Tooltip>
                  <TooltipTrigger
                    className="text-muted-foreground"
                    aria-label={`Como ${label.toLowerCase()} é calculada`}
                  >
                    <CircleHelp className="size-3.5" />
                  </TooltipTrigger>
                  <TooltipContent>{tooltip}</TooltipContent>
                </Tooltip>
              )}
            </CardDescription>
            <Icon className="size-4 text-primary" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
            {details.length > 0 && (
              <dl className="mt-3 space-y-1.5 border-t pt-3 text-xs">
                {details.map((detail) => (
                  <div
                    key={detail.label}
                    className="flex items-center justify-between gap-3"
                  >
                    <dt className="text-muted-foreground">{detail.label}</dt>
                    <dd className="shrink-0 font-medium">{detail.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
