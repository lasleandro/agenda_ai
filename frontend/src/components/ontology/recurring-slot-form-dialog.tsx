"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BrazilianDatePicker } from "@/components/ui/brazilian-date-picker";
import { createRecurringSlots, deleteRecurringSlot, updateRecurringSlot } from "@/lib/api";
import { DAY_LABELS } from "@/lib/ontology-utils";
import type { Place, RecurringSlot } from "@/lib/types";
import { SchedulerPlaceSelect } from "./scheduler-place-select";

/** Create/edit dialog for a place stay. */
export function RecurringSlotFormDialog({
  open,
  onOpenChange,
  slot,
  duplicateSlot,
  places,
  fixedPlaceId,
  onPlaceCreated,
  onSaved,
  onDeleted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slot?: RecurringSlot | null;
  duplicateSlot?: RecurringSlot | null;
  places?: Place[];
  fixedPlaceId?: string;
  onPlaceCreated?: (place: Place) => void;
  onSaved: (slot: RecurringSlot) => void;
  onDeleted?: (slotId: string) => void;
}) {
  const initialSlot = slot ?? duplicateSlot;
  const [placeId, setPlaceId] = useState(initialSlot?.place_id ?? fixedPlaceId ?? places?.[0]?.id ?? "");
  const [dayOfWeek, setDayOfWeek] = useState(initialSlot?.day_of_week ?? 0);
  const [selectedDays, setSelectedDays] = useState<number[]>([initialSlot?.day_of_week ?? 0]);
  const [startTime, setStartTime] = useState(initialSlot?.start_time?.slice(0, 5) ?? "08:00");
  const [endTime, setEndTime] = useState(initialSlot?.end_time?.slice(0, 5) ?? "09:00");
  const [validFrom, setValidFrom] = useState(initialSlot?.valid_from ?? "");
  const [validUntil, setValidUntil] = useState(initialSlot?.valid_until ?? "");
  const [label, setLabel] = useState(initialSlot?.label ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!placeId) {
      setError("Selecione um local");
      return;
    }
    if (!slot && selectedDays.length === 0) {
      setError("Selecione pelo menos um dia da semana");
      return;
    }
    if (validFrom && validUntil && validUntil < validFrom) {
      setError("A data final deve ser igual ou posterior à data inicial");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const sharedPayload = {
        place_id: placeId,
        start_time: `${startTime}:00`,
        end_time: `${endTime}:00`,
        label: label.trim() || null,
        slot_kind: "availability" as const,
        class_type: "individual" as const,
        group_name: null,
        level: null,
        max_participants: 1,
        valid_from: validFrom || null,
        valid_until: validUntil || null,
      };
      const saved = slot
        ? await updateRecurringSlot(slot.id, {
            ...sharedPayload,
            day_of_week: dayOfWeek,
          })
        : (
            await createRecurringSlots({
              ...sharedPayload,
              days_of_week: selectedDays,
            })
          )[0];
      onSaved(saved);
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível salvar o horário. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!slot) return;
    setSaving(true);
    try {
      await deleteRecurringSlot(slot.id);
      onDeleted?.(slot.id);
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível remover o horário. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {slot ? "Editar permanência" : duplicateSlot ? "Duplicar permanência" : "Nova permanência"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {places && (
            <SchedulerPlaceSelect
              id="slot-place"
              value={placeId}
              places={places}
              onChange={setPlaceId}
              onPlaceCreated={onPlaceCreated}
            />
          )}

          {!slot ? (
            <div className="space-y-1.5">
              <Label>Dias da semana</Label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {DAY_LABELS.map((day, index) => (
                  <label
                    key={day}
                    className="flex items-center gap-2 rounded-md border border-input px-3 py-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={selectedDays.includes(index)}
                      onChange={() =>
                        setSelectedDays((current) =>
                          current.includes(index)
                            ? current.filter((value) => value !== index)
                            : [...current, index].sort((first, second) => first - second)
                        )
                      }
                    />
                    {day}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Um horário será criado para cada dia selecionado.
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="slot-day">Dia da semana</Label>
              <select
                id="slot-day"
                value={dayOfWeek}
                onChange={(e) => setDayOfWeek(Number(e.target.value))}
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              >
                {DAY_LABELS.map((d, i) => (
                  <option key={d} value={i}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="slot-start">Início</Label>
              <Input
                id="slot-start"
                type="time"
                lang="pt-BR"
                step={60}
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="slot-end">Fim</Label>
              <Input
                id="slot-end"
                type="time"
                lang="pt-BR"
                step={60}
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
              />
            </div>
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Vigência (opcional)</legend>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="slot-valid-from">De</Label>
                <BrazilianDatePicker
                  id="slot-valid-from"
                  value={validFrom}
                  max={validUntil || undefined}
                  onChange={setValidFrom}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="slot-valid-until">Até</Label>
                <BrazilianDatePicker
                  id="slot-valid-until"
                  value={validUntil}
                  min={validFrom || undefined}
                  onChange={setValidUntil}
                />
              </div>
            </div>
          </fieldset>

          <div className="space-y-1.5">
            <Label htmlFor="slot-label">Identificação (opcional)</Label>
            <Input
              id="slot-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Ex: Quadra 2"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter className="justify-between sm:justify-between">
          {slot && (
            <Button variant="destructive" onClick={handleDelete} disabled={saving}>
              Remover
            </Button>
          )}
          <div className="flex gap-2 ml-auto">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "Salvando..." : "Salvar"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
