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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { replaceDefaultRates, replacePlaceRates } from "@/lib/api";
import {
  centsToRateInput,
  formatBrlFromCents,
  parseRateToCents,
} from "@/lib/financial-utils";
import type {
  FinancialTimeCategory,
  PlaceRateMatrixDetail,
} from "@/lib/types";

function ruleKey(category: FinancialTimeCategory, participantCount: number): string {
  return `${category}-${participantCount}`;
}

function initialDraft(
  matrix: Pick<PlaceRateMatrixDetail, "rates">
): Record<string, string> {
  return Object.fromEntries(
    matrix.rates.map((rate) => [
      ruleKey(rate.time_category, rate.participant_count),
      centsToRateInput(rate.hourly_rate_cents),
    ])
  );
}

function RatesEditor({
  matrix,
  onSave,
  savedMessage,
  valueLabel,
}: {
  matrix: Pick<PlaceRateMatrixDetail, "rates">;
  onSave: (rates: {
    time_category: FinancialTimeCategory;
    participant_count: number;
    hourly_rate_cents: number | null;
  }[]) => Promise<void>;
  savedMessage: string;
  valueLabel: string;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    initialDraft(matrix)
  );
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(
    null
  );

  async function handleSave() {
    try {
      const rates = (["regular", "prime"] as const).flatMap((category) =>
        [1, 2, 3, 4].map((participantCount) => ({
          time_category: category,
          participant_count: participantCount,
          hourly_rate_cents: parseRateToCents(
            draft[ruleKey(category, participantCount)] ?? ""
          ),
        }))
      );
      setSaving(true);
      await onSave(rates);
      setNotice({ text: savedMessage, error: false });
    } catch (caught) {
      setDraft(initialDraft(matrix));
      setNotice({
          text: caught instanceof Error ? caught.message : "Não foi possível salvar os valores. Tente novamente.",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <p className="text-xs text-muted-foreground sm:hidden">
        Deslize para ver todos os valores.
      </p>
      <div
        className="overflow-x-auto rounded-lg border border-border"
        role="region"
        aria-label="Valores por período e formato"
        tabIndex={0}
      >
        <div className="grid min-w-[620px] grid-cols-[160px_repeat(4,1fr)]">
          <div className="flex items-center gap-1.5 bg-muted/40 p-3 text-xs font-medium">
            Período
            <Tooltip>
              <TooltipTrigger
                className="text-muted-foreground"
                aria-label="Como o valor por participante é cobrado"
              >
                <Info className="size-3.5" />
              </TooltipTrigger>
              <TooltipContent>
                O valor de cada coluna é por participante, não o total da
                aula. Uma aula de 2 pessoas a R$ 180/h cobra R$ 180 de cada
                uma — R$ 360/h no total.
              </TooltipContent>
            </Tooltip>
          </div>
          {[1, 2, 3, 4].map((count) => (
            <div key={count} className="bg-muted/40 p-3 text-xs font-medium">
              {count === 1 ? "Individual" : `${count} pessoas`}
            </div>
          ))}
          {(["regular", "prime"] as const).map((category) => (
            <div key={category} className="contents">
              <div className="border-t border-border p-3 text-sm font-medium">
                {category === "regular" ? "Horário regular" : "Horário nobre"}
              </div>
              {[1, 2, 3, 4].map((count) => {
                const rate = matrix.rates.find(
                  (item) =>
                    item.time_category === category &&
                    item.participant_count === count
                );
                const key = ruleKey(category, count);
                const hasOwnValue = Boolean(draft[key]?.trim());
                const caption = hasOwnValue
                  ? valueLabel
                  : rate?.effective_hourly_rate_cents != null
                    ? `Valor global definido: ${formatBrlFromCents(
                        rate.effective_hourly_rate_cents
                      )}`
                    : null;
                return (
                  <div key={key} className="space-y-1 border-t border-border p-2">
                    <Input
                      inputMode="decimal"
                      value={draft[key] ?? ""}
                      onChange={(event) =>
                        setDraft((current) => ({
                          ...current,
                          [key]: event.target.value,
                        }))
                      }
                      placeholder={
                        rate?.effective_hourly_rate_cents === null
                          ? "Não definido"
                          : centsToRateInput(rate?.effective_hourly_rate_cents ?? null)
                      }
                    />
                    {caption && (
                      <p className="text-[11px] text-muted-foreground">{caption}</p>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      {notice && (
        <p className={notice.error ? "text-sm text-destructive" : "text-sm text-emerald-600"}>
          {notice.text}
        </p>
      )}
      <CardFooter className="-mx-4 -mb-4 justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Salvando..." : savedMessage}
        </Button>
      </CardFooter>
    </>
  );
}

export function PlaceRateEditor({
  matrix,
  onSaved,
}: {
  matrix: PlaceRateMatrixDetail;
  onSaved: (matrix: PlaceRateMatrixDetail) => void;
}) {
  return (
    <RatesEditor
      matrix={matrix}
      savedMessage="Salvar valores do local"
      valueLabel="Valor do local"
      onSave={async (rates) => onSaved(await replacePlaceRates(matrix.place_id as string, rates))}
    />
  );
}

export function DefaultRatesCard({
  matrix,
  onSaved,
}: {
  matrix: PlaceRateMatrixDetail;
  onSaved: (matrix: PlaceRateMatrixDetail) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Valores padrão</CardTitle>
        <CardDescription>
          Valores por participante aplicados a compromissos sem local definido. Cada
          local pode substituí-los na sua própria página, em &quot;Meus Locais&quot;.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <RatesEditor
          matrix={matrix}
          savedMessage="Salvar valores padrão"
          valueLabel="Valor padrão"
          onSave={async (rates) => onSaved(await replaceDefaultRates(rates))}
        />
      </CardContent>
    </Card>
  );
}
