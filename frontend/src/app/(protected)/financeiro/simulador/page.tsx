"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FlaskConical } from "lucide-react";
import {
  FinancialPeriodControls,
  type FinancialPeriod,
} from "@/components/financial/financial-period-controls";
import { FinancialSimulator } from "@/components/financial/financial-simulator";
import { Card, CardContent } from "@/components/ui/card";
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

function initialFilters() {
  const today = new Date();
  return {
    dateFrom: dateInputValue(
      new Date(today.getFullYear(), today.getMonth(), 1)
    ),
    dateTo: dateInputValue(
      new Date(today.getFullYear(), today.getMonth() + 1, 0)
    ),
    placeId: "",
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
  const [filters, setFilters] = useState(initialFilters);
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
        const initial = initialFilters();
        const [configurationResult, dashboardResult, scenariosResult] =
          await Promise.all([
            fetchFinancialConfiguration(),
            fetchFinancialDashboard(
              initial.dateFrom,
              initial.dateTo,
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
              : "Falha ao carregar o simulador financeiro"
          );
        }
      }
    });
    return () => {
      active = false;
    };
  }, [router]);

  async function applyFilters(nextFilters: {
    dateFrom: string;
    dateTo: string;
    placeId: string;
  }) {
    setRefreshing(true);
    setError(null);
    try {
      const result = await fetchFinancialDashboard(
        nextFilters.dateFrom,
        nextFilters.dateTo,
        nextFilters.placeId ? [nextFilters.placeId] : [],
        "estimated_when_unconfigured"
      );
      setFilters(nextFilters);
      setDashboard(result);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Falha ao atualizar o contexto do simulador"
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
        <FinancialPeriodControls
          period={{ dateFrom: filters.dateFrom, dateTo: filters.dateTo }}
          refreshing={refreshing}
          onApply={(period: FinancialPeriod) =>
            applyFilters({ ...period, placeId: filters.placeId })
          }
        />
        <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border bg-muted/20 p-3 sm:p-4">
          <div>
            <p className="text-sm font-medium">Local do cenário</p>
            <p className="text-xs text-muted-foreground">
              Afeta apenas a simulação; sua agenda não será alterada.
            </p>
          </div>
          <label className="grid gap-1 text-xs font-medium">
            Local
            <select
              className="h-8 min-w-52 rounded-md border bg-background px-3 text-sm"
              value={filters.placeId}
              disabled={refreshing}
              onChange={(event) =>
                applyFilters({ ...filters, placeId: event.target.value })
              }
            >
              <option value="">Todos os locais</option>
              {configuration.places.map((place) => (
                <option key={place.place_id ?? ""} value={place.place_id ?? ""}>
                  {place.place_name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <FinancialSimulator
          key={`${filters.dateFrom}-${filters.dateTo}-${filters.placeId}`}
          dashboard={dashboard}
          configuration={configuration}
          dateFrom={filters.dateFrom}
          dateTo={filters.dateTo}
          placeId={filters.placeId}
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
                </div>
              ))}
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}
