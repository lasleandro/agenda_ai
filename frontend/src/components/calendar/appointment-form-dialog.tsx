"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SchedulerPlaceSelect } from "@/components/ontology/scheduler-place-select";
import type {
  AppointmentCreateInput,
  ContactSummary,
  Place,
} from "@/lib/types";

function formatSelection(start: Date, end: Date): string {
  const date = start.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });
  const time = (value: Date) =>
    value.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time(start)}–${time(end)}`;
}

export function AppointmentFormDialog({
  open,
  onOpenChange,
  start,
  end,
  suggestedPlaceId,
  contacts,
  places,
  onPlaceCreated,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  start: Date;
  end: Date;
  suggestedPlaceId: string | null;
  contacts: ContactSummary[];
  places: Place[];
  onPlaceCreated: (place: Place) => void;
  onCreate: (input: AppointmentCreateInput) => Promise<void>;
}) {
  const [contactId, setContactId] = useState("");
  const [placeId, setPlaceId] = useState(suggestedPlaceId ?? places[0]?.id ?? "");
  const [service, setService] = useState("Aula de tênis");
  const [isRecurring, setIsRecurring] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!contactId || !placeId || !service.trim()) {
      setError("Selecione o cliente, o local e informe o serviço");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await onCreate({
        contact_id: contactId,
        place_id: placeId,
        service: service.trim(),
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        is_recurring: isRecurring,
      });
      onOpenChange(false);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Falha ao criar agendamento"
      );
    } finally {
      setSaving(false);
    }
  }

  const canBook = contacts.length > 0 && places.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Novo agendamento</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="rounded-lg bg-muted px-3 py-2 text-sm capitalize text-muted-foreground">
            {formatSelection(start, end)}
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="booking-contact">Cliente</Label>
            <select
              id="booking-contact"
              value={contactId}
              onChange={(event) => setContactId(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
            >
              <option value="">Selecione um cliente</option>
              {contacts.map((contact) => (
                <option key={contact.id} value={contact.id}>
                  {contact.display_name}
                </option>
              ))}
            </select>
          </div>

          <SchedulerPlaceSelect
            id="booking-place"
            value={placeId}
            places={places}
            onChange={setPlaceId}
            onPlaceCreated={onPlaceCreated}
          />

          <div className="space-y-1.5">
            <Label htmlFor="booking-service">Serviço</Label>
            <Input
              id="booking-service"
              value={service}
              onChange={(event) => setService(event.target.value)}
            />
          </div>

          <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-2">
            <span>
              <span className="block text-sm font-medium">Repetir semanalmente</span>
              <span className="block text-xs text-muted-foreground">
                O agendamento aparecerá neste dia e horário toda semana.
              </span>
            </span>
            <input
              type="checkbox"
              role="switch"
              checked={isRecurring}
              onChange={(event) => setIsRecurring(event.target.checked)}
              className="h-4 w-4 accent-primary"
            />
          </label>

          {!canBook && (
            <p className="text-sm text-muted-foreground">
              Cadastre ao menos um cliente e um local antes de criar um agendamento.
            </p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving || !canBook}>
            {saving ? "Salvando..." : "Agendar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
