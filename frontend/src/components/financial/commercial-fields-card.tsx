"use client";

import { useState } from "react";
import { CircleDollarSign } from "lucide-react";
import { Badge } from "@/components/ui/badge";
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
import { Label } from "@/components/ui/label";
import {
  centsToRateInput,
  formatBrlFromCents,
  parseRateToCents,
} from "@/lib/financial-utils";
import type {
  CommercialOverrideInput,
  CommercialStatus,
  EffectiveCommercialValues,
  FinancialValueSource,
} from "@/lib/types";

const STATUS_LABELS: Record<CommercialStatus, string> = {
  active: "Ativo",
  waiting: "Em espera",
  paused: "Pausado",
};

const SOURCE_LABELS: Record<FinancialValueSource, string> = {
  customer: "Próprio do cliente",
  group: "Definido no grupo",
  tenant: "Padrão da conta",
  unset: "Não definido",
};

export function commercialStatusLabel(status: CommercialStatus): string {
  return STATUS_LABELS[status];
}

export function financialSourceLabel(source: FinancialValueSource): string {
  return SOURCE_LABELS[source];
}

export function CommercialFieldsCard({
  values,
  title = "Comercial",
  description,
  onSave,
}: {
  values: EffectiveCommercialValues;
  title?: string;
  description: string;
  onSave: (input: CommercialOverrideInput) => Promise<void>;
}) {
  const [status, setStatus] = useState(values.commercial_status ?? "");
  const [rate, setRate] = useState(centsToRateInput(values.hourly_rate_cents));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    let hourlyRateCents: number | null;
    try {
      hourlyRateCents = parseRateToCents(rate);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Valor inválido");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await onSave({
        commercial_status: (status || null) as CommercialStatus | null,
        hourly_rate_cents: hourlyRateCents,
      });
    } catch {
      // The parent restores its previous optimistic state and provides context.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CircleDollarSign className="h-4 w-4 text-muted-foreground" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="commercial-status">Status</Label>
            <select
              id="commercial-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              disabled={saving}
              className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
            >
              <option value="">Usar valor herdado</option>
              <option value="active">Ativo</option>
              <option value="waiting">Em espera</option>
              <option value="paused">Pausado</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="commercial-hourly-rate">R$/hora por participante</Label>
            <Input
              id="commercial-hourly-rate"
              inputMode="decimal"
              value={rate}
              onChange={(event) => setRate(event.target.value)}
              disabled={saving}
              placeholder="Usar valor herdado"
            />
          </div>
        </div>

        <div className="grid gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs sm:grid-cols-2">
          <div>
            <p className="text-muted-foreground">Status efetivo</p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {STATUS_LABELS[values.effective_commercial_status]}
              </span>
              <Badge variant="outline">
                {SOURCE_LABELS[values.commercial_status_source]}
              </Badge>
            </div>
          </div>
          <div>
            <p className="text-muted-foreground">Valor efetivo</p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {formatBrlFromCents(values.effective_hourly_rate_cents)}/h
              </span>
              <Badge variant="outline">{SOURCE_LABELS[values.hourly_rate_source]}</Badge>
            </div>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
      <CardFooter className="justify-end">
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? "Salvando..." : "Salvar comercial"}
        </Button>
      </CardFooter>
    </Card>
  );
}
