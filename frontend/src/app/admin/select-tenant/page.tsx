"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Building2,
  Calendar,
  CalendarClock,
  CircleDollarSign,
  Settings2,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { AuthRequestError, fetchSession, impersonate } from "@/lib/auth";
import {
  fetchTenants,
  updateAssistantSettings,
  updateCommercialFinancials,
} from "@/lib/api";
import type { TenantSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function SelectTenantPage() {
  const router = useRouter();
  const [tenants, setTenants] = useState<TenantSummary[] | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [pendingFeatureIds, setPendingFeatureIds] = useState<Set<string>>(new Set());
  const [pendingAssistantIds, setPendingAssistantIds] = useState<Set<string>>(new Set());
  const [settingsTenant, setSettingsTenant] = useState<TenantSummary | null>(null);
  const [settingsTab, setSettingsTab] = useState<"assistant" | "financial" | "tasks">("assistant");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchSession().then(async (user) => {
      if (!active) return;
      if (!user) {
        router.replace("/login");
        return;
      }
      if (user.role !== "platform_admin") {
        router.replace("/agenda");
        return;
      }
      try {
        const res = await fetchTenants();
        if (active) setTenants(res.tenants);
      } catch {
        if (active) setError("Falha ao carregar tenants");
      }
    });
    return () => {
      active = false;
    };
  }, [router]);

  async function handleSelect(tenant: TenantSummary) {
    setPendingId(tenant.id);
    setError(null);
    try {
      await impersonate(tenant.id);
      router.replace("/agenda");
    } catch (requestError) {
      if (requestError instanceof AuthRequestError && requestError.status === 401) {
        router.replace("/login");
        return;
      }
      setError("Falha ao acessar o tenant");
      setPendingId(null);
    }
  }

  function handleFeatureToggle(tenant: TenantSummary) {
    const enabled = !tenant.commercial_financials_enabled;
    setError(null);
    setTenants((current) =>
      current?.map((item) =>
        item.id === tenant.id
          ? { ...item, commercial_financials_enabled: enabled }
          : item
      ) ?? null
    );
    setSettingsTenant((current) =>
      current?.id === tenant.id
        ? { ...current, commercial_financials_enabled: enabled }
        : current
    );
    setPendingFeatureIds((current) => new Set(current).add(tenant.id));

    void updateCommercialFinancials(tenant.id, enabled)
      .catch(() => {
        setTenants((current) =>
          current?.map((item) =>
            item.id === tenant.id
              ? {
                  ...item,
                  commercial_financials_enabled: tenant.commercial_financials_enabled,
                }
              : item
          ) ?? null
        );
        setSettingsTenant((current) =>
          current?.id === tenant.id
            ? {
                ...current,
                commercial_financials_enabled: tenant.commercial_financials_enabled,
              }
            : current
        );
        setError(`Falha ao atualizar o módulo Financeiro de ${tenant.name}`);
      })
      .finally(() => {
        setPendingFeatureIds((current) => {
          const next = new Set(current);
          next.delete(tenant.id);
          return next;
        });
      });
  }

  function handleAssistantSettingsSave(
    tenant: TenantSummary,
    temperature: number,
    memoryWindowMessages: number
  ) {
    if (
      !Number.isFinite(temperature) ||
      temperature < 0 ||
      temperature > 2 ||
      !Number.isFinite(memoryWindowMessages) ||
      memoryWindowMessages < 2 ||
      memoryWindowMessages > 200
    ) {
      setError(
        "Temperatura deve ser 0–2 e janela de memória 2–200 mensagens."
      );
      return;
    }
    if (
      temperature === tenant.assistant_temperature &&
      memoryWindowMessages === tenant.assistant_memory_window_messages
    ) {
      return;
    }

    const previous = {
      temperature: tenant.assistant_temperature,
      memoryWindow: tenant.assistant_memory_window_messages,
    };
    setError(null);
    setTenants((current) =>
      current?.map((item) =>
        item.id === tenant.id
          ? {
              ...item,
              assistant_temperature: temperature,
              assistant_memory_window_messages: memoryWindowMessages,
            }
          : item
      ) ?? null
    );
    setSettingsTenant((current) =>
      current?.id === tenant.id
        ? {
            ...current,
            assistant_temperature: temperature,
            assistant_memory_window_messages: memoryWindowMessages,
          }
        : current
    );
    setPendingAssistantIds((current) => new Set(current).add(tenant.id));

    void updateAssistantSettings(tenant.id, temperature, memoryWindowMessages)
      .catch(() => {
        setTenants((current) =>
          current?.map((item) =>
            item.id === tenant.id
              ? {
                  ...item,
                  assistant_temperature: previous.temperature,
                  assistant_memory_window_messages: previous.memoryWindow,
                }
              : item
          ) ?? null
        );
        setSettingsTenant((current) =>
          current?.id === tenant.id
            ? {
                ...current,
                assistant_temperature: previous.temperature,
                assistant_memory_window_messages: previous.memoryWindow,
              }
            : current
        );
        setError(`Falha ao atualizar o assistente de ${tenant.name}`);
      })
      .finally(() => {
        setPendingAssistantIds((current) => {
          const next = new Set(current);
          next.delete(tenant.id);
          return next;
        });
      });
  }

  return (
    <div className="min-h-dvh w-full bg-[var(--bg-page)] px-4 py-8 sm:px-6 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-400 to-purple-500 text-sm font-bold text-white">
            T
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-foreground">
              Painel Admin
            </h1>
            <p className="text-sm text-muted-foreground">
              Selecione um tenant para acessar sua agenda.
            </p>
          </div>
          <Link
            href="/admin/scheduled-tasks"
            className="ml-auto rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted"
          >
            Tarefas agendadas
          </Link>
        </div>

        {error && (
          <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        {tenants === null && !error && (
          <p className="text-sm text-muted-foreground">Carregando tenants...</p>
        )}

        {tenants !== null && tenants.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nenhum tenant cadastrado ainda. Onboarding manual via scripts/create_user.py.
          </p>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {tenants?.map((tenant) => (
            <article
              key={tenant.id}
              className={cn(
                "overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-opacity hover:border-indigo-400",
                pendingId === tenant.id && "opacity-60",
                pendingId !== null && pendingId !== tenant.id && "opacity-40"
              )}
            >
              <button
                type="button"
                onClick={() => handleSelect(tenant)}
                disabled={pendingId !== null}
                className="flex w-full flex-col gap-3 p-5 text-left"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-400/80 text-sm font-semibold text-white">
                    {tenant.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-foreground">
                      {tenant.name}
                    </p>
                    <span
                      className={cn(
                        "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                        tenant.status === "active"
                          ? "bg-emerald-500/10 text-emerald-600"
                          : "bg-muted text-muted-foreground"
                      )}
                    >
                      {tenant.status}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Users className="h-3.5 w-3.5" />
                    {tenant.contact_count} contatos
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5" />
                    {tenant.appointment_count} agendamentos
                  </span>
                </div>

                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Building2 className="h-3.5 w-3.5" />
                  {tenant.assistant_phone ?? "sem número configurado"}
                </span>
              </button>

              <div className="border-t border-border bg-muted/30 p-3">
                <button
                  type="button"
                  onClick={() => {
                    setSettingsTenant(tenant);
                    setSettingsTab("assistant");
                  }}
                  className="flex w-full items-center justify-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted"
                >
                  <Settings2 className="h-4 w-4" />
                  Configurações
                </button>
              </div>
            </article>
          ))}
        </div>
        {settingsTenant && (
          <TenantSettingsDialog
            tenant={settingsTenant}
            tab={settingsTab}
            onTabChange={setSettingsTab}
            onClose={() => setSettingsTenant(null)}
            financialSaving={pendingFeatureIds.has(settingsTenant.id)}
            assistantSaving={pendingAssistantIds.has(settingsTenant.id)}
            onFeatureToggle={() => handleFeatureToggle(settingsTenant)}
            onAssistantSave={(temperature, memoryWindowMessages) =>
              handleAssistantSettingsSave(
                settingsTenant,
                temperature,
                memoryWindowMessages
              )
            }
          />
        )}
      </div>
    </div>
  );
}

function AssistantSettingsRow({
  tenant,
  saving,
  onSave,
}: {
  tenant: TenantSummary;
  saving: boolean;
  onSave: (temperature: number, memoryWindowMessages: number) => void;
}) {
  const [temperature, setTemperature] = useState(
    String(tenant.assistant_temperature)
  );
  const [memoryWindow, setMemoryWindow] = useState(
    String(tenant.assistant_memory_window_messages)
  );

  function commit() {
    onSave(Number(temperature), Number(memoryWindow));
  }

  return (
    <div className="flex items-center justify-between gap-3 border-t border-border bg-muted/30 px-5 py-3">
      <span className="flex items-center gap-2 text-xs font-medium text-foreground">
        <Sparkles className="h-4 w-4 text-muted-foreground" />
        Assistente IA
      </span>
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          Temp.
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            disabled={saving}
            onChange={(e) => setTemperature(e.target.value)}
            onBlur={commit}
            className="w-14 rounded-md border border-border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-60"
          />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          Janela
          <input
            type="number"
            min={2}
            max={200}
            step={1}
            value={memoryWindow}
            disabled={saving}
            onChange={(e) => setMemoryWindow(e.target.value)}
            onBlur={commit}
            className="w-14 rounded-md border border-border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-60"
          />
        </label>
      </div>
    </div>
  );
}

function TenantSettingsDialog({
  tenant,
  tab,
  onTabChange,
  onClose,
  financialSaving,
  assistantSaving,
  onFeatureToggle,
  onAssistantSave,
}: {
  tenant: TenantSummary;
  tab: "assistant" | "financial" | "tasks";
  onTabChange: (tab: "assistant" | "financial" | "tasks") => void;
  onClose: () => void;
  financialSaving: boolean;
  assistantSaving: boolean;
  onFeatureToggle: () => void;
  onAssistantSave: (temperature: number, memoryWindowMessages: number) => void;
}) {
  const task = tenant.scheduled_task;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="tenant-settings-title"
        className="flex h-[38rem] max-h-[calc(100dvh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 id="tenant-settings-title" className="text-base font-semibold text-foreground">
              Configurações
            </h2>
            <p className="text-sm text-muted-foreground">{tenant.name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar configurações"
            className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex gap-1 overflow-x-auto border-b border-border px-3 pt-3">
          <SettingsTabButton active={tab === "assistant"} onClick={() => onTabChange("assistant")}>
            <Sparkles className="h-4 w-4" />
            Assistente IA
          </SettingsTabButton>
          <SettingsTabButton active={tab === "financial"} onClick={() => onTabChange("financial")}>
            <CircleDollarSign className="h-4 w-4" />
            Módulo financeiro
          </SettingsTabButton>
          <SettingsTabButton active={tab === "tasks"} onClick={() => onTabChange("tasks")}>
            <CalendarClock className="h-4 w-4" />
            Resumo de tarefas
          </SettingsTabButton>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {tab === "assistant" && (
            <div className="rounded-lg border border-border">
              <AssistantSettingsRow
                tenant={tenant}
                saving={assistantSaving}
                onSave={onAssistantSave}
              />
              <p className="px-5 py-3 text-xs text-muted-foreground">
                Defina o nível de criatividade e a janela de contexto do assistente deste tenant.
              </p>
            </div>
          )}

          {tab === "financial" && (
            <div className="rounded-lg border border-border p-4">
              <div className="flex items-start justify-between gap-5">
                <div>
                  <h3 className="text-sm font-medium text-foreground">Módulo financeiro</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Habilita os recursos comerciais e financeiros para este tenant.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={tenant.commercial_financials_enabled}
                  aria-label="Alternar módulo financeiro"
                  disabled={financialSaving}
                  onClick={onFeatureToggle}
                  className={cn(
                    "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-60",
                    tenant.commercial_financials_enabled ? "bg-indigo-500" : "bg-muted"
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
                      tenant.commercial_financials_enabled ? "translate-x-5" : "translate-x-0.5"
                    )}
                  />
                </button>
              </div>
            </div>
          )}

          {tab === "tasks" && (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-sm font-medium text-foreground">Resumo de tarefas agendadas</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Status da tarefa de resumo diário deste tenant.
                  </p>
                </div>
                <Link
                  href={`/admin/scheduled-tasks?tab=manage&q=${encodeURIComponent(tenant.name)}`}
                  className="shrink-0 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted"
                >
                  Gerenciar tarefas
                </Link>
              </div>

              {!task.configured ? (
                <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                  Nenhuma tarefa de resumo diário foi configurada para este tenant.
                </div>
              ) : (
                <div className="overflow-hidden rounded-lg border border-border">
                  <dl className="divide-y divide-border text-sm">
                    <SummaryRow label="Status">
                      <span className={cn("font-medium", task.enabled ? "text-emerald-600" : "text-muted-foreground")}>
                        {task.enabled ? "Ativa" : "Desativada"}
                      </span>
                    </SummaryRow>
                    <SummaryRow label="Horário local">{task.local_time?.slice(0, 5) ?? "—"}</SummaryRow>
                    <SummaryRow label="Próxima execução">{formatTaskDate(task.next_run_at)}</SummaryRow>
                    <SummaryRow label="Última execução">
                      {task.latest_run_status
                        ? `${task.latest_run_status} · ${formatTaskDate(task.latest_run_at)}`
                        : "Sem execuções"}
                    </SummaryRow>
                  </dl>
                </div>
              )}

              {task.readiness_issues.length > 0 && (
                <div className="rounded-lg bg-amber-500/10 px-4 py-3 text-sm text-amber-700">
                  <p className="font-medium">Pendências para execução</p>
                  <ul className="mt-1 list-disc pl-5">
                    {task.readiness_issues.map((issue) => (
                      <li key={issue}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function SettingsTabButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-t-md px-3 py-2 text-sm font-medium",
        active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 px-4 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-foreground">{children}</dd>
    </div>
  );
}

function formatTaskDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}
