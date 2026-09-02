import { ArrowRight, Scale } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatBrlFromCents } from "@/lib/financial-utils";
import type { FinancialScenarioResult } from "@/lib/types";

function signedCurrency(cents: number) {
  const formatted = formatBrlFromCents(Math.abs(cents));
  return `${cents >= 0 ? "+" : "-"}${formatted}`;
}

export function ScenarioResults({
  result,
}: {
  result: FinancialScenarioResult;
}) {
  return (
    <div className="space-y-5">
      {result.capacity_source?.mode === "estimated_default" && (
        <Badge variant="outline" className="border-amber-500/40 bg-amber-500/5 text-amber-800 dark:text-amber-200">
          Estimativa de capacidade
        </Badge>
      )}
      <div className="grid items-stretch gap-3 md:grid-cols-[1fr_auto_1fr]">
        <Card>
          <CardHeader>
            <CardDescription>Aulas agendadas atuais</CardDescription>
            <CardTitle>
              {formatBrlFromCents(result.baseline.projected_revenue_cents)}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs text-muted-foreground">
            <p>{result.baseline.occupancy_pct.toFixed(1)}% de ocupação</p>
            <p>{result.baseline.participant_hours.toFixed(1)} horas-aluno</p>
            <p>Eventos avulsos não entram nesta comparação.</p>
          </CardContent>
        </Card>
        <ArrowRight className="hidden size-5 self-center text-muted-foreground md:block" />
        <Card className="border-primary/40 bg-primary/5">
          <CardHeader>
            <CardDescription>Cenário simulado</CardDescription>
            <CardTitle>
              {formatBrlFromCents(result.scenario.projected_revenue_cents)}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs text-muted-foreground">
            <p>{result.scenario.occupancy_pct.toFixed(1)}% de ocupação</p>
            <p>{result.scenario.participant_hours.toFixed(1)} horas-aluno</p>
            <p
              className={
                result.incremental_revenue_cents >= 0
                  ? "font-medium text-emerald-700"
                  : "font-medium text-destructive"
              }
            >
              {signedCurrency(result.incremental_revenue_cents)} versus atual
            </p>
          </CardContent>
        </Card>
      </div>

      {result.customer_estimate && (
        <Card>
          <CardHeader>
            <CardDescription>Base de clientes estimada</CardDescription>
            <CardTitle>
              {result.customer_estimate.minimum_customers}–{result.customer_estimate.maximum_customers} clientes
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            {result.customer_estimate.weekly_participant_hours.toFixed(1)} horas-aluno por semana, considerando de 1 a 3 horas por cliente/semana em {result.customer_estimate.calendar_weeks} semana(s).
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Scale className="size-4 text-primary" />
            Trade-off individual × grupos
          </CardTitle>
          <CardDescription>
            Ocupação mínima do grupo para igualar a receita de uma aula
            individual de uma hora.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="mb-2 text-xs text-muted-foreground sm:hidden">
            Deslize para ver toda a comparação.
          </p>
          <div
            className="overflow-x-auto"
            role="region"
            aria-label="Comparação entre formatos de aula"
            tabIndex={0}
          >
          <table className="w-full min-w-[620px] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="pb-2 font-medium">Formato</th>
                <th className="pb-2 font-medium">R$/aluno/h médio</th>
                <th className="pb-2 font-medium">Receita com turma cheia</th>
                <th className="pb-2 font-medium">Versus individual</th>
                <th className="pb-2 font-medium">Ponto de equilíbrio</th>
              </tr>
            </thead>
            <tbody>
              {result.tradeoffs.map((row) => (
                <tr key={row.participant_count} className="border-b last:border-0">
                  <td className="py-3 font-medium">
                    {row.participant_count === 1
                      ? "Individual"
                      : `${row.participant_count} pessoas`}
                  </td>
                  <td className="py-3">
                    {formatBrlFromCents(row.average_hourly_rate_cents)}
                  </td>
                  <td className="py-3">
                    {formatBrlFromCents(row.full_class_revenue_cents)}
                  </td>
                  <td className="py-3">
                    {row.revenue_vs_individual_pct === null
                      ? "Preço incompleto"
                      : `${row.revenue_vs_individual_pct.toFixed(1)}%`}
                  </td>
                  <td className="py-3">
                    {row.participant_count === 1
                      ? "Referência"
                      : row.break_even_occupancy_pct === null
                        ? "Preço incompleto"
                        : `${row.break_even_occupancy_pct.toFixed(1)}% da turma`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
