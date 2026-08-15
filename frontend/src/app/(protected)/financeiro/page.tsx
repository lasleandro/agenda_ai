"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  CircleDollarSign,
  FlaskConical,
  ReceiptText,
  Settings2,
} from "lucide-react";
import { FinancialDashboardSection } from "@/components/financial/financial-dashboard-section";
import { FinancialMonthSummary } from "@/components/financial/financial-month-summary";
import { FinancialSimulator } from "@/components/financial/financial-simulator";
import { GlobalRatesSection } from "@/components/financial/global-rates-section";
import { PlaceRatesSection } from "@/components/financial/place-rates-section";
import { PrimeTimeSection } from "@/components/financial/prime-time-section";
import { RevenueSection } from "@/components/financial/revenue-section";
import {
  fetchFinancialDashboard,
  fetchFinancialConfiguration,
  fetchFinancialScenarios,
  fetchFinancialSettings,
} from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import type {
  FinancialConfigurationDetail,
  FinancialDashboardDetail,
  GenericPlaceRateMatrixDetail,
  FinancialScenarioDetail,
  FinancialSettingsDetail,
  PlaceRateMatrixDetail,
} from "@/lib/types";

type FinanceTab = "dashboard" | "revenue" | "simulator" | "configuration";

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

export default function FinanceiroPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<FinanceTab>("dashboard");
  const [filters, setFilters] = useState(initialFilters);
  const [settings, setSettings] = useState<FinancialSettingsDetail | null>(null);
  const [configuration, setConfiguration] =
    useState<FinancialConfigurationDetail | null>(null);
  const [dashboard, setDashboard] =
    useState<FinancialDashboardDetail | null>(null);
  const [monthDashboard, setMonthDashboard] =
    useState<FinancialDashboardDetail | null>(null);
  const [scenarios, setScenarios] = useState<FinancialScenarioDetail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let active = true;
    fetchSession().then(async (user) => {
      if (!active) return;
      if (!sessionHasFeature(user, "commercial_financials")) {
        router.replace("/");
        return;
      }
      try {
        const initial = initialFilters();
        const [
          settingsResult,
          configurationResult,
          dashboardResult,
          scenariosResult,
        ] = await Promise.all([
          fetchFinancialSettings(),
          fetchFinancialConfiguration(),
          fetchFinancialDashboard(initial.dateFrom, initial.dateTo),
          fetchFinancialScenarios(),
        ]);
        if (!active) return;
        setSettings(settingsResult);
        setConfiguration(configurationResult);
        setDashboard(dashboardResult);
        setMonthDashboard(dashboardResult);
        setScenarios(scenariosResult.scenarios);
      } catch (caught) {
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Falha ao carregar o Financeiro"
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
        nextFilters.placeId ? [nextFilters.placeId] : []
      );
      setFilters(nextFilters);
      setDashboard(result);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Falha ao atualizar o dashboard"
      );
    } finally {
      setRefreshing(false);
    }
  }

  function updatePlace(matrix: PlaceRateMatrixDetail) {
    setConfiguration((current) =>
      current
        ? {
            ...current,
            places: current.places.map((place) =>
              place.place_id === matrix.place_id ? matrix : place
            ),
          }
        : current
    );
  }

  function updateGenericPlace(matrix: GenericPlaceRateMatrixDetail) {
    setConfiguration((current) =>
      current ? { ...current, generic_place: matrix } : current
    );
  }

  if (error && (!settings || !configuration || !dashboard)) {
    return <div className="p-6 text-sm text-destructive">{error}</div>;
  }

  if (!settings || !configuration || !dashboard) {
    return <div className="p-6 text-sm text-muted-foreground">Carregando...</div>;
  }

  const tabs: {
    key: FinanceTab;
    label: string;
    icon: typeof BarChart3;
  }[] = [
    { key: "dashboard", label: "Visão geral", icon: BarChart3 },
    { key: "revenue", label: "Receita", icon: ReceiptText },
    { key: "simulator", label: "Simulador", icon: FlaskConical },
    { key: "configuration", label: "Configuração", icon: Settings2 },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-auto p-4 md:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <CircleDollarSign className="h-5 w-5 text-primary" />
          Financeiro
        </h1>
        <p className="text-sm text-muted-foreground">
          Acompanhe capacidade, compare cenários e configure suas regras.
        </p>
      </div>

      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
        {monthDashboard && <FinancialMonthSummary monthDashboard={monthDashboard} />}

        <div
          className="flex w-fit gap-1 rounded-lg border bg-muted/30 p-1"
          role="tablist"
          aria-label="Áreas do Financeiro"
        >
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={activeTab === key}
              onClick={() => setActiveTab(key)}
              className={`flex h-8 items-center gap-1.5 rounded-md px-3 text-sm transition-colors ${
                activeTab === key
                  ? "bg-background font-medium shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </div>

        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {activeTab === "dashboard" && (
          <FinancialDashboardSection
            key={`${filters.dateFrom}-${filters.dateTo}-${filters.placeId}`}
            dashboard={dashboard}
            filters={filters}
            places={configuration.places}
            refreshing={refreshing}
            onApplyFilters={applyFilters}
          />
        )}

        {activeTab === "simulator" && (
          <FinancialSimulator
            key={`${filters.dateFrom}-${filters.dateTo}-${filters.placeId}`}
            dashboard={dashboard}
            settings={settings}
            configuration={configuration}
            dateFrom={filters.dateFrom}
            dateTo={filters.dateTo}
            placeId={filters.placeId}
            initialScenarios={scenarios}
          />
        )}

        {activeTab === "revenue" && (
          <RevenueSection
            key={`${filters.dateFrom}-${filters.dateTo}`}
            dateFrom={filters.dateFrom}
            dateTo={filters.dateTo}
          />
        )}

        {activeTab === "configuration" && (
          <>
            <GlobalRatesSection settings={settings} onSaved={setSettings} />
            <PrimeTimeSection
              windows={configuration.prime_time_windows}
              onSaved={(windows) =>
                setConfiguration((current) =>
                  current
                    ? { ...current, prime_time_windows: windows }
                    : current
                )
              }
            />
            <PlaceRatesSection
              genericPlace={configuration.generic_place}
              places={configuration.places}
              onSaved={updatePlace}
              onGenericSaved={updateGenericPlace}
            />
          </>
        )}
      </div>
    </div>
  );
}
