"use client";

import { useState } from "react";
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
  breakEnabled: boolean;
  breakStart: string;
  breakEnd: string;
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
      const breakInterval = intervals.find(
        (interval) =>
          interval.day_of_week === day && interval.interval_type === "break"
      );
      return [
        day,
        {
          enabled: Boolean(work),
          start: work?.start_time.slice(0, 5) ?? "08:00",
          end: work?.end_time.slice(0, 5) ?? "18:00",
          breakEnabled: Boolean(breakInterval),
          breakStart: breakInterval?.start_time.slice(0, 5) ?? "12:00",
          breakEnd: breakInterval?.end_time.slice(0, 5) ?? "13:00",
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

  function updateDay(day: number, update: Partial<DayDraft>) {
    setDays((current) => ({
      ...current,
      [day]: { ...current[day], ...update },
    }));
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
      if (draft.breakEnabled) {
        if (
          !draft.breakStart ||
          !draft.breakEnd ||
          draft.breakEnd <= draft.breakStart ||
          draft.breakStart < draft.start ||
          draft.breakEnd > draft.end
        ) {
          setNotice({
            text: `A pausa de ${DAY_LABELS[day]} deve ficar dentro da jornada.`,
            error: true,
          });
          return;
        }
        payload.push({
          day_of_week: day,
          interval_type: "break",
          start_time: `${draft.breakStart}:00`,
          end_time: `${draft.breakEnd}:00`,
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
        text: caught instanceof Error ? caught.message : "Falha ao salvar jornada",
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
          Defina dias úteis, finais de semana e pausas. A jornada alimentará os
          cálculos de capacidade.
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
                <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={draft.breakEnabled}
                    onChange={(event) =>
                      updateDay(day, { breakEnabled: event.target.checked })
                    }
                    disabled={!draft.enabled}
                    className="h-4 w-4 accent-primary"
                  />
                  Pausa
                </label>
              </div>
              {draft.enabled && draft.breakEnabled && (
                <div className="mt-3 flex flex-wrap items-center gap-2 pl-0 sm:pl-32">
                  <span className="text-xs text-muted-foreground">Pausa</span>
                  <Input
                    type="time"
                    value={draft.breakStart}
                    onChange={(event) =>
                      updateDay(day, { breakStart: event.target.value })
                    }
                    className="w-32"
                  />
                  <span className="text-sm text-muted-foreground">até</span>
                  <Input
                    type="time"
                    value={draft.breakEnd}
                    onChange={(event) =>
                      updateDay(day, { breakEnd: event.target.value })
                    }
                    className="w-32"
                  />
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
