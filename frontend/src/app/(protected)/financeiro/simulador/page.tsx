"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FlaskConical, Info } from "lucide-react";
import { FinancialSimulator } from "@/components/financial/financial-simulator";
import { Card, CardContent } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  fetchFinancialConfiguration,
  fetchFinancialDashboard,
  fetchFinancialScenarios,
} from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import type {
  FinancialConfigurationDetail,
  FinancialDashboardDetail,
  FinancialScenarioDetail,
} from "@/lib/types";
import { useRouter } from "next/navigation";
import { formatBrlFromCents } from "@/lib/financial-utils";

function dateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function currentMonthRange() {
  const today = new Date();
  return {
    dateFrom: dateInputValue(
      new Date(today.getFullYear(), today.getMonth(), 1)
    ),
    dateTo: dateInputValue(
      new Date(today.getFullYear(), today.getMonth() + 1, 0)
    ),
  };
}

export default function FinancialSimulatorPage() {
  const router = useRouter();
  const [configuration, setConfiguration] =
    useState<FinancialConfigurationDetail | null>(null);
  const [dashboard, setDashboard] =
    useState<FinancialDashboardDetail | null>(null);
  const [scenarios, setScenarios] = useState<FinancialScenarioDetail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [{ dateFrom, dateTo }] = useState(currentMonthRange);
  const [placeId, setPlaceId] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let active = true;
    fetchSession().then(async (user) => {
      if (!active) return;
      if (!sessionHasFeature(user, "commercial_financials")) {
        router.replace("/agenda");
        return;
      }
      try {
        const [configurationResult, dashboardResult, scenariosResult] =
          await Promise.all([
            fetchFinancialConfiguration(),
            fetchFinancialDashboard(
              dateFrom,
              dateTo,
              [],
              "estimated_when_unconfigured"
            ),
            fetchFinancialScenarios(),
          ]);
        if (!active) return;
        setConfiguration(configurationResult);
        setDashboard(dashboardResult);
        setScenarios(scenariosResult.scenarios);
      } catch (caught) {
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Não foi possível carregar o simulador financeiro. Tente novamente."
          );
        }
      }
    });
    return () => {
      active = false;
    };
  }, [router, dateFrom, dateTo]);

  async function applyLocation(nextPlaceId: string) {
    setRefreshing(true);
    setError(null);
    try {
      const result = await fetchFinancialDashboard(
        dateFrom,
        dateTo,
        nextPlaceId ? [nextPlaceId] : [],
        "estimated_when_unconfigured"
      );
      setPlaceId(nextPlaceId);
      setDashboard(result);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Não foi possível atualizar o simulador. Tente novamente."
      );
    } finally {
      setRefreshing(false);
    }
  }

  if (error && (!configuration || !dashboard)) {
    return <div className="p-6 text-sm text-destructive">{error}</div>;
  }

  if (!configuration || !dashboard) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-auto p-4 md:p-6">
        <div className="h-14 animate-pulse rounded-xl bg-muted" />
        <div className="h-96 animate-pulse rounded-xl bg-muted" />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-auto p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            <FlaskConical className="size-5 text-primary" />
            Simulador financeiro
          </h1>
          <p className="text-sm text-muted-foreground">
            Teste cenários sem alterar sua agenda ou seus preços configurados.
          </p>
        </div>
        <Link
          href="/financeiro"
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-medium transition-colors hover:bg-muted"
        >
          <ArrowLeft className="size-3.5" />
          Voltar ao financeiro
        </Link>
      </div>

      {error && (
        <p
          className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}

      <div className="mx-auto w-full max-w-7xl space-y-5">
        <FinancialSimulator
          key={`${dateFrom}-${dateTo}-${placeId}`}
          dashboard={dashboard}
          configuration={configuration}
          dateFrom={dateFrom}
          dateTo={dateTo}
          placeId={placeId}
          onLocationChange={applyLocation}
          locationBusy={refreshing}
          initialScenarios={scenarios}
        />
        <section className="space-y-3" aria-labelledby="simulator-potential">
          <div>
            <h2 id="simulator-potential" className="text-base font-semibold tracking-tight">
              Potencial
            </h2>
            <p className="text-sm text-muted-foreground">
              Referências hipotéticas para 100% da capacidade com os preços configurados.
            </p>
          </div>
          <Card>
            <CardContent className="grid gap-0 divide-y p-0 md:grid-cols-3 md:divide-x md:divide-y-0">
              {dashboard.capacity_presets.map((preset) => (
                <div key={preset.key} className="p-5">
                  <p className="text-sm font-medium">{preset.label}</p>
                  <p className="mt-3 text-2xl font-semibold tracking-tight">
                    {formatBrlFromCents(preset.projected_revenue_cents)}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {preset.participant_hours.toFixed(1)} horas-aluno
                  </p>
                  <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                    {preset.customer_estimate.maximum_customers > 0
                      ? `${preset.customer_estimate.minimum_customers}–${preset.customer_estimate.maximum_customers} clientes`
                      : "— clientes"}
                    <Tooltip>
                      <TooltipTrigger
                        className="text-muted-foreground"
                        aria-label="Como a base de clientes é estimada"
                      >
                        <Info className="size-3" />
                      </TooltipTrigger>
                      <TooltipContent>
                        Estimativa por horas-aluno: cada cliente ocupa de 1 a 3
                        horas por semana. Quem faz duas aulas semanais conta como
                        um cliente que ocupa mais horas.
                      </TooltipContent>
                    </Tooltip>
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}
