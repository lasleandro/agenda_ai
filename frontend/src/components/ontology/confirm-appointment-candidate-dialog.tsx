"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SchedulerPlaceSelect } from "@/components/ontology/scheduler-place-select";
import type { CandidateDetail, Place } from "@/lib/types";

function localDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function ConfirmAppointmentCandidateDialog({
  candidate,
  places,
  onOpenChange,
  onConfirm,
}: {
  candidate: CandidateDetail;
  places: Place[];
  onOpenChange: (open: boolean) => void;
  onConfirm: (input: { place_id: string | null; start_at: string | null; end_at: string | null; service: string | null }) => Promise<void>;
}) {
  const [placeId, setPlaceId] = useState(candidate.suggested_place_id ?? "");
  const [startAt, setStartAt] = useState(localDateTime(candidate.proposed_start_at));
  const [endAt, setEndAt] = useState(localDateTime(candidate.proposed_end_at));
  const [service, setService] = useState(candidate.service ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSaving(true);
    setError(null);
    try {
      await onConfirm({
        place_id: placeId || null,
        start_at: startAt ? new Date(startAt).toISOString() : null,
        end_at: endAt ? new Date(endAt).toISOString() : null,
        service: service || null,
      });
      onOpenChange(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Não foi possível confirmar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Confirmar agendamento</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Revise os dados de {candidate.contact_name ?? "cliente"} antes de criar o agendamento.
          </p>
          <div className="space-y-1.5">
            <Label htmlFor="candidate-service">Serviço</Label>
            <Input id="candidate-service" value={service} onChange={(event) => setService(event.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="candidate-start">Início</Label>
              <Input id="candidate-start" type="datetime-local" value={startAt} onChange={(event) => setStartAt(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="candidate-end">Fim</Label>
              <Input id="candidate-end" type="datetime-local" value={endAt} onChange={(event) => setEndAt(event.target.value)} />
            </div>
          </div>
          <SchedulerPlaceSelect id="candidate-place" places={places} value={placeId} onChange={setPlaceId} />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Cancelar</Button>
          <Button type="button" onClick={submit} disabled={saving}>Confirmar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
