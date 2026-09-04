"use client";

import { useState } from "react";
import { CircleDollarSign } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { confirmRevenueOccurrence } from "@/lib/api";
import { parseRateToCents } from "@/lib/financial-utils";
import type {
  AttendanceStatus,
  RevenueCandidateDetail,
  RevenueOccurrenceDetail,
  RevenueParticipantOutcomeInput,
} from "@/lib/types";

const STATUS_LABELS: Record<AttendanceStatus, string> = {
  attended: "Realizada",
  no_show: "Falta",
  cancelled: "Cancelada",
};

export function RevenueConfirmDialog({
  candidate,
  open,
  onOpenChange,
  onConfirmed,
}: {
  candidate: RevenueCandidateDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmed: (occurrence: RevenueOccurrenceDetail) => void;
}) {
  const isCourtesy = candidate.billing_type === "courtesy";
  const [outcomes, setOutcomes] = useState<RevenueParticipantOutcomeInput[]>(
    candidate.participants.map((participant) => ({
      contact_id: participant.contact_id,
      attendance_status: "attended",
      billable: !isCourtesy,
      non_billable_reason: isCourtesy ? "courtesy" : null,
    }))
  );
  const [adjustment, setAdjustment] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateStatus(contactId: string, status: AttendanceStatus) {
    setOutcomes((current) =>
      current.map((outcome) =>
        outcome.contact_id === contactId
          ? {
              ...outcome,
              attendance_status: status,
              billable: status === "attended" && !isCourtesy,
              non_billable_reason:
                status === "attended" && !isCourtesy
                  ? null
                  : isCourtesy
                    ? "courtesy"
                    : null,
            }
          : outcome
      )
    );
  }

  function updateBillable(contactId: string, billable: boolean) {
    setOutcomes((current) =>
      current.map((outcome) =>
        outcome.contact_id === contactId
          ? {
              ...outcome,
              billable,
              non_billable_reason: billable
                ? null
                : isCourtesy
                  ? "courtesy"
                  : null,
            }
          : outcome
      )
    );
  }

  async function confirm() {
    setError(null);
    setSaving(true);
    try {
      const adjustmentCents = parseRateToCents(
        adjustment.startsWith("-") ? adjustment.slice(1) : adjustment
      );
      const signedAdjustment =
        adjustment.startsWith("-")
          ? -(adjustmentCents ?? 0)
          : (adjustmentCents ?? 0);
      const occurrence = await confirmRevenueOccurrence({
        source_type: candidate.source_type,
        source_id: candidate.source_id,
        occurrence_date: candidate.occurrence_date,
        participant_outcomes: outcomes,
        adjustment_cents: signedAdjustment,
        note: note.trim() || null,
      });
      onConfirmed(occurrence);
      onOpenChange(false);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Não foi possível confirmar a receita. Tente novamente."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CircleDollarSign className="size-4 text-primary" />
            Confirmar ocorrência
          </DialogTitle>
          <DialogDescription>
            {candidate.source_label} ·{" "}
            {candidate.occurrence_date.split("-").reverse().join("/")} ·{" "}
            {candidate.place_name ?? "Sem local"}
            {isCourtesy && " · Cortesia"}
          </DialogDescription>
          {isCourtesy && (
            <p className="text-xs text-muted-foreground">
              Agendada como cortesia — participantes começam como não
              faturáveis, mas você pode marcar como faturável individualmente
              se necessário.
            </p>
          )}
        </DialogHeader>

        <div className="max-h-[55vh] space-y-3 overflow-y-auto">
          {candidate.participants.map((participant) => {
            const outcome = outcomes.find(
              (item) => item.contact_id === participant.contact_id
            );
            return (
              <div
                key={participant.contact_id}
                className="grid gap-3 rounded-lg border p-3 sm:grid-cols-[1fr_150px_auto] sm:items-end"
              >
                <div>
                  <p className="font-medium">{participant.contact_name}</p>
                  <p className="text-xs text-muted-foreground">
                    O preço será congelado ao confirmar.
                  </p>
                </div>
                <label className="grid gap-1 text-xs font-medium">
                  Resultado
                  <select
                    className="h-8 rounded-md border bg-background px-2 text-sm"
                    value={outcome?.attendance_status}
                    onChange={(event) =>
                      updateStatus(
                        participant.contact_id,
                        event.target.value as AttendanceStatus
                      )
                    }
                  >
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex h-8 items-center gap-2 text-xs font-medium">
                  <input
                    type="checkbox"
                    checked={outcome?.billable ?? false}
                    onChange={(event) =>
                      updateBillable(
                        participant.contact_id,
                        event.target.checked
                      )
                    }
                    className="accent-primary"
                  />
                  Faturável
                </label>
              </div>
            );
          })}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-xs font-medium">
            Ajuste total em R$
            <Input
              inputMode="decimal"
              placeholder="Ex.: -10,00 ou 15,00"
              value={adjustment}
              onChange={(event) => setAdjustment(event.target.value)}
            />
          </label>
          <label className="grid gap-1 text-xs font-medium">
            Observação
            <Input
              maxLength={1000}
              placeholder="Opcional"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancelar
          </Button>
          <Button type="button" onClick={confirm} disabled={saving}>
            {saving ? "Confirmando..." : "Confirmar receita"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
