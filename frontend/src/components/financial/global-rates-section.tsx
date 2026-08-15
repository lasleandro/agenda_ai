"use client";

import { useState } from "react";
import { Info } from "lucide-react";
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { updateFinancialSettings } from "@/lib/api";
import {
  centsToRateInput,
  formatBrlFromCents,
  parseRateToCents,
} from "@/lib/financial-utils";
import type {
  CommercialStatus,
  FinancialSettingsDetail,
} from "@/lib/types";

function initialRates(settings: FinancialSettingsDetail): Record<number, string> {
  return Object.fromEntries(
    settings.rates.map((rate) => [
      rate.participant_count,
      centsToRateInput(rate.hourly_rate_cents),
    ])
  );
}

export function GlobalRatesSection({
  settings,
  onSaved,
}: {
  settings: FinancialSettingsDetail;
  onSaved: (settings: FinancialSettingsDetail) => void;
}) {
  const [defaultStatus, setDefaultStatus] = useState(
    settings.default_commercial_status
  );
  const [rates, setRates] = useState<Record<number, string>>(() =>
    initialRates(settings)
  );
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(
    null
  );

  async function handleSave() {
    let parsedRates;
    try {
      parsedRates = [1, 2, 3, 4].map((participantCount) => ({
        participant_count: participantCount,
        hourly_rate_cents: parseRateToCents(rates[participantCount] ?? ""),
      }));
    } catch (caught) {
      setNotice({
        text: caught instanceof Error ? caught.message : "Valor inválido",
        error: true,
      });
      return;
    }

    setSaving(true);
    setNotice({ text: "Configuração salva.", error: false });
    try {
      onSaved(
        await updateFinancialSettings({
          default_commercial_status: defaultStatus,
          rates: parsedRates,
        })
      );
    } catch (caught) {
      setDefaultStatus(settings.default_commercial_status);
      setRates(initialRates(settings));
      setNotice({
        text: caught instanceof Error ? caught.message : "Falha ao salvar configuração",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          Configuração global
          <Tooltip>
            <TooltipTrigger
              className="text-muted-foreground"
              aria-label="Como o valor por participante é cobrado"
            >
              <Info className="size-3.5" />
            </TooltipTrigger>
            <TooltipContent>
              O valor informado é por participante. Uma aula de 2 pessoas a
              R$ 180/h cobra R$ 180 de cada uma — R$ 360/h no total da aula.
            </TooltipContent>
          </Tooltip>
        </CardTitle>
        <CardDescription>
          Valores por participante. O total estimado da aula considera a quantidade
          de pessoas.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="max-w-xs space-y-1.5">
          <Label htmlFor="financial-default-status">Status padrão</Label>
          <select
            id="financial-default-status"
            value={defaultStatus}
            onChange={(event) =>
              setDefaultStatus(event.target.value as CommercialStatus)
            }
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          >
            <option value="active">Ativo</option>
            <option value="waiting">Em espera</option>
            <option value="paused">Pausado</option>
          </select>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[1, 2, 3, 4].map((participantCount) => {
            let parsed: number | null = null;
            try {
              parsed = parseRateToCents(rates[participantCount] ?? "");
            } catch {
              parsed = null;
            }
            return (
              <div
                key={participantCount}
                className="space-y-2 rounded-lg border border-border p-3"
              >
                <Label htmlFor={`global-rate-${participantCount}`}>
                  {participantCount === 1
                    ? "Aula individual"
                    : `${participantCount} participantes`}
                </Label>
                <Input
                  id={`global-rate-${participantCount}`}
                  inputMode="decimal"
                  value={rates[participantCount] ?? ""}
                  onChange={(event) =>
                    setRates((current) => ({
                      ...current,
                      [participantCount]: event.target.value,
                    }))
                  }
                  placeholder="R$/hora"
                />
                <p className="text-xs text-muted-foreground">
                  Total:{" "}
                  {parsed === null
                    ? "não definido"
                    : formatBrlFromCents(parsed * participantCount)}
                  /h
                </p>
              </div>
            );
          })}
        </div>
        {notice && (
          <p className={notice.error ? "text-sm text-destructive" : "text-sm text-emerald-600"}>
            {notice.text}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Salvando..." : "Salvar configuração"}
        </Button>
      </CardFooter>
    </Card>
  );
}
