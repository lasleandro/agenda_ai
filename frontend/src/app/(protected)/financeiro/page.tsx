"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BarChart3, CircleDollarSign, ReceiptText } from "lucide-react";
import { FinancialDashboardSection } from "@/components/financial/financial-dashboard-section";
import {
  FinancialPeriodControls,
  type FinancialPeriod,
} from "@/components/financial/financial-period-controls";
import { RevenueSection } from "@/components/financial/revenue-section";
import {
  fetchFinancialConfiguration,
  fetchFinancialDashboard,
  fetchFinancialOperationalAnalytics,
} from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import type {
  FinancialConfigurationDetail,
  FinancialDashboardDetail,
  FinancialOperationalAnalyticsDetail,
} from "@/lib/types";

type FinanceView = "dashboard" | "revenue";

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

function FinancialPageSkeleton() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-auto p-4 md:p-6">
      <div className="mx-auto w-full max-w-7xl space-y-5">
        <div className="h-14 animate-pulse rounded-xl bg-muted" />
        <div className="h-28 animate-pulse rounded-xl bg-muted" />
        <div className="h-52 animate-pulse rounded-xl bg-muted" />
      </div>
    </div>
  );
}

export default function FinanceiroPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState(initialFilters);
  const [configuration, setConfiguration] =
    useState<FinancialConfigurationDetail | null>(null);
  const [dashboard, setDashboard] =
    useState<FinancialDashboardDetail | null>(null);
  const [operationalAnalytics, setOperationalAnalytics] =
    useState<FinancialOperationalAnalyticsDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const activeView: FinanceView =
    searchParams.get("view") === "receita" ? "revenue" : "dashboard";

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
        const [configurationResult, dashboardResult, analyticsResult] = await Promise.all([
          fetchFinancialConfiguration(),
          fetchFinancialDashboard(initial.dateFrom, initial.dateTo),
          fetchFinancialOperationalAnalytics(initial.dateFrom, initial.dateTo),
        ]);
        if (!active) return;
        setConfiguration(configurationResult);
        setDashboard(dashboardResult);
        setOperationalAnalytics(analyticsResult);
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
      const [result, analyticsResult] = await Promise.all([
        fetchFinancialDashboard(
          nextFilters.dateFrom,
          nextFilters.dateTo,
          nextFilters.placeId ? [nextFilters.placeId] : []
        ),
        fetchFinancialOperationalAnalytics(nextFilters.dateFrom, nextFilters.dateTo),
      ]);
      setFilters(nextFilters);
      setDashboard(result);
      setOperationalAnalytics(analyticsResult);
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

  function selectView(view: FinanceView) {
    const params = new URLSearchParams(searchParams.toString());
    if (view === "revenue") {
      params.set("view", "receita");
    } else {
      params.delete("view");
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  if (error && (!configuration || !dashboard || !operationalAnalytics)) {
    return <div className="p-6 text-sm text-destructive">{error}</div>;
  }

  if (!configuration || !dashboard || !operationalAnalytics) {
    return <FinancialPageSkeleton />;
  }

  const views: {
    key: FinanceView;
    label: string;
    icon: typeof BarChart3;
  }[] = [
    { key: "dashboard", label: "Visão geral", icon: BarChart3 },
    { key: "revenue", label: "Realizado", icon: ReceiptText },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-auto p-4 md:p-6">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
              <CircleDollarSign className="size-5 text-primary" />
              Financeiro
            </h1>
            <p className="text-sm text-muted-foreground">
              Acompanhe receita, ocupação e capacidade.
            </p>
          </div>
          <Link
            href="/financeiro/simulador"
            className="inline-flex h-8 items-center rounded-lg border border-border px-3 text-sm font-medium transition-colors hover:bg-muted"
          >
            Abrir simulador
          </Link>
        </header>

        <FinancialPeriodControls
          period={{ dateFrom: filters.dateFrom, dateTo: filters.dateTo }}
          refreshing={refreshing}
          onApply={(period: FinancialPeriod) =>
            applyFilters({ ...period, placeId: filters.placeId })
          }
        />

        <nav
          className="grid w-full grid-cols-2 rounded-lg border bg-muted/30 p-1 sm:flex sm:w-fit"
          aria-label="Áreas do Financeiro"
        >
          {views.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              aria-current={activeView === key ? "page" : undefined}
              onClick={() => selectView(key)}
              className={`flex h-8 items-center justify-center gap-1.5 rounded-md px-3 text-sm transition-colors ${
                activeView === key
                  ? "bg-background font-medium shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </nav>

        {error && (
          <div
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            {error}
          </div>
        )}

        {activeView === "dashboard" ? (
          <FinancialDashboardSection
            dashboard={dashboard}
            dateFrom={filters.dateFrom}
            dateTo={filters.dateTo}
            placeId={filters.placeId}
            places={configuration.places}
            operationalAnalytics={operationalAnalytics}
            refreshing={refreshing}
            onPlaceChange={(placeId) =>
              applyFilters({ ...filters, placeId })
            }
          />
        ) : (
          <RevenueSection dateFrom={filters.dateFrom} dateTo={filters.dateTo} />
        )}
      </div>
    </div>
  );
}
