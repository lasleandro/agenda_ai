"use client";

import { useEffect, useState } from "react";
import { CalendarClock, Settings, Undo2 } from "lucide-react";
import { CancellationNoticeSection } from "@/components/rules/cancellation-notice-section";
import { WorkJourneySection } from "@/components/rules/work-journey-section";
import { fetchCancellationNoticeHours, fetchWorkJourney } from "@/lib/api";
import type {
  CancellationNoticeHoursDetail,
  WorkJourneyIntervalDetail,
} from "@/lib/types";

export default function MinhasRegrasPage() {
  const [workJourney, setWorkJourney] = useState<
    WorkJourneyIntervalDetail[] | null
  >(null);
  const [notice, setNotice] = useState<CancellationNoticeHoursDetail | null>(
    null
  );
  const [activeTab, setActiveTab] = useState<"journey" | "makeup">("journey");
  const [error, setError] = useState<string | null>(null);

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
              : "Falha ao carregar Minhas Regras"
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

  if (error && (!workJourney || !notice)) {
    return <div className="p-6 text-sm text-destructive">{error}</div>;
  }

  if (!workJourney || !notice) {
    return <div className="p-6 text-sm text-muted-foreground">Carregando...</div>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-auto p-4 md:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <Settings className="h-5 w-5 text-primary" />
          Minhas Regras
        </h1>
        <p className="text-sm text-muted-foreground">
          Jornada de trabalho e regras de reposição, aplicadas independentemente
          do módulo financeiro.
        </p>
      </div>

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <div
          className="flex w-fit gap-1 rounded-lg border bg-muted/30 p-1"
          role="tablist"
          aria-label="Áreas de Minhas Regras"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "journey"}
            onClick={() => setActiveTab("journey")}
            className={`flex h-8 items-center gap-1.5 rounded-md px-3 text-sm transition-colors ${
              activeTab === "journey"
                ? "bg-background font-medium shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <CalendarClock className="size-4" />
            Jornada de trabalho
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "makeup"}
            onClick={() => setActiveTab("makeup")}
            className={`flex h-8 items-center gap-1.5 rounded-md px-3 text-sm transition-colors ${
              activeTab === "makeup"
                ? "bg-background font-medium shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Undo2 className="size-4" />
            Reposições
          </button>
        </div>

        {activeTab === "journey" && (
          <WorkJourneySection intervals={workJourney} onSaved={setWorkJourney} />
        )}
        {activeTab === "makeup" && (
          <CancellationNoticeSection detail={notice} onSaved={setNotice} />
        )}
      </div>
    </div>
  );
}
