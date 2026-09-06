"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Calculator,
  History,
  Info,
  Save,
  SlidersHorizontal,
} from "lucide-react";
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  evaluateFinancialScenario,
  saveFinancialScenario,
} from "@/lib/api";
import { centsToRateInput } from "@/lib/financial-utils";
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

const ESTIMATED_CAPACITY_MODE = "estimated_when_unconfigured" as const;

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

export function FinancialSimulator({
  dashboard,
  configuration,
  dateFrom,
  dateTo,
  placeId,
  onLocationChange,
  locationBusy,
  initialScenarios,
}: {
  dashboard: FinancialDashboardDetail;
  configuration: FinancialConfigurationDetail;
  dateFrom: string;
  dateTo: string;
  placeId: string;
  onLocationChange: (placeId: string) => void;
  locationBusy: boolean;
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
  const [result, setResult] = useState<FinancialScenarioResult | null>(null);
  const [scenarios, setScenarios] =
    useState<FinancialScenarioDetail[]>(initialScenarios);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scenariosOpen, setScenariosOpen] = useState(false);

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
    return {
      name: name.trim() || "Cenário sem nome",
      date_from: dateFrom,
      date_to: dateTo,
      place_ids: placeId ? [placeId] : null,
      capacity_mode: ESTIMATED_CAPACITY_MODE,
      mode,
      occupancy_pct: occupancy,
      participant_mix: mode === "custom" ? customMix : null,
      rate_overrides: [],
    };
  }

  async function evaluate() {
    setError(null);
    setEvaluating(true);
    try {
      setResult(await evaluateFinancialScenario(buildInput()));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Não foi possível simular o cenário. Tente novamente."
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
        caught instanceof Error ? caught.message : "Não foi possível salvar o cenário. Tente novamente."
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

  function loadScenario(scenario: FinancialScenarioDetail) {
    const input = scenario.input_snapshot;
    setName(input.name);
    setMode(input.mode);
    setOccupancy(input.occupancy_pct);
    setMix({
      1: input.participant_mix?.find((item) => item.participant_count === 1)
        ?.percentage ?? 0,
      2: input.participant_mix?.find((item) => item.participant_count === 2)
        ?.percentage ?? 0,
      3: input.participant_mix?.find((item) => item.participant_count === 3)
        ?.percentage ?? 0,
      4: input.participant_mix?.find((item) => item.participant_count === 4)
        ?.percentage ?? 0,
    });
    setResult(scenario.result_snapshot);
    setError(null);
    setScenariosOpen(false);
  }

  return (
    <div className="space-y-5">
      {dashboard.capacity_source.mode === "estimated_default" && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="space-y-2 p-4 text-sm text-amber-950 dark:text-amber-100">
            <p className="font-medium">Jornada estimada</p>
            <p>
              Você ainda não configurou sua jornada de trabalho. Para uma
              projeção personalizada, configure-a em Configurações → Jornada
              de trabalho.
            </p>
            {placeId ? (
              <p>
                A estimativa genérica não pode ser atribuída a um local
                específico. Selecione todos os locais ou configure sua jornada
                para projetar este local.
              </p>
            ) : (
              <p>
                Enquanto isso, esta simulação considera 8 horas por dia, de
                segunda-feira a sábado (48 horas por semana), avaliadas pela
                tarifa regular.
              </p>
            )}
            <Link
              href={dashboard.capacity_source.configuration_path ?? "/minhas-regras"}
              className="inline-flex h-8 items-center rounded-md border border-amber-700/30 px-3 text-xs font-medium transition-colors hover:bg-amber-500/10"
            >
              Configurar jornada
            </Link>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SlidersHorizontal className="size-4 text-primary" />
            Premissas da simulação
          </CardTitle>
          <CardDescription>
            Ajuste as premissas abaixo sem alterar preços ou compromissos reais.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5 text-xs font-medium">
              Período
              <p className="flex h-9 items-center rounded-md border bg-muted/50 px-3 text-sm font-normal text-muted-foreground">
                {dateFrom.split("-").reverse().join("/")} –{" "}
                {dateTo.split("-").reverse().join("/")}
              </p>
              <span className="font-normal text-muted-foreground">
                O simulador projeta sempre um mês.
              </span>
            </div>
            <label className="grid gap-1.5 text-xs font-medium">
              Local do cenário
              <select
                className="h-9 rounded-md border bg-background px-3 text-sm"
                value={placeId}
                disabled={locationBusy}
                onChange={(event) => onLocationChange(event.target.value)}
              >
                <option value="">Todos os locais</option>
                {configuration.places.map((place) => (
                  <option key={place.place_id ?? ""} value={place.place_id ?? ""}>
                    {place.place_name}
                  </option>
                ))}
              </select>
              <span className="font-normal text-muted-foreground">
                Afeta apenas a simulação; sua agenda não será alterada.
              </span>
            </label>
          </div>
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

            </div>

            <section className="border-t pt-5 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
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
              {placeId ? (
                <>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Preços configurados para este local. Para alterá-los, use{" "}
                    <Link
                      href="/minhas-regras"
                      className="font-medium underline underline-offset-2"
                    >
                      Minhas Regras
                    </Link>
                    .
                  </p>
                  <table className="mt-4 w-full table-fixed text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="pb-2 font-medium">Formato</th>
                        <th className="pb-2 font-medium">Regular</th>
                        <th className="pb-2 font-medium">Nobre</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[1, 2, 3, 4].map((participantCount) => (
                        <tr
                          key={participantCount}
                          className="border-b last:border-0"
                        >
                          <td className="py-3 font-medium">
                            {participantCount === 1
                              ? "Individual"
                              : `${participantCount} pessoas`}
                          </td>
                          {(["regular", "prime"] as FinancialTimeCategory[]).map(
                            (category) => {
                              const configured = centsToRateInput(
                                configuredRate(category, participantCount)
                              );
                              return (
                                <td
                                  key={category}
                                  className="py-3 pr-2 text-muted-foreground last:pr-0"
                                >
                                  R$ {configured || "não definido"}
                                </td>
                              );
                            }
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              ) : (
                <p className="mt-1 text-sm text-muted-foreground">
                  Usando os preços configurados de cada local.
                </p>
              )}
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
              <Popover open={scenariosOpen} onOpenChange={setScenariosOpen}>
                <PopoverTrigger
                  render={
                    <Button
                      variant="outline"
                      className="sm:ml-auto"
                      disabled={scenarios.length === 0}
                    >
                      <History className="size-4" />
                      Cenários salvos
                      {scenarios.length > 0 && (
                        <span className="rounded-full bg-muted px-1.5 text-xs font-medium">
                          {scenarios.length}
                        </span>
                      )}
                    </Button>
                  }
                />
                <PopoverContent align="end" className="w-80 p-1.5">
                  <p className="px-1.5 py-1 text-xs text-muted-foreground">
                    Carregar um cenário restaura as premissas e o resultado
                    salvos. Alterar as premissas depois não muda o que já foi
                    salvo.
                  </p>
                  <div className="mt-1 max-h-72 overflow-y-auto">
                    {scenarios.map((scenario) => (
                      <button
                        key={scenario.id}
                        type="button"
                        onClick={() => loadScenario(scenario)}
                        className="flex w-full flex-col items-start gap-0.5 rounded-md px-1.5 py-2 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
                      >
                        <span className="flex items-center gap-2 text-sm font-medium">
                          {scenario.name}
                          {scenario.result_snapshot.capacity_source?.mode ===
                            "estimated_default" && (
                            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-800 dark:text-amber-200">
                              Estimativa
                            </span>
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(scenario.created_at).toLocaleString("pt-BR")}{" "}
                          · {scenario.input_snapshot.occupancy_pct}% de ocupação
                        </span>
                      </button>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
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
            estimated={result.capacity_source?.mode === "estimated_default"}
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
    </div>
  );
}
