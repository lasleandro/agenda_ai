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
import { replacePlaceRates } from "@/lib/api";
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

function initialDraft(matrix: PlaceRateMatrixDetail): Record<string, string> {
  return Object.fromEntries(
    matrix.rates.map((rate) => [
      ruleKey(rate.time_category, rate.participant_count),
      centsToRateInput(rate.hourly_rate_cents),
    ])
  );
}

export function PlaceRateEditor({
  matrix,
  onSaved,
}: {
  matrix: PlaceRateMatrixDetail;
  onSaved: (matrix: PlaceRateMatrixDetail) => void;
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
      setNotice({ text: "Valores do local salvos.", error: false });
      onSaved(await replacePlaceRates(matrix.place_id, rates));
    } catch (caught) {
      setDraft(initialDraft(matrix));
      setNotice({
        text: caught instanceof Error ? caught.message : "Falha ao salvar local",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-border">
        <div className="grid min-w-[620px] grid-cols-[160px_repeat(4,1fr)]">
          <div className="bg-muted/40 p-3 text-xs font-medium">Período</div>
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
                    <p className="text-[11px] text-muted-foreground">
                      {rate?.hourly_rate_cents === null
                        ? `Herda ${formatBrlFromCents(
                            rate.effective_hourly_rate_cents
                          )}`
                        : "Valor do local"}
                    </p>
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
          {saving ? "Salvando..." : "Salvar valores do local"}
        </Button>
      </CardFooter>
    </>
  );
}

export function PlaceRatesSection({
  places,
  onSaved,
}: {
  places: PlaceRateMatrixDetail[];
  onSaved: (matrix: PlaceRateMatrixDetail) => void;
}) {
  const [selectedPlaceId, setSelectedPlaceId] = useState(places[0]?.place_id ?? "");
  const selected = places.find((place) => place.place_id === selectedPlaceId) ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Valores por local</CardTitle>
        <CardDescription>
          Campos vazios herdam a tabela global. Regular e nobre são independentes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {places.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Cadastre um local para configurar valores específicos.
          </p>
        ) : (
          <>
            <select
              value={selectedPlaceId}
              onChange={(event) => setSelectedPlaceId(event.target.value)}
              className="h-9 w-full max-w-sm rounded-md border border-input bg-transparent px-3 text-sm"
            >
              {places.map((place) => (
                <option key={place.place_id} value={place.place_id}>
                  {place.place_name}
                </option>
              ))}
            </select>
            {selected && (
              <PlaceRateEditor
                key={selected.place_id}
                matrix={selected}
                onSaved={onSaved}
              />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
