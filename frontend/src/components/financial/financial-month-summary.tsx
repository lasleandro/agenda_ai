import { CalendarCheck2, CircleDollarSign, Gauge } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { formatBrlFromCents } from "@/lib/financial-utils";
import type { FinancialDashboardDetail } from "@/lib/types";

function todayISO() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(
    today.getDate()
  ).padStart(2, "0")}`;
}

function realizedCents(dashboard: FinancialDashboardDetail) {
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
}: {
  monthDashboard: FinancialDashboardDetail;
}) {
  const cards = [
    {
      label: "Realizado no mês",
      value: formatBrlFromCents(realizedCents(monthDashboard)),
      icon: CalendarCheck2,
    },
    {
      label: "Projeção do mês",
      value: formatBrlFromCents(monthDashboard.projected_revenue_cents),
      icon: CircleDollarSign,
    },
    {
      label: "Capacidade total do mês",
      value: formatBrlFromCents(fullCapacityCents(monthDashboard)),
      icon: Gauge,
    },
  ];

  return (
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-3">
      {cards.map(({ label, value, icon: Icon }) => (
        <Card key={label}>
          <CardHeader className="flex-row items-center justify-between">
            <CardDescription>{label}</CardDescription>
            <Icon className="size-4 text-primary" />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
