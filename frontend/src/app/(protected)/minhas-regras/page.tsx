"use client";

import { useEffect, useState } from "react";
import { Settings } from "lucide-react";
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

        <WorkJourneySection intervals={workJourney} onSaved={setWorkJourney} />
        <CancellationNoticeSection detail={notice} onSaved={setNotice} />
      </div>
    </div>
  );
}
