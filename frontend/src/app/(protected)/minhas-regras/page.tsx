"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  CalendarClock,
  CircleDollarSign,
  MapPin,
  Settings,
  Sun,
  Undo2,
} from "lucide-react";
import { CancellationNoticeSection } from "@/components/rules/cancellation-notice-section";
import { WorkJourneySection } from "@/components/rules/work-journey-section";
import { GlobalRatesSection } from "@/components/financial/global-rates-section";
import { DefaultRatesCard } from "@/components/financial/place-rates-section";
import { PlacesSection } from "@/components/ontology/places-section";
import { PrimeTimeSection } from "@/components/financial/prime-time-section";
import {
  fetchCancellationNoticeHours,
  fetchFinancialConfiguration,
  fetchFinancialSettings,
  fetchWorkJourney,
} from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import type {
  CancellationNoticeHoursDetail,
  FinancialConfigurationDetail,
  FinancialSettingsDetail,
  PlaceRateMatrixDetail,
  WorkJourneyIntervalDetail,
} from "@/lib/types";

type ConfigurationTab =
  | "journey"
  | "makeup"
  | "global-rates"
  | "prime-time"
  | "places";

const TAB_KEYS: ConfigurationTab[] = [
  "journey",
  "makeup",
  "global-rates",
  "prime-time",
  "places",
];

export default function MinhasRegrasPage() {
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") as ConfigurationTab | null;
  const [workJourney, setWorkJourney] = useState<
    WorkJourneyIntervalDetail[] | null
  >(null);
  const [notice, setNotice] = useState<CancellationNoticeHoursDetail | null>(
    null
  );
  const [financialEnabled, setFinancialEnabled] = useState<boolean | null>(null);
  const [financialSettings, setFinancialSettings] =
    useState<FinancialSettingsDetail | null>(null);
  const [financialConfiguration, setFinancialConfiguration] =
    useState<FinancialConfigurationDetail | null>(null);
  const [activeTab, setActiveTab] = useState<ConfigurationTab>(
    requestedTab && TAB_KEYS.includes(requestedTab) ? requestedTab : "journey"
  );
  const [error, setError] = useState<string | null>(null);
  const [financialError, setFinancialError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([fetchWorkJourney(), fetchCancellationNoticeHours()])
      .then(([journeyResult, noticeResult]) => {
        if (!active) return;
        setWorkJourney(journeyResult);
        setNotice(noticeResult);
      })
      .catch((caught) => {
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Não foi possível carregar Minha Operação. Tente novamente."
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadFinancialConfiguration() {
      try {
        const user = await fetchSession();
        const enabled = sessionHasFeature(user, "commercial_financials");
        if (!active) return;
        setFinancialEnabled(enabled);
        if (!enabled) return;

        const [settingsResult, configurationResult] = await Promise.all([
          fetchFinancialSettings(),
          fetchFinancialConfiguration(),
        ]);
        if (!active) return;
        setFinancialSettings(settingsResult);
        setFinancialConfiguration(configurationResult);
      } catch (caught) {
        if (active) {
          setFinancialError(
            caught instanceof Error
              ? caught.message
              : "Não foi possível carregar as configurações financeiras. Tente novamente."
          );
        }
      }
    }

    void loadFinancialConfiguration();
    return () => {
      active = false;
    };
  }, []);

  function updateDefaultRates(matrix: PlaceRateMatrixDetail) {
    setFinancialConfiguration((current) =>
      current ? { ...current, default_rates: matrix } : current
    );
  }

  if (error && (!workJourney || !notice)) {
    return <div className="p-6 text-sm text-destructive">{error}</div>;
  }

  if (!workJourney || !notice) {
    return <div className="p-6 text-sm text-muted-foreground">Carregando...</div>;
  }

  const tabs: {
    key: ConfigurationTab;
    label: string;
    icon: typeof Settings;
  }[] = [
    { key: "journey", label: "Jornada de trabalho", icon: CalendarClock },
    { key: "makeup", label: "Reposições", icon: Undo2 },
    ...(financialEnabled
      ? [
          { key: "global-rates" as const, label: "Valores globais", icon: CircleDollarSign },
          { key: "prime-time" as const, label: "Horários nobres", icon: Sun },
        ]
      : []),
    { key: "places", label: "Meus Locais", icon: MapPin },
  ];

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-5 overflow-auto p-4 md:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <Settings className="h-5 w-5 text-primary" />
          Minha Operação
        </h1>
        <p className="text-sm text-muted-foreground">
          Defina regras operacionais, locais de atendimento e, quando disponível,
          parâmetros financeiros da sua operação.
        </p>
      </div>

      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div
          className="min-w-0 overflow-x-auto"
          role="tablist"
          aria-label="Áreas de Minha Operação"
        >
          <div className="flex w-max gap-1 rounded-lg border bg-muted/30 p-1">
            {tabs.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={activeTab === key}
                onClick={() => setActiveTab(key)}
                className={`flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-sm transition-colors ${
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
        </div>

        {activeTab === "journey" && (
          <WorkJourneySection intervals={workJourney} onSaved={setWorkJourney} />
        )}
        {activeTab === "makeup" && (
          <CancellationNoticeSection detail={notice} onSaved={setNotice} />
        )}
        {activeTab === "global-rates" && (
          <FinancialTabState error={financialError}>
            {financialSettings && financialConfiguration && (
              <div className="flex flex-col gap-5">
                <GlobalRatesSection
                  settings={financialSettings}
                  onSaved={setFinancialSettings}
                />
                <DefaultRatesCard
                  matrix={financialConfiguration.default_rates}
                  onSaved={updateDefaultRates}
                />
              </div>
            )}
          </FinancialTabState>
        )}
        {activeTab === "prime-time" && (
          <FinancialTabState error={financialError}>
            {financialConfiguration && (
              <PrimeTimeSection
                windows={financialConfiguration.prime_time_windows}
                onSaved={(windows) =>
                  setFinancialConfiguration((current) =>
                    current ? { ...current, prime_time_windows: windows } : current
                  )
                }
              />
            )}
          </FinancialTabState>
        )}
        {activeTab === "places" && <PlacesSection />}
      </div>
    </div>
  );
}

function FinancialTabState({
  children,
  error,
}: {
  children: React.ReactNode;
  error: string | null;
}) {
  if (error) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (!children) {
    return <div className="text-sm text-muted-foreground">Carregando...</div>;
  }
  return <>{children}</>;
}
