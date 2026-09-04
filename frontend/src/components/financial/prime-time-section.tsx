"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
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
import { replacePrimeTimeWindows } from "@/lib/api";
import { DAY_LABELS } from "@/lib/ontology-utils";
import type { PrimeTimeWindowDetail } from "@/lib/types";

type PrimeDraft = {
  key: string;
  days_of_week: number[];
  start_time: string;
  end_time: string;
};

function toDrafts(windows: PrimeTimeWindowDetail[]): PrimeDraft[] {
  return windows.map((window, index) => ({
    key: window.id ?? `default-${index}`,
    days_of_week: window.days_of_week,
    start_time: window.start_time.slice(0, 5),
    end_time: window.end_time.slice(0, 5),
  }));
}

export function PrimeTimeSection({
  windows,
  onSaved,
}: {
  windows: PrimeTimeWindowDetail[];
  onSaved: (windows: PrimeTimeWindowDetail[]) => void;
}) {
  const [drafts, setDrafts] = useState<PrimeDraft[]>(() => toDrafts(windows));
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(
    null
  );

  function updateDraft(key: string, update: Partial<PrimeDraft>) {
    setDrafts((current) =>
      current.map((draft) => (draft.key === key ? { ...draft, ...update } : draft))
    );
  }

  async function handleSave() {
    const invalid = drafts.find(
      (draft) =>
        draft.days_of_week.length === 0 ||
        !draft.start_time ||
        !draft.end_time ||
        draft.end_time <= draft.start_time
    );
    if (invalid) {
      setNotice({
        text: "Cada faixa precisa de dias e de um horário final posterior ao inicial.",
        error: true,
      });
      return;
    }

    setSaving(true);
    setNotice({ text: "Horários nobres salvos.", error: false });
    try {
      const updated = await replacePrimeTimeWindows(
        drafts.map((draft) => ({
          days_of_week: draft.days_of_week,
          start_time: `${draft.start_time}:00`,
          end_time: `${draft.end_time}:00`,
        }))
      );
      onSaved(updated);
    } catch (caught) {
      setDrafts(toDrafts(windows));
      setNotice({
        text: caught instanceof Error ? caught.message : "Não foi possível salvar os horários. Tente novamente.",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Horários nobres</CardTitle>
        <CardDescription>
          Os padrões iniciais são 05:00–08:00 e 18:00–21:00. As faixas não podem
          se sobrepor no mesmo dia.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {drafts.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nenhum horário nobre configurado.
          </p>
        )}
        {drafts.map((draft) => (
          <div key={draft.key} className="rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="time"
                value={draft.start_time}
                onChange={(event) =>
                  updateDraft(draft.key, { start_time: event.target.value })
                }
                className="w-32"
              />
              <span className="text-sm text-muted-foreground">até</span>
              <Input
                type="time"
                value={draft.end_time}
                onChange={(event) =>
                  updateDraft(draft.key, { end_time: event.target.value })
                }
                className="w-32"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() =>
                  setDrafts((current) =>
                    current.filter((item) => item.key !== draft.key)
                  )
                }
                aria-label="Remover faixa"
                className="ml-auto"
              >
                <Trash2 />
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {DAY_LABELS.map((day, dayIndex) => {
                const selected = draft.days_of_week.includes(dayIndex);
                return (
                  <button
                    key={day}
                    type="button"
                    aria-pressed={selected}
                    onClick={() =>
                      updateDraft(draft.key, {
                        days_of_week: selected
                          ? draft.days_of_week.filter((value) => value !== dayIndex)
                          : [...draft.days_of_week, dayIndex].sort(),
                      })
                    }
                    className={`rounded-full border px-2 py-1 text-xs ${
                      selected
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground"
                    }`}
                  >
                    {day.slice(0, 3)}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            setDrafts((current) => [
              ...current,
              {
                key: crypto.randomUUID(),
                days_of_week: [0, 1, 2, 3, 4],
                start_time: "08:00",
                end_time: "09:00",
              },
            ])
          }
        >
          <Plus />
          Adicionar faixa
        </Button>
        {notice && (
          <p className={notice.error ? "text-sm text-destructive" : "text-sm text-emerald-600"}>
            {notice.text}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Salvando..." : "Salvar horários nobres"}
        </Button>
      </CardFooter>
    </Card>
  );
}
