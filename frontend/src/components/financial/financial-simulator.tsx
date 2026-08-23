"use client";

import { useState } from "react";
import { Calculator, Info, Pencil, Save, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  evaluateFinancialScenario,
  saveFinancialScenario,
} from "@/lib/api";
import {
  centsToRateInput,
  formatBrlFromCents,
  parseRateToCents,
} from "@/lib/financial-utils";
import type {
  FinancialConfigurationDetail,
  FinancialDashboardDetail,
  FinancialScenarioDetail,
  FinancialScenarioInput,
  FinancialScenarioMode,
  FinancialScenarioResult,
  FinancialTimeCategory,
} from "@/lib/types";
import { ScenarioResults } from "./scenario-results";
import { SimulatedAgenda } from "./simulated-agenda";

const MODE_OPTIONS: {
  value: FinancialScenarioMode;
  label: string;
  helper: string;
}[] = [
  {
    value: "observed_demand",
    label: "Mix da demanda observada",
    helper: "Repete a distribuição encontrada no período.",
  },
  {
    value: "all_individual",
    label: "Todas individuais",
    helper: "Simula cada horário com uma pessoa.",
  },
  {
    value: "full_groups",
    label: "Todos grupos de quatro",
    helper: "Simula todos os horários com quatro pessoas.",
  },
  {
    value: "individual_regular_groups_prime",
    label: "Individuais no regular, grupos no nobre",
    helper: "Reserva grupos de quatro para horários nobres.",
  },
  {
    value: "groups_regular_individual_prime",
    label: "Grupos no regular, individuais no nobre",
    helper: "Reserva aulas individuais para horários nobres.",
  },
  {
    value: "custom",
    label: "Mix personalizado",
    helper: "Você distribui o percentual entre os formatos.",
  },
];

function rateKey(category: FinancialTimeCategory, participantCount: number) {
  return `${category}-${participantCount}`;
}

export function FinancialSimulator({
  dashboard,
  configuration,
  dateFrom,
  dateTo,
  placeId,
  initialScenarios,
}: {
  dashboard: FinancialDashboardDetail;
  configuration: FinancialConfigurationDetail;
  dateFrom: string;
  dateTo: string;
  placeId: string;
  initialScenarios: FinancialScenarioDetail[];
}) {
  const observedMix = Object.fromEntries(
    dashboard.observed_participant_mix.map((item) => [
      item.participant_count,
      item.percentage,
    ])
  );
  const [name, setName] = useState("Cenário de capacidade");
  const [mode, setMode] =
    useState<FinancialScenarioMode>("observed_demand");
  const [occupancy, setOccupancy] = useState(100);
  const [mix, setMix] = useState<Record<number, number>>({
    1: observedMix[1] ?? 0,
    2: observedMix[2] ?? 0,
    3: observedMix[3] ?? 0,
    4: observedMix[4] ?? 0,
  });
  const [rateInputs, setRateInputs] = useState<Record<string, string>>({});
  const [editingRates, setEditingRates] = useState(false);
  const [result, setResult] = useState<FinancialScenarioResult | null>(null);
  const [scenarios, setScenarios] =
    useState<FinancialScenarioDetail[]>(initialScenarios);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [saving, setSaving] = useState(false);

  function configuredRate(
    category: FinancialTimeCategory,
    participantCount: number
  ) {
    if (placeId) {
      const matrix = configuration.places.find(
        (place) => place.place_id === placeId
      );
      const rate = matrix?.rates.find(
        (item) =>
          item.time_category === category &&
          item.participant_count === participantCount
      );
      if (rate) return rate.effective_hourly_rate_cents;
    }
    const defaultRate = configuration.default_rates.rates.find(
      (item) =>
        item.time_category === category &&
        item.participant_count === participantCount
    );
    return defaultRate?.effective_hourly_rate_cents ?? null;
  }

  function buildInput(): FinancialScenarioInput {
    const customMix = [1, 2, 3, 4].map((participantCount) => ({
      participant_count: participantCount,
      percentage: mix[participantCount] ?? 0,
    }));
    if (
      mode === "custom" &&
      Math.abs(
        customMix.reduce((total, item) => total + item.percentage, 0) - 100
      ) > 0.01
    ) {
      throw new Error("No mix personalizado, os percentuais devem somar 100%");
    }
    const rateOverrides = editingRates
      ? (
      ["regular", "prime"] as FinancialTimeCategory[]
    ).flatMap((category) =>
      [1, 2, 3, 4].flatMap((participantCount) => {
        const raw = rateInputs[rateKey(category, participantCount)] ?? "";
        const parsed = parseRateToCents(raw);
        return parsed === null
          ? []
          : [
              {
                time_category: category,
                participant_count: participantCount,
                hourly_rate_cents: parsed,
              },
            ];
      })
    )
      : [];
    return {
      name: name.trim() || "Cenário sem nome",
      date_from: dateFrom,
      date_to: dateTo,
      place_ids: placeId ? [placeId] : null,
      mode,
      occupancy_pct: occupancy,
      participant_mix: mode === "custom" ? customMix : null,
      rate_overrides: rateOverrides,
    };
  }

  async function evaluate() {
    setError(null);
    setEvaluating(true);
    try {
      setResult(await evaluateFinancialScenario(buildInput()));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Falha ao simular cenário"
      );
    } finally {
      setEvaluating(false);
    }
  }

  async function save() {
    setError(null);
    setSaving(true);
    let optimisticId: string | null = null;
    try {
      const input = buildInput();
      if (result) {
        optimisticId = `optimistic-${Date.now()}`;
        const optimistic: FinancialScenarioDetail = {
          id: optimisticId,
          name: input.name,
          input_snapshot: input,
          result_snapshot: result,
          created_at: new Date().toISOString(),
        };
        setScenarios((current) => [optimistic, ...current]);
      }
      const saved = await saveFinancialScenario(input);
      setResult(saved.result_snapshot);
      setScenarios((current) => [
        saved,
        ...current.filter((item) => item.id !== optimisticId),
      ]);
    } catch (caught) {
      if (optimisticId) {
        setScenarios((current) =>
          current.filter((item) => item.id !== optimisticId)
        );
      }
      setError(
        caught instanceof Error ? caught.message : "Falha ao salvar cenário"
      );
    } finally {
      setSaving(false);
    }
  }

  const selectedMode = MODE_OPTIONS.find((option) => option.value === mode);
  const mixTotal = Object.values(mix).reduce(
    (total, percentage) => total + percentage,
    0
  );

  function enableRateEditing() {
    setRateInputs(
      Object.fromEntries(
        (["regular", "prime"] as FinancialTimeCategory[]).flatMap((category) =>
          [1, 2, 3, 4].map((participantCount) => [
            rateKey(category, participantCount),
            centsToRateInput(configuredRate(category, participantCount)),
          ])
        )
      )
    );
    setEditingRates(true);
  }

  function resetRateEditing() {
    setRateInputs({});
    setEditingRates(false);
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SlidersHorizontal className="size-4 text-primary" />
            Premissas da simulação
          </CardTitle>
          <CardDescription>
            Ajuste as hipóteses abaixo sem alterar preços ou compromissos reais.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-5 xl:grid-cols-[0.9fr_1.4fr]">
            <div className="space-y-5">
            <label className="grid gap-1.5 text-xs font-medium">
              Nome do cenário
              <Input
                value={name}
                maxLength={120}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="grid gap-1.5 text-xs font-medium">
              Distribuição
              <select
                className="h-9 rounded-md border bg-background px-3 text-sm"
                value={mode}
                onChange={(event) =>
                  setMode(event.target.value as FinancialScenarioMode)
                }
              >
                {MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="font-normal text-muted-foreground">
                {selectedMode?.helper}
              </span>
            </label>

            {mode === "custom" && (
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-medium">
                  <span>Mix de formatos</span>
                  <span
                    className={
                      Math.abs(mixTotal - 100) < 0.01
                        ? "text-emerald-700"
                        : "text-destructive"
                    }
                  >
                    Total: {mixTotal.toFixed(1)}%
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[1, 2, 3, 4].map((participantCount) => (
                    <label
                      key={participantCount}
                      className="grid gap-1 text-xs text-muted-foreground"
                    >
                      {participantCount === 1
                        ? "Individual"
                        : `${participantCount} pessoas`}
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        step="0.1"
                        value={mix[participantCount]}
                        onChange={(event) =>
                          setMix((current) => ({
                            ...current,
                            [participantCount]: Number(event.target.value),
                          }))
                        }
                      />
                    </label>
                  ))}
                </div>
              </div>
            )}

            <label className="grid gap-2 text-xs font-medium">
              Ocupação desejada: {occupancy.toFixed(0)}%
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={occupancy}
                onChange={(event) => setOccupancy(Number(event.target.value))}
                className="accent-primary"
              />
            </label>

            <div className="rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
              Período: {dateFrom.split("-").reverse().join("/")} a{" "}
              {dateTo.split("-").reverse().join("/")}
              <br />
              Local:{" "}
              {placeId
                ? configuration.places.find(
                    (place) => place.place_id === placeId
                  )?.place_name
                : "todos os locais"}
            </div>
            </div>

            <section className="border-t pt-5 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="flex items-center gap-1.5 font-medium">
              Preços usados na simulação
              <Tooltip>
                <TooltipTrigger
                  className="text-muted-foreground"
                  aria-label="Como o valor por participante é cobrado"
                >
                  <Info className="size-3.5" />
                </TooltipTrigger>
                <TooltipContent>
                  O valor é por participante, não o total da aula. Uma aula
                  de 2 pessoas a R$ 180/h cobra R$ 180 de cada uma — R$ 360/h
                  no total.
                </TooltipContent>
              </Tooltip>
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Valores configurados para o recorte. Altere somente para testar outra regra.
                  </p>
                </div>
                {editingRates ? (
                  <Button variant="ghost" size="sm" onClick={resetRateEditing}>
                    Usar valores configurados
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" onClick={enableRateEditing}>
                    <Pencil className="size-3.5" />
                    Editar preços
                  </Button>
                )}
              </div>
              <div className="mt-4">
            <table className="w-full table-fixed text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="pb-2 font-medium">Formato</th>
                  <th className="pb-2 font-medium">Regular</th>
                  <th className="pb-2 font-medium">Nobre</th>
                </tr>
              </thead>
              <tbody>
                {[1, 2, 3, 4].map((participantCount) => (
                  <tr key={participantCount} className="border-b last:border-0">
                    <td className="py-3 font-medium">
                      {participantCount === 1
                        ? "Individual"
                        : `${participantCount} pessoas`}
                    </td>
                    {(["regular", "prime"] as FinancialTimeCategory[]).map(
                      (category) => {
                        const key = rateKey(category, participantCount);
                        const configured = centsToRateInput(
                          configuredRate(category, participantCount)
                        );
                        return (
                          <td key={category} className="py-3 pr-2 last:pr-0">
                            {editingRates ? (
                              <Input
                                inputMode="decimal"
                                value={rateInputs[key] ?? configured}
                                onChange={(event) =>
                                  setRateInputs((current) => ({
                                    ...current,
                                    [key]: event.target.value,
                                  }))
                                }
                                aria-label={`Preço ${category}, ${participantCount} pessoas`}
                              />
                            ) : (
                              <span className="text-muted-foreground">
                                R$ {configured || "não definido"}
                              </span>
                            )}
                          </td>
                        );
                      }
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
              </div>
            </section>
          </div>
            <div className="mt-5 flex flex-wrap gap-2 border-t pt-4">
              <Button onClick={evaluate} disabled={evaluating}>
                <Calculator className="size-4" />
                {evaluating ? "Calculando..." : "Simular"}
              </Button>
              <Button
                variant="outline"
                onClick={save}
                disabled={saving}
              >
                <Save className="size-4" />
                {saving ? "Salvando..." : "Salvar cenário"}
              </Button>
            </div>
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {result ? (
        <>
          <ScenarioResults result={result} />
          <SimulatedAgenda
            events={result.simulated_schedule}
            period={{ from: dateFrom, to: dateTo }}
          />
        </>
      ) : (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Ajuste as premissas e selecione Simular para comparar com a agenda
            atual.
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Cenários salvos</CardTitle>
          <CardDescription>
            Cada item preserva uma fotografia imutável das entradas e do
            resultado.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {scenarios.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhum cenário salvo.
            </p>
          ) : (
            <div className="divide-y">
              {scenarios.map((scenario) => (
                <div
                  key={scenario.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div>
                    <p className="font-medium">{scenario.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(scenario.created_at).toLocaleString("pt-BR")} ·{" "}
                      {scenario.input_snapshot.occupancy_pct}% de ocupação
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold">
                      {formatBrlFromCents(
                        scenario.result_snapshot.scenario
                          .projected_revenue_cents
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      projeção do cenário
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
