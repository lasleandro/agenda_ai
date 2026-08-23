"use client";

import { useState, type FormEvent } from "react";
import { CalendarRange } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface FinancialPeriod {
  dateFrom: string;
  dateTo: string;
}

type PeriodPreset = { label: string; period: FinancialPeriod };

function dateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function rangeFromToday(days: number, direction: "past" | "future"): FinancialPeriod {
  const today = new Date();
  const other = new Date(today);
  other.setDate(other.getDate() + (direction === "past" ? -(days - 1) : days - 1));
  return direction === "past"
    ? { dateFrom: dateInputValue(other), dateTo: dateInputValue(today) }
    : { dateFrom: dateInputValue(today), dateTo: dateInputValue(other) };
}

function monthRange(offset: number): FinancialPeriod {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth() + offset, 1);
  const end = new Date(today.getFullYear(), today.getMonth() + offset + 1, 0);
  return { dateFrom: dateInputValue(start), dateTo: dateInputValue(end) };
}

function formatPeriod(period: FinancialPeriod) {
  return `${period.dateFrom.split("-").reverse().join("/")} – ${period.dateTo
    .split("-")
    .reverse()
    .join("/")}`;
}

function matches(period: FinancialPeriod, candidate: FinancialPeriod) {
  return period.dateFrom === candidate.dateFrom && period.dateTo === candidate.dateTo;
}

export function FinancialPeriodControls({
  period,
  refreshing,
  onApply,
}: {
  period: FinancialPeriod;
  refreshing: boolean;
  onApply: (period: FinancialPeriod) => void;
}) {
  const presets: PeriodPreset[] = [
    { label: "Últimos 30 dias", period: rangeFromToday(30, "past") },
    { label: "Últimos 15 dias", period: rangeFromToday(15, "past") },
    { label: "Próximos 15 dias", period: rangeFromToday(15, "future") },
    { label: "Próximos 30 dias", period: rangeFromToday(30, "future") },
    { label: "Último mês fechado", period: monthRange(-1) },
    { label: "Este mês", period: monthRange(0) },
    { label: "Próximo mês", period: monthRange(1) },
  ];
  const isPreset = presets.some((preset) => matches(period, preset.period));
  const [showCustom, setShowCustom] = useState(!isPreset);

  return (
    <section className="space-y-2" aria-label="Período de análise">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/20 p-2">
        <span className="px-1 text-sm font-medium">Período</span>
        <div className="flex flex-wrap gap-1" aria-label="Atalhos de período">
          {presets.map((preset) => {
            const active = matches(period, preset.period);
            return (
              <Button
                key={preset.label}
                type="button"
                variant={active ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={active}
                disabled={refreshing}
                onClick={() => {
                  setShowCustom(false);
                  onApply(preset.period);
                }}
              >
                {preset.label}
              </Button>
            );
          })}
          <Button
            type="button"
            variant={showCustom ? "secondary" : "ghost"}
            size="sm"
            aria-expanded={showCustom}
            disabled={refreshing}
            onClick={() => setShowCustom((visible) => !visible)}
          >
            Personalizado
          </Button>
        </div>
        <span className="ml-auto px-1 text-xs text-muted-foreground">
          {formatPeriod(period)}
        </span>
      </div>
      {showCustom && (
        <FinancialPeriodForm
          key={`${period.dateFrom}-${period.dateTo}`}
          period={period}
          refreshing={refreshing}
          onApply={(nextPeriod) => {
            onApply(nextPeriod);
            setShowCustom(false);
          }}
        />
      )}
    </section>
  );
}

function FinancialPeriodForm({
  period,
  refreshing,
  onApply,
}: {
  period: FinancialPeriod;
  refreshing: boolean;
  onApply: (period: FinancialPeriod) => void;
}) {
  const [draft, setDraft] = useState(period);
  const invalidRange = draft.dateTo < draft.dateFrom;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!invalidRange) onApply(draft);
  }

  return (
    <form className="flex flex-wrap items-end gap-2 px-1" onSubmit={submit}>
      <label className="grid gap-1 text-xs font-medium">
        De
        <input className="h-8 rounded-md border bg-background px-2 text-sm" type="date" value={draft.dateFrom} required disabled={refreshing} onChange={(event) => setDraft((current) => ({ ...current, dateFrom: event.target.value }))} />
      </label>
      <label className="grid gap-1 text-xs font-medium">
        Até
        <input className="h-8 rounded-md border bg-background px-2 text-sm" type="date" value={draft.dateTo} required disabled={refreshing} onChange={(event) => setDraft((current) => ({ ...current, dateTo: event.target.value }))} />
      </label>
      <Button type="submit" size="sm" disabled={refreshing || invalidRange}>
        <CalendarRange className="size-3.5" />
        Aplicar
      </Button>
      {invalidRange && <p className="text-xs text-destructive">A data final deve ser posterior à inicial.</p>}
    </form>
  );
}
