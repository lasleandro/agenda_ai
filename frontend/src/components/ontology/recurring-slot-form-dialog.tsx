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
import { createRecurringSlots, deleteRecurringSlot, updateRecurringSlot } from "@/lib/api";
import { DAY_LABELS } from "@/lib/ontology-utils";
import type { Place, RecurringSlot } from "@/lib/types";
import { SchedulerPlaceSelect } from "./scheduler-place-select";

const DAY_PRESETS = [
  { value: "every-day", label: "Todos os dias", days: [0, 1, 2, 3, 4, 5, 6] },
  { value: "weekdays", label: "Segunda a sexta", days: [0, 1, 2, 3, 4] },
  { value: "weekend", label: "Sábado e domingo", days: [5, 6] },
  { value: "monday-wednesday-friday", label: "Segunda, quarta e sexta", days: [0, 2, 4] },
  { value: "tuesday-thursday", label: "Terça e quinta", days: [1, 3] },
  { value: "specific", label: "Dia específico", days: null },
] as const;

/** Create/edit dialog for a place stay. */
export function RecurringSlotFormDialog({
  open,
  onOpenChange,
  slot,
  places,
  fixedPlaceId,
  onPlaceCreated,
  onSaved,
  onDeleted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slot?: RecurringSlot | null;
  places?: Place[];
  fixedPlaceId?: string;
  onPlaceCreated?: (place: Place) => void;
  onSaved: (slot: RecurringSlot) => void;
  onDeleted?: (slotId: string) => void;
}) {
  const [placeId, setPlaceId] = useState(slot?.place_id ?? fixedPlaceId ?? places?.[0]?.id ?? "");
  const [dayOfWeek, setDayOfWeek] = useState(slot?.day_of_week ?? 0);
  const [dayPreset, setDayPreset] = useState("specific");
  const [startTime, setStartTime] = useState(slot?.start_time?.slice(0, 5) ?? "08:00");
  const [endTime, setEndTime] = useState(slot?.end_time?.slice(0, 5) ?? "09:00");
  const [validFrom, setValidFrom] = useState(slot?.valid_from ?? "");
  const [validUntil, setValidUntil] = useState(slot?.valid_until ?? "");
  const [label, setLabel] = useState(slot?.label ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!placeId) {
      setError("Selecione um local");
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
      const selectedPreset = DAY_PRESETS.find((preset) => preset.value === dayPreset);
      const saved = slot
        ? await updateRecurringSlot(slot.id, {
            ...sharedPayload,
            day_of_week: dayOfWeek,
          })
        : (
            await createRecurringSlots({
              ...sharedPayload,
              days_of_week: selectedPreset?.days
                ? [...selectedPreset.days]
                : [dayOfWeek],
            })
          )[0];
      onSaved(saved);
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao salvar horário");
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
      setError(e instanceof Error ? e.message : "Falha ao remover horário");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{slot ? "Editar permanência" : "Nova permanência"}</DialogTitle>
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

          {!slot && (
            <div className="space-y-1.5">
              <Label htmlFor="slot-day-preset">Repetição</Label>
              <select
                id="slot-day-preset"
                value={dayPreset}
                onChange={(e) => setDayPreset(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              >
                {DAY_PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}
                  </option>
                ))}
              </select>
              {dayPreset !== "specific" && (
                <p className="text-xs text-muted-foreground">
                  Um horário será criado para cada dia selecionado.
                </p>
              )}
            </div>
          )}

          {(slot || dayPreset === "specific") && (
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
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="slot-end">Fim</Label>
              <Input
                id="slot-end"
                type="time"
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
                <Input
                  id="slot-valid-from"
                  type="date"
                  value={validFrom}
                  max={validUntil || undefined}
                  onChange={(e) => setValidFrom(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="slot-valid-until">Até</Label>
                <Input
                  id="slot-valid-until"
                  type="date"
                  value={validUntil}
                  min={validFrom || undefined}
                  onChange={(e) => setValidUntil(e.target.value)}
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
