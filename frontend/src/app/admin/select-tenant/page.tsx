"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Calendar, CircleDollarSign, Sparkles, Users } from "lucide-react";
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
        router.replace("/");
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
      router.replace("/");
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
    <div className="min-h-screen w-full bg-[var(--bg-page)] px-6 py-12">
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

              <div className="flex items-center justify-between border-t border-border bg-muted/30 px-5 py-3">
                <span className="flex items-center gap-2 text-xs font-medium text-foreground">
                  <CircleDollarSign className="h-4 w-4 text-muted-foreground" />
                  Módulo Financeiro
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={tenant.commercial_financials_enabled}
                  aria-label={`${
                    tenant.commercial_financials_enabled ? "Desativar" : "Ativar"
                  } módulo Financeiro para ${tenant.name}`}
                  disabled={pendingFeatureIds.has(tenant.id)}
                  onClick={() => handleFeatureToggle(tenant)}
                  className={cn(
                    "relative h-5 w-9 rounded-full transition-colors disabled:opacity-60",
                    tenant.commercial_financials_enabled
                      ? "bg-emerald-500"
                      : "bg-muted-foreground/30"
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
                      tenant.commercial_financials_enabled && "translate-x-4"
                    )}
                  />
                </button>
              </div>

              <AssistantSettingsRow
                tenant={tenant}
                saving={pendingAssistantIds.has(tenant.id)}
                onSave={(temperature, memoryWindowMessages) =>
                  handleAssistantSettingsSave(
                    tenant,
                    temperature,
                    memoryWindowMessages
                  )
                }
              />
            </article>
          ))}
        </div>
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
