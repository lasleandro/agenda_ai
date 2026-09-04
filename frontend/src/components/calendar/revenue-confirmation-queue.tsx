"use client";

import { useEffect, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { RevenueConfirmDialog } from "@/components/financial/revenue-confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { fetchRevenueCandidates } from "@/lib/api";
import type {
  RevenueCandidateDetail,
  RevenueCandidateList,
  RevenueOccurrenceDetail,
} from "@/lib/types";

function formatDateTime(value: string) {
  return new Date(value).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function RevenueConfirmationQueue({
  dateFrom,
  dateTo,
}: {
  dateFrom: string;
  dateTo: string;
}) {
  const [candidateList, setCandidateList] =
    useState<RevenueCandidateList | null>(null);
  const [selectedCandidate, setSelectedCandidate] =
    useState<RevenueCandidateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchRevenueCandidates(dateFrom, dateTo, 200)
      .then((result) => {
        if (active) setCandidateList(result);
      })
      .catch((caught) => {
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Não foi possível carregar as confirmações. Tente novamente."
          );
        }
      });
    return () => {
      active = false;
    };
  }, [dateFrom, dateTo]);

  function confirmed(occurrence: RevenueOccurrenceDetail) {
    setCandidateList((current) =>
      current
        ? {
            ...current,
            candidates: current.candidates.map((candidate) =>
              candidate.source_type === occurrence.source_type &&
              candidate.source_id === occurrence.source_id &&
              candidate.occurrence_date === occurrence.occurrence_date
                ? { ...candidate, recognized_occurrence_id: occurrence.id }
                : candidate
            ),
          }
        : current
    );
  }

  if (error && !candidateList) {
    return <p className="text-sm text-destructive">{error}</p>;
  }
  if (!candidateList) {
    return <p className="text-sm text-muted-foreground">Carregando confirmações...</p>;
  }

  const pending = candidateList.candidates
    .filter(
      (candidate) =>
        candidate.recognized_occurrence_id === null && candidate.can_confirm
    )
    .sort((first, second) => second.ends_at.localeCompare(first.ends_at));

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Ocorrências aguardando confirmação</CardTitle>
          <CardDescription>
            Confirme o resultado de aulas já encerradas. Horários futuros não
            aparecem nesta lista.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <p className="mb-3 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
          {pending.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Nenhuma aula aguardando confirmação neste período.
            </p>
          ) : (
            <div className="divide-y">
              {pending.map((candidate) => (
                <div
                  key={`${candidate.source_type}-${candidate.source_id}-${candidate.occurrence_date}`}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{candidate.source_label}</p>
                      <Badge variant="outline">
                        {candidate.participants.length} pessoa(s)
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(candidate.starts_at)} · {candidate.place_name ?? "Sem local"} · {" "}
                      {candidate.participants
                        .map((participant) => participant.contact_name)
                        .join(", ")}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => setSelectedCandidate(candidate)}
                  >
                    <CheckCircle2 className="size-4" />
                    Confirmar ocorrência
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {selectedCandidate && (
        <RevenueConfirmDialog
          key={`${selectedCandidate.source_type}-${selectedCandidate.source_id}-${selectedCandidate.occurrence_date}`}
          candidate={selectedCandidate}
          open
          onOpenChange={(open) => {
            if (!open) setSelectedCandidate(null);
          }}
          onConfirmed={confirmed}
        />
      )}
    </>
  );
}
