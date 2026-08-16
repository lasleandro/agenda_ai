"use client";

import { useEffect, useState } from "react";
import { Check, Clock, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  dismissAppointmentCandidate,
  confirmAppointmentFromCandidate,
  fetchAppointmentCandidates,
  fulfillWaitlistFromCandidate,
} from "@/lib/api";
import { AddToWaitlistDialog } from "./add-to-waitlist-dialog";
import { ConfirmAppointmentCandidateDialog } from "./confirm-appointment-candidate-dialog";
import type { CandidateDetail, ContactSummary, Place, WaitlistEntry } from "@/lib/types";

const ACTION_LABELS: Record<string, string> = {
  create: "Possível novo agendamento",
  confirm: "Confirmação de aula",
  reschedule: "Possível remarcação",
  cancel: "Possível cancelamento",
  recurrence: "Possível horário fixo",
  waitlist_request: "Cliente sem horário disponível",
  none: "Sem ação",
};

function splitDateTime(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: "", time: "" };
  const [date, rest] = iso.split("T");
  return { date, time: (rest ?? "").slice(0, 5) };
}

function placeContext(candidate: CandidateDetail, places: Place[]): string | null {
  const placeName = candidate.resolved_place_id
    ? places.find((place) => place.id === candidate.resolved_place_id)?.name
    : null;
  if (candidate.place_source === "unique_stay") {
    return `Local definido pela permanência${placeName ? `: ${placeName}` : ""}.`;
  }
  if (candidate.place_source === "home_place_tiebreak") {
    return `Local definido entre permanências pelo local habitual${placeName ? `: ${placeName}` : ""}.`;
  }
  if (candidate.place_resolution === "ambiguous") {
    return "Há mais de uma permanência nesse horário. Escolha o local antes de confirmar.";
  }
  if (candidate.place_resolution === "uncovered") {
    return "Não há permanência cobrindo este horário. Escolha o local para registrar uma exceção.";
  }
  if (candidate.place_resolution === "invalid_place") {
    return "O local informado não pertence a este profissional.";
  }
  return null;
}

export function DetectedCandidatesTab({
  places,
  onWaitlistEntryCreated,
}: {
  places: Place[];
  onWaitlistEntryCreated: (entry: WaitlistEntry) => void;
}) {
  const [candidates, setCandidates] = useState<CandidateDetail[] | null>(null);
  const [waitlistCandidate, setWaitlistCandidate] = useState<CandidateDetail | null>(null);
  const [appointmentCandidate, setAppointmentCandidate] = useState<CandidateDetail | null>(null);
  const [notice, setNotice] = useState<{ message: string; error: boolean } | null>(null);

  useEffect(() => {
    fetchAppointmentCandidates("all")
      .then((res) => setCandidates(res.candidates))
      .catch((caught) => {
        setCandidates([]);
        setNotice({
          message: caught instanceof Error ? caught.message : "Não foi possível carregar os eventos detectados.",
          error: true,
        });
      });
  }, []);

  function dismiss(candidate: CandidateDetail) {
    setCandidates((current) => current?.filter((item) => item.id !== candidate.id) ?? null);
    void dismissAppointmentCandidate(candidate.id).catch((caught) => {
      setCandidates((current) => (current ? [...current, candidate] : [candidate]));
      setNotice({
        message: caught instanceof Error ? caught.message : "Não foi possível dispensar.",
        error: true,
      });
    });
  }

  function handleFulfillWaitlist(input: {
    desired_date: string;
    desired_start_time: string;
    desired_end_time: string;
    place_id?: string | null;
    note?: string | null;
  }) {
    if (!waitlistCandidate) return;
    const candidate = waitlistCandidate;
    setWaitlistCandidate(null);
    void fulfillWaitlistFromCandidate(candidate.id, input)
      .then((entry) => {
        setCandidates((current) => current?.filter((item) => item.id !== candidate.id) ?? null);
        onWaitlistEntryCreated(entry);
        setNotice({ message: `${entry.contact_name} adicionado(a) à fila de espera.`, error: false });
      })
      .catch((caught) => {
        setNotice({
          message: caught instanceof Error ? caught.message : "Não foi possível adicionar à fila.",
          error: true,
        });
      });
  }

  function confirmAppointment(input: {
    place_id: string | null;
    start_at: string | null;
    end_at: string | null;
    service: string | null;
  }) {
    if (!appointmentCandidate) return Promise.resolve();
    const candidate = appointmentCandidate;
    setAppointmentCandidate(null);
    setCandidates((current) => current?.filter((item) => item.id !== candidate.id) ?? null);
    return confirmAppointmentFromCandidate(candidate.id, input)
      .then(() => setNotice({ message: "Agendamento confirmado.", error: false }))
      .catch((caught) => {
        setCandidates((current) => (current ? [...current, candidate] : [candidate]));
        setNotice({
          message: caught instanceof Error ? caught.message : "Não foi possível confirmar.",
          error: true,
        });
        throw caught;
      });
  }

  const fakeContactForDialog: ContactSummary | null = waitlistCandidate
    ? {
        id: waitlistCandidate.contact_id ?? "",
        display_name: waitlistCandidate.contact_name ?? "Cliente",
        phone: null,
        level: null,
        home_place_id: null,
        home_place_name: null,
        makeup_credits_available: 0,
      }
    : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Eventos de agendamento detectados automaticamente nas conversas — revise e descarte, ou
        adicione à fila de espera quando aplicável.
      </p>

      {notice && (
        <p className={`text-sm ${notice.error ? "text-destructive" : "text-muted-foreground"}`}>
          {notice.message}
        </p>
      )}

      {candidates === null && <p className="text-sm text-muted-foreground">Carregando...</p>}

      {candidates !== null && candidates.length === 0 && (
        <p className="text-sm text-muted-foreground">Nenhum evento detectado no momento.</p>
      )}

      {candidates !== null && candidates.length > 0 && (
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
          {candidates.map((candidate) => {
            const { date, time: startTime } = splitDateTime(candidate.proposed_start_at);
            const { time: endTime } = splitDateTime(candidate.proposed_end_at);
            const candidatePlaceContext = placeContext(candidate, places);
            return (
              <div
                key={candidate.id}
                className="rounded-xl border border-border bg-card p-4 text-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-foreground">
                      {ACTION_LABELS[candidate.action] ?? candidate.action}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {candidate.contact_name ?? "Cliente não identificado"}
                      {date && ` · ${new Date(`${date}T12:00:00`).toLocaleDateString("pt-BR")}`}
                      {startTime && ` às ${startTime}`}
                      {endTime && `–${endTime}`}
                    </p>
                  </div>
                  {candidate.status === "detected" && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => dismiss(candidate)}
                      title="Dispensar"
                      aria-label="Dispensar"
                    >
                      <X />
                    </Button>
                  )}
                </div>

                {candidate.evidence.length > 0 && (
                  <div className="mt-2 space-y-0.5 border-l-2 border-border pl-2 text-xs text-muted-foreground">
                    {candidate.evidence.map((item) => (
                      <p key={item.message_id}>{item.text}</p>
                    ))}
                  </div>
                )}

                {candidate.ambiguities.length > 0 && (
                  <p className="mt-2 text-xs text-amber-700">
                    {candidate.ambiguities.map((a) => a.description).join(" · ")}
                  </p>
                )}

                {candidatePlaceContext && (
                  <p className="mt-2 text-xs text-muted-foreground">{candidatePlaceContext}</p>
                )}

                {candidate.status === "fulfilled" && candidate.resulting_appointment_id && (
                  <p className="mt-2 text-xs text-emerald-700">Autoexecutado</p>
                )}
                {candidate.escalation_delivery_status && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {candidate.escalation_delivery_status === "queued" && "Aguardando envio ao agente"}
                    {candidate.escalation_delivery_status === "needs_place_review" && "Aguardando escolha de local"}
                    {candidate.escalation_delivery_status === "sent" && "Confirmação enviada ao agente"}
                    {candidate.escalation_delivery_status === "failed" && "Falha ao enviar confirmação"}
                    {candidate.escalation_delivery_status === "expired" && "Confirmação expirada"}
                    {candidate.escalation_status === "executed" && " · Executado"}
                    {candidate.escalation_status === "rejected" && " · Recusado"}
                    {candidate.escalation_status === "expired" && " · Expirado"}
                    {candidate.escalation_status === "failed" && " · Falhou"}
                  </p>
                )}

                {candidate.status === "detected" && candidate.action === "waitlist_request" && candidate.contact_id && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={() => setWaitlistCandidate(candidate)}
                  >
                    <Clock />
                    Adicionar à fila de espera
                  </Button>
                )}

                {candidate.status === "detected" && candidate.operation === "create" && candidate.contact_id && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={() => setAppointmentCandidate(candidate)}
                  >
                    <Check />
                    Confirmar agendamento
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {waitlistCandidate && fakeContactForDialog && (
        <AddToWaitlistDialog
          contact={fakeContactForDialog}
          places={places}
          title="Confirmar entrada na fila de espera"
          description={`Revise o horário detectado para ${fakeContactForDialog.display_name} antes de adicionar à fila.`}
          initialDesiredDate={splitDateTime(waitlistCandidate.proposed_start_at).date}
          initialStartTime={splitDateTime(waitlistCandidate.proposed_start_at).time}
          initialEndTime={splitDateTime(waitlistCandidate.proposed_end_at).time}
          onOpenChange={(open) => {
            if (!open) setWaitlistCandidate(null);
          }}
          onAdd={handleFulfillWaitlist}
        />
      )}

      {appointmentCandidate && (
        <ConfirmAppointmentCandidateDialog
          candidate={appointmentCandidate}
          places={places}
          onOpenChange={(open) => {
            if (!open) setAppointmentCandidate(null);
          }}
          onConfirm={confirmAppointment}
        />
      )}
    </div>
  );
}
