"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ContactSummary, Place, WaitlistEntryInput } from "@/lib/types";

export function AddToWaitlistDialog({
  contact,
  places,
  onOpenChange,
  onAdd,
  initialDesiredDate,
  initialStartTime,
  initialEndTime,
  title,
  description,
}: {
  contact: ContactSummary;
  places: Place[];
  onOpenChange: (open: boolean) => void;
  onAdd: (input: WaitlistEntryInput) => void;
  /** Pre-fill from a passive-observer candidate ("YYYY-MM-DD"/"HH:MM") — the
   * instructor still reviews/completes before it becomes a real entry. */
  initialDesiredDate?: string;
  initialStartTime?: string;
  initialEndTime?: string;
  title?: string;
  description?: string;
}) {
  const [desiredDate, setDesiredDate] = useState(initialDesiredDate ?? "");
  const [startTime, setStartTime] = useState(initialStartTime ?? "");
  const [endTime, setEndTime] = useState(initialEndTime ?? "");
  const [placeId, setPlaceId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit() {
    if (!desiredDate || !startTime || !endTime) {
      setError("Informe data, horário de início e horário de término.");
      return;
    }
    if (endTime <= startTime) {
      setError("O horário de término deve ser após o início.");
      return;
    }
    onAdd({
      contact_id: contact.id,
      place_id: placeId || null,
      desired_date: desiredDate,
      desired_start_time: `${startTime}:00`,
      desired_end_time: `${endTime}:00`,
      note: note || null,
    });
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title ?? "Adicionar à fila de espera"}</DialogTitle>
          <DialogDescription>
            {description ??
              `Registre o horário que ${contact.display_name} gostaria de ter, para ser avisado quando abrir.`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Data desejada</label>
            <Input
              type="date"
              value={desiredDate}
              onChange={(e) => setDesiredDate(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Início</label>
              <Input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Término</label>
              <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Local (opcional)
            </label>
            <select
              value={placeId}
              onChange={(e) => setPlaceId(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="">Qualquer local</option>
              {places.map((place) => (
                <option key={place.id} value={place.id}>
                  {place.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Observação (opcional)
            </label>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Ex: prefere no período da tarde"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit}>Adicionar à fila</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
