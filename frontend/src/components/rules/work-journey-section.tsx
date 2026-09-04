"use client";

import { useState } from "react";
import { Copy, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { replaceWorkJourney } from "@/lib/api";
import { DAY_LABELS } from "@/lib/ontology-utils";
import type {
  WorkJourneyIntervalDetail,
  WorkJourneyIntervalInput,
} from "@/lib/types";

type DayDraft = {
  enabled: boolean;
  start: string;
  end: string;
  breaks: BreakDraft[];
};

type BreakDraft = {
  start: string;
  end: string;
};

function initialDays(
  intervals: WorkJourneyIntervalDetail[]
): Record<number, DayDraft> {
  return Object.fromEntries(
    DAY_LABELS.map((_, day) => {
      const work = intervals.find(
        (interval) =>
          interval.day_of_week === day && interval.interval_type === "work"
      );
      const breaks = intervals
        .filter(
          (interval) =>
            interval.day_of_week === day && interval.interval_type === "break"
        )
        .map((interval) => ({
          start: interval.start_time.slice(0, 5),
          end: interval.end_time.slice(0, 5),
        }));
      return [
        day,
        {
          enabled: Boolean(work),
          start: work?.start_time.slice(0, 5) ?? "08:00",
          end: work?.end_time.slice(0, 5) ?? "18:00",
          breaks,
        },
      ];
    })
  );
}

export function WorkJourneySection({
  intervals,
  onSaved,
}: {
  intervals: WorkJourneyIntervalDetail[];
  onSaved: (intervals: WorkJourneyIntervalDetail[]) => void;
}) {
  const [days, setDays] = useState<Record<number, DayDraft>>(() =>
    initialDays(intervals)
  );
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(
    null
  );
  const [copyFromDay, setCopyFromDay] = useState<number | null>(null);
  const [copyTargets, setCopyTargets] = useState<Set<number>>(new Set());

  function updateDay(day: number, update: Partial<DayDraft>) {
    setDays((current) => ({
      ...current,
      [day]: { ...current[day], ...update },
    }));
  }

  function addBreak(day: number) {
    updateDay(day, {
      breaks: [...days[day].breaks, { start: "12:00", end: "13:00" }],
    });
  }

  function updateBreak(day: number, index: number, update: Partial<BreakDraft>) {
    updateDay(day, {
      breaks: days[day].breaks.map((breakDraft, breakIndex) =>
        breakIndex === index ? { ...breakDraft, ...update } : breakDraft
      ),
    });
  }

  function removeBreak(day: number, index: number) {
    updateDay(day, {
      breaks: days[day].breaks.filter((_, breakIndex) => breakIndex !== index),
    });
  }

  function toggleCopyTarget(day: number) {
    setCopyTargets((current) => {
      const next = new Set(current);
      if (next.has(day)) {
        next.delete(day);
      } else {
        next.add(day);
      }
      return next;
    });
  }

  function applyCopy() {
    if (copyFromDay === null) return;
    const source = days[copyFromDay];
    setDays((current) => {
      const next = { ...current };
      for (const target of copyTargets) {
        next[target] = {
          enabled: true,
          start: source.start,
          end: source.end,
          breaks: source.breaks.map((breakDraft) => ({ ...breakDraft })),
        };
      }
      return next;
    });
    setCopyFromDay(null);
    setCopyTargets(new Set());
  }

  async function handleSave() {
    const payload: WorkJourneyIntervalInput[] = [];
    for (const day of Object.keys(days).map(Number)) {
      const draft = days[day];
      if (!draft.enabled) continue;
      if (!draft.start || !draft.end || draft.end <= draft.start) {
        setNotice({
          text: `Revise o horário de ${DAY_LABELS[day]}.`,
          error: true,
        });
        return;
      }
      payload.push({
        day_of_week: day,
        interval_type: "work",
        start_time: `${draft.start}:00`,
        end_time: `${draft.end}:00`,
      });
      const breaks = [...draft.breaks].sort((first, second) =>
        first.start.localeCompare(second.start)
      );
      for (const breakDraft of breaks) {
        if (
          !breakDraft.start ||
          !breakDraft.end ||
          breakDraft.end <= breakDraft.start ||
          breakDraft.start < draft.start ||
          breakDraft.end > draft.end
        ) {
          setNotice({
            text: `A pausa de ${DAY_LABELS[day]} deve ficar dentro da jornada.`,
            error: true,
          });
          return;
        }
      }
      if (breaks.some((breakDraft, index) => index > 0 && breakDraft.start < breaks[index - 1].end)) {
        setNotice({
          text: `As pausas de ${DAY_LABELS[day]} não podem se sobrepor.`,
          error: true,
        });
        return;
      }
      for (const breakDraft of breaks) {
        payload.push({
          day_of_week: day,
          interval_type: "break",
          start_time: `${breakDraft.start}:00`,
          end_time: `${breakDraft.end}:00`,
        });
      }
    }

    setSaving(true);
    setNotice({ text: "Jornada salva.", error: false });
    try {
      onSaved(await replaceWorkJourney(payload));
    } catch (caught) {
      setDays(initialDays(intervals));
      setNotice({
        text: caught instanceof Error ? caught.message : "Não foi possível salvar a jornada. Tente novamente.",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Jornada de trabalho</CardTitle>
        <CardDescription>
          Defina dias úteis, finais de semana e pausas. A jornada orienta
          recomendações de horário e cálculos de capacidade, sem bloquear
          agendamentos confirmados.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {DAY_LABELS.map((dayLabel, day) => {
          const draft = days[day];
          return (
            <div
              key={dayLabel}
              className={`rounded-lg border border-border p-3 ${
                day >= 5 ? "bg-muted/30" : ""
              }`}
            >
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex w-28 items-center gap-2 text-sm font-medium">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(event) =>
                      updateDay(day, { enabled: event.target.checked })
                    }
                    className="h-4 w-4 accent-primary"
                  />
                  {dayLabel}
                </label>
                <Input
                  type="time"
                  value={draft.start}
                  onChange={(event) => updateDay(day, { start: event.target.value })}
                  disabled={!draft.enabled}
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">até</span>
                <Input
                  type="time"
                  value={draft.end}
                  onChange={(event) => updateDay(day, { end: event.target.value })}
                  disabled={!draft.enabled}
                  className="w-32"
                />
                <Popover
                  open={copyFromDay === day}
                  onOpenChange={(open) => {
                    setCopyFromDay(open ? day : null);
                    setCopyTargets(new Set());
                  }}
                >
                  <PopoverTrigger
                    render={
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={!draft.enabled}
                        className="ml-auto"
                      >
                        <Copy />
                        Copiar para
                      </Button>
                    }
                  />
                  <PopoverContent>
                    <p className="text-sm font-medium">
                      Copiar horário de {dayLabel} para:
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {DAY_LABELS.map((targetLabel, targetDay) =>
                        targetDay === day ? null : (
                          <label
                            key={targetLabel}
                            className="flex items-center gap-2 text-sm"
                          >
                            <input
                              type="checkbox"
                              checked={copyTargets.has(targetDay)}
                              onChange={() => toggleCopyTarget(targetDay)}
                              className="h-4 w-4 accent-primary"
                            />
                            {targetLabel}
                          </label>
                        )
                      )}
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      onClick={applyCopy}
                      disabled={copyTargets.size === 0}
                    >
                      Aplicar
                    </Button>
                  </PopoverContent>
                </Popover>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => addBreak(day)}
                  disabled={!draft.enabled}
                >
                  <Plus />
                  Adicionar pausa
                </Button>
              </div>
              {draft.enabled && draft.breaks.length > 0 && (
                <div className="mt-3 space-y-2 pl-0 sm:pl-32">
                  {draft.breaks.map((breakDraft, index) => (
                    <div key={`${day}-${index}`} className="flex flex-wrap items-center gap-2">
                      <span className="w-14 text-xs text-muted-foreground">
                        Pausa {index + 1}
                      </span>
                      <Input
                        type="time"
                        value={breakDraft.start}
                        onChange={(event) =>
                          updateBreak(day, index, { start: event.target.value })
                        }
                        className="w-32"
                      />
                      <span className="text-sm text-muted-foreground">até</span>
                      <Input
                        type="time"
                        value={breakDraft.end}
                        onChange={(event) =>
                          updateBreak(day, index, { end: event.target.value })
                        }
                        className="w-32"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        aria-label={`Remover pausa ${index + 1} de ${dayLabel}`}
                        onClick={() => removeBreak(day, index)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {notice && (
          <p className={notice.error ? "text-sm text-destructive" : "text-sm text-emerald-600"}>
            {notice.text}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Salvando..." : "Salvar jornada"}
        </Button>
      </CardFooter>
    </Card>
  );
}
