"use client";

import { useState } from "react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

const WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

function parseDate(value: string): Date | null {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

function dateValue(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

export function BrazilianDatePicker({
  id,
  value,
  min,
  max,
  onChange,
}: {
  id: string;
  value: string;
  min?: string;
  max?: string;
  onChange: (value: string) => void;
}) {
  const selectedDate = parseDate(value);
  const [open, setOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(selectedDate ?? new Date());
  const calendarDays = eachDayOfInterval({
    start: startOfWeek(startOfMonth(visibleMonth), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(visibleMonth), { weekStartsOn: 1 }),
  });

  function setPopoverOpen(nextOpen: boolean) {
    if (nextOpen) setVisibleMonth(selectedDate ?? new Date());
    setOpen(nextOpen);
  }

  function selectDate(date: Date) {
    onChange(dateValue(date));
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={setPopoverOpen}>
      <PopoverTrigger
        id={id}
        className={cn(
          "flex h-8 w-full items-center justify-between rounded-lg border border-input bg-transparent px-2.5 text-left text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          !selectedDate && "text-muted-foreground"
        )}
      >
        {selectedDate ? format(selectedDate, "dd/MM/yyyy", { locale: ptBR }) : "Selecionar data"}
        <CalendarDays className="size-4 text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent className="w-72 gap-3 p-3" align="start">
        <div className="flex items-center justify-between">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Mês anterior"
            onClick={() => setVisibleMonth((month) => subMonths(month, 1))}
          >
            <ChevronLeft />
          </Button>
          <p className="text-sm font-medium capitalize">
            {format(visibleMonth, "MMMM 'de' yyyy", { locale: ptBR })}
          </p>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Próximo mês"
            onClick={() => setVisibleMonth((month) => addMonths(month, 1))}
          >
            <ChevronRight />
          </Button>
        </div>
        <div className="grid grid-cols-7 gap-1 text-center">
          {WEEKDAY_LABELS.map((weekday) => (
            <span key={weekday} className="py-1 text-xs font-medium text-muted-foreground">
              {weekday}
            </span>
          ))}
          {calendarDays.map((date) => {
            const valueForDate = dateValue(date);
            const disabled = Boolean((min && valueForDate < min) || (max && valueForDate > max));
            const selected = Boolean(selectedDate && isSameDay(date, selectedDate));
            return (
              <button
                key={valueForDate}
                type="button"
                disabled={disabled}
                aria-pressed={selected}
                onClick={() => selectDate(date)}
                className={cn(
                  "size-8 rounded-md text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-35",
                  !isSameMonth(date, visibleMonth) && "text-muted-foreground",
                  selected && "bg-primary text-primary-foreground hover:bg-primary"
                )}
              >
                {format(date, "d")}
              </button>
            );
          })}
        </div>
        {value && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="self-start"
            onClick={() => {
              onChange("");
              setOpen(false);
            }}
          >
            Limpar data
          </Button>
        )}
      </PopoverContent>
    </Popover>
  );
}
