"use client";

import { useState } from "react";
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
import { Label } from "@/components/ui/label";
import { createRecurringGroup } from "@/lib/api";
import {
  CONTACT_LEVEL_LABELS,
  DAY_LABELS,
} from "@/lib/ontology-utils";
import { CONTACT_LEVELS } from "@/lib/types";
import type { ContactSummary, Place, RecurringSlot } from "@/lib/types";
import { SchedulerPlaceSelect } from "./scheduler-place-select";

function toPythonDay(dateValue: string): number {
  const jsDay = new Date(`${dateValue}T12:00:00`).getDay();
  return jsDay === 0 ? 6 : jsDay - 1;
}

export function RecurringGroupDialog({
  open,
  onOpenChange,
  contacts,
  places,
  onPlaceCreated,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contacts: ContactSummary[];
  places: Place[];
  onPlaceCreated: (place: Place) => void;
  onCreated: (slot: RecurringSlot) => void;
}) {
  const [placeId, setPlaceId] = useState("");
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [startTime, setStartTime] = useState("08:00");
  const [endTime, setEndTime] = useState("09:00");
  const [label, setLabel] = useState("");
  const [level, setLevel] = useState("beginner");
  const [isRecurring, setIsRecurring] = useState(true);
  const [scheduledDate, setScheduledDate] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [maxParticipants, setMaxParticipants] = useState(4);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!placeId) {
      setError("Cadastre ou selecione um local");
      return;
    }
    if (endTime <= startTime) {
      setError("O horário final deve ser posterior ao inicial");
      return;
    }
    if (contacts.length > maxParticipants) {
      setError("A capacidade deve comportar todos os clientes selecionados");
      return;
    }
    if (!isRecurring && !scheduledDate) {
      setError("Informe a data do grupo esporádico");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const slot = await createRecurringGroup({
        place_id: placeId,
        day_of_week: isRecurring ? dayOfWeek : toPythonDay(scheduledDate),
        start_time: `${startTime}:00`,
        end_time: `${endTime}:00`,
        label: label.trim() || null,
        level,
        max_participants: maxParticipants,
        contact_ids: contacts.map((contact) => contact.id),
        recurrence_type: isRecurring ? "weekly" : "once",
        scheduled_date: isRecurring ? null : scheduledDate,
      });
      onCreated(slot);
      onOpenChange(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Falha ao criar grupo");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Criar grupo</DialogTitle>
          <DialogDescription>
            {contacts.length} clientes selecionados. Defina quando o grupo acontecerá.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <SchedulerPlaceSelect
            id="group-place"
            value={placeId}
            places={places}
            onChange={setPlaceId}
            onPlaceCreated={onPlaceCreated}
          />

          <label className="flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-2">
            <span>
              <span className="block text-sm font-medium">Repetir semanalmente</span>
              <span className="block text-xs text-muted-foreground">
                Desative para criar um grupo em uma única data.
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

          {isRecurring ? (
            <div className="space-y-1.5">
              <Label htmlFor="group-day">Dia da semana</Label>
              <select
                id="group-day"
                value={dayOfWeek}
                onChange={(event) => setDayOfWeek(Number(event.target.value))}
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              >
                {DAY_LABELS.map((day, index) => (
                  <option key={day} value={index}>
                    {day}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="group-date">Data</Label>
              <Input
                id="group-date"
                type="date"
                value={scheduledDate}
                onChange={(event) => setScheduledDate(event.target.value)}
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="group-start">Início</Label>
              <Input
                id="group-start"
                type="time"
                value={startTime}
                onChange={(event) => setStartTime(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="group-end">Fim</Label>
              <Input
                id="group-end"
                type="time"
                value={endTime}
                onChange={(event) => setEndTime(event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="group-level">Nível do grupo</Label>
            <select
              id="group-level"
              value={level}
              onChange={(event) => setLevel(event.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
            >
              {CONTACT_LEVELS.map((groupLevel) => (
                <option key={groupLevel} value={groupLevel}>
                  {CONTACT_LEVEL_LABELS[groupLevel]}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="group-label">Nome (opcional)</Label>
              <Input
                id="group-label"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="Ex: Turma iniciante"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="group-capacity">Máx. alunos</Label>
              <Input
                id="group-capacity"
                type="number"
                min={Math.max(1, contacts.length)}
                max={4}
                value={maxParticipants}
                onChange={(event) => setMaxParticipants(Number(event.target.value))}
              />
            </div>
          </div>

          <div className="rounded-lg border border-border bg-muted/40 px-3 py-2">
            <p className="text-xs font-medium">Participantes</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {contacts.map((contact) => contact.display_name).join(", ")}
            </p>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Criando..." : "Criar grupo"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
