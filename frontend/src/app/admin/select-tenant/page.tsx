"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Archive,
  ArchiveRestore,
  Building2,
  Calendar,
  CalendarClock,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  Plus,
  RotateCcw,
  Settings2,
  ShieldOff,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { AuthRequestError, fetchSession, impersonate } from "@/lib/auth";
import {
  ApiError,
  archiveTenant,
  createTenant,
  fetchTenants,
  reactivateTenant,
  restoreTenant,
  suspendTenant,
  updateAssistantSettings,
  updateCommercialFinancials,
  updateTenantWhatsappNumber,
} from "@/lib/api";
import type { TenantCreateInput, TenantListResponse, TenantSummary } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { WhatsappField } from "@/components/ui/whatsapp-field";
import { cn } from "@/lib/utils";
import { PlatformAdminHeader } from "@/components/admin/platform-admin-header";
import { TENANT_TIMEZONES } from "@/lib/tenant-timezones";

type LifecycleAction = "suspend" | "reactivate" | "archive" | "restore";
type SettingsTab = "assistant" | "financial" | "tasks" | "lifecycle";
const TENANTS_PER_PAGE = 12;

export default function SelectTenantPage() {
  const router = useRouter();
  const [tenants, setTenants] = useState<TenantSummary[] | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [pendingFeatureIds, setPendingFeatureIds] = useState<Set<string>>(new Set());
  const [pendingAssistantIds, setPendingAssistantIds] = useState<Set<string>>(new Set());
  const [pendingWhatsappIds, setPendingWhatsappIds] = useState<Set<string>>(new Set());
  const [pendingLifecycleIds, setPendingLifecycleIds] = useState<Set<string>>(new Set());
  const [settingsTenant, setSettingsTenant] = useState<TenantSummary | null>(null);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("assistant");
  const [showArchived, setShowArchived] = useState(false);
  const [pagination, setPagination] = useState<Omit<TenantListResponse, "tenants"> | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adminEmail, setAdminEmail] = useState<string | null>(null);
  const latestTenantRequest = useRef(0);

  const loadTenants = useCallback(async (includeArchived: boolean, page: number) => {
    const requestId = ++latestTenantRequest.current;
    try {
      let res = await fetchTenants({
        includeArchived,
        page,
        pageSize: TENANTS_PER_PAGE,
      });
      if (requestId !== latestTenantRequest.current) return;
      if (res.total_pages > 0 && page > res.total_pages) {
        res = await fetchTenants({
          includeArchived,
          page: res.total_pages,
          pageSize: TENANTS_PER_PAGE,
        });
        if (requestId !== latestTenantRequest.current) return;
      }
      setTenants(res.tenants);
      setPagination({
        page: res.page,
        page_size: res.page_size,
        total: res.total,
        total_pages: res.total_pages,
      });
    } catch {
      if (requestId === latestTenantRequest.current) {
        setError("Não foi possível carregar os tenants. Tente novamente.");
      }
    }
  }, []);

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
      setAdminEmail(user.email);
      await loadTenants(false, 1);
    });
    return () => {
      active = false;
    };
  }, [router, loadTenants]);

  function handleToggleArchived() {
    const next = !showArchived;
    setShowArchived(next);
    void loadTenants(next, 1);
  }

  function handlePageChange(page: number) {
    if (!pagination || page < 1 || page > pagination.total_pages) return;
    void loadTenants(showArchived, page);
  }

  async function handleTenantCreated() {
    setShowArchived(false);
    await loadTenants(false, 1);
    setSuccess("Tenant criado. O proprietário recebeu um email de ativação.");
  }

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
      if (requestError instanceof AuthRequestError && requestError.status === 409) {
        const label = tenant.status === "archived" ? "arquivado" : "suspenso";
        if (window.confirm(`${tenant.name} está ${label}. Acessar mesmo assim?`)) {
          try {
            await impersonate(tenant.id, { confirm: true });
            router.replace("/agenda");
            return;
          } catch {
            setError("Não foi possível acessar o tenant. Tente novamente.");
          }
        }
        setPendingId(null);
        return;
      }
      setError("Não foi possível acessar o tenant. Tente novamente.");
      setPendingId(null);
    }
  }

  function handleLifecycleAction(
    tenant: TenantSummary,
    action: LifecycleAction,
    reason?: string
  ) {
    const optimisticStatus =
      action === "suspend"
        ? "suspended"
        : action === "archive"
          ? "archived"
          : "active";
    const optimisticReason =
      action === "suspend" || action === "archive" ? reason ?? null : null;
    const previous = {
      status: tenant.status,
      status_changed_at: tenant.status_changed_at,
      status_reason: tenant.status_reason,
    };
    setError(null);

    const applyLocal = (patch: Partial<TenantSummary>) => {
      setTenants(
        (current) =>
          current?.map((item) =>
            item.id === tenant.id ? { ...item, ...patch } : item
          ) ?? null
      );
      setSettingsTenant((current) =>
        current?.id === tenant.id ? { ...current, ...patch } : current
      );
    };

    applyLocal({ status: optimisticStatus, status_reason: optimisticReason });
    setPendingLifecycleIds((current) => new Set(current).add(tenant.id));

    const call =
      action === "suspend"
        ? suspendTenant(tenant.id, reason)
        : action === "reactivate"
          ? reactivateTenant(tenant.id)
          : action === "archive"
            ? archiveTenant(tenant.id, reason)
            : restoreTenant(tenant.id);

    void call
      .then((state) => {
        const dropTile = state.status === "archived" && !showArchived;
        if (dropTile) {
          setTenants(
            (current) => current?.filter((item) => item.id !== tenant.id) ?? null
          );
          setSettingsTenant((current) =>
            current?.id === tenant.id ? null : current
          );
          void loadTenants(showArchived, pagination?.page ?? 1);
          return;
        }
        applyLocal({
          status: state.status,
          status_changed_at: state.status_changed_at,
          status_reason: state.status_reason,
        });
        void loadTenants(showArchived, pagination?.page ?? 1);
      })
      .catch(() => {
        applyLocal(previous);
        setError(`Falha ao atualizar o ciclo de vida de ${tenant.name}`);
      })
      .finally(() => {
        setPendingLifecycleIds((current) => {
          const next = new Set(current);
          next.delete(tenant.id);
          return next;
        });
      });
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

  function handleWhatsappNumberSave(tenant: TenantSummary, whatsapp: string) {
    const trimmed = whatsapp.trim();
    if (!trimmed || trimmed === tenant.assistant_phone) {
      return;
    }
    setError(null);
    setPendingWhatsappIds((current) => new Set(current).add(tenant.id));

    void updateTenantWhatsappNumber(tenant.id, trimmed)
      .then((updated) => {
        setTenants((current) =>
          current?.map((item) => (item.id === tenant.id ? updated : item)) ?? null
        );
        setSettingsTenant((current) =>
          current?.id === tenant.id ? updated : current
        );
      })
      .catch((err) => {
        const code = err instanceof ApiError ? err.code : undefined;
        setError(
          code === "WHATSAPP_NUMBER_ALREADY_IN_USE"
            ? "Este número já está associado a outro tenant."
            : `Falha ao atualizar o número de ${tenant.name}`
        );
      })
      .finally(() => {
        setPendingWhatsappIds((current) => {
          const next = new Set(current);
          next.delete(tenant.id);
          return next;
        });
      });
  }

  return (
    <div className="min-h-dvh w-full bg-[var(--bg-page)] px-4 py-8 sm:px-6 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <PlatformAdminHeader active="tenants" adminEmail={adminEmail} />
        <div className="mb-8 flex flex-wrap items-start gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Tenants
            </h1>
            <p className="text-sm text-muted-foreground">
              Selecione um tenant para acessar sua agenda.
            </p>
          </div>
          <div className="ml-auto flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setError(null);
                setSuccess(null);
                setCreateDialogOpen(true);
              }}
              className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              <Plus className="h-4 w-4" />
              Novo tenant
            </button>
            <button
              type="button"
              onClick={handleToggleArchived}
              className={cn(
                "rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-muted",
                showArchived
                  ? "bg-muted text-foreground"
                  : "bg-card text-muted-foreground"
              )}
            >
              {showArchived ? "Ocultar arquivados" : "Mostrar arquivados"}
            </button>
          </div>
        </div>

        {success && (
          <p className="mb-4 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700" role="status">
            {success}
          </p>
        )}
        {error && (
          <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {tenants === null && !error && (
          <p className="text-sm text-muted-foreground">Carregando tenants...</p>
        )}

        {tenants !== null && tenants.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {showArchived
              ? "Nenhum tenant arquivado encontrado."
              : "Nenhum tenant cadastrado ainda. Crie o primeiro tenant para enviar o email de ativação."}
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
                        statusBadgeClass(tenant.status)
                      )}
                    >
                      {statusLabel(tenant.status)}
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
                  {tenant.agent_binding_confirmed_at ? (
                    <span className="ml-1 inline-flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400">
                      <Check className="h-3.5 w-3.5" />
                      assistente ativo
                    </span>
                  ) : (
                    <span className="ml-1 text-muted-foreground/70">
                      assistente inativo
                    </span>
                  )}
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
        {pagination && pagination.total > 0 && (
          <TenantPager
            page={pagination.page}
            pageSize={pagination.page_size}
            total={pagination.total}
            totalPages={pagination.total_pages}
            onChange={handlePageChange}
          />
        )}
        <TenantCreationDialog
          open={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          onCreated={handleTenantCreated}
          onError={setError}
        />
        {settingsTenant && (
          <TenantSettingsDialog
            tenant={settingsTenant}
            tab={settingsTab}
            onTabChange={setSettingsTab}
            onClose={() => setSettingsTenant(null)}
            financialSaving={pendingFeatureIds.has(settingsTenant.id)}
            assistantSaving={pendingAssistantIds.has(settingsTenant.id)}
            whatsappSaving={pendingWhatsappIds.has(settingsTenant.id)}
            lifecycleSaving={pendingLifecycleIds.has(settingsTenant.id)}
            onFeatureToggle={() => handleFeatureToggle(settingsTenant)}
            onAssistantSave={(temperature, memoryWindowMessages) =>
              handleAssistantSettingsSave(
                settingsTenant,
                temperature,
                memoryWindowMessages
              )
            }
            onWhatsappNumberSave={(whatsapp) =>
              handleWhatsappNumberSave(settingsTenant, whatsapp)
            }
            onLifecycleAction={(action, reason) =>
              handleLifecycleAction(settingsTenant, action, reason)
            }
          />
        )}
      </div>
    </div>
  );
}

function TenantPager({
  page,
  pageSize,
  total,
  totalPages,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <nav
      aria-label="Paginação de tenants"
      className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-sm text-muted-foreground"
    >
      <span>{start}–{end} de {total} tenants</span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Página anterior"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className="rounded-md border border-border bg-card p-1.5 text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span>Página {page} de {totalPages}</span>
        <button
          type="button"
          aria-label="Próxima página"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
          className="rounded-md border border-border bg-card p-1.5 text-foreground hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </nav>
  );
}

function TenantCreationDialog({
  open,
  onOpenChange,
  onCreated,
  onError,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => Promise<void>;
  onError: (message: string | null) => void;
}) {
  const [values, setValues] = useState<TenantCreateInput>({
    name: "",
    owner_email: "",
    whatsapp: "",
    timezone: "America/Sao_Paulo",
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function updateValue<K extends keyof TenantCreateInput>(key: K, value: TenantCreateInput[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    onError(null);
    if (!values.whatsapp) {
      setFormError("Informe o número de WhatsApp da operação.");
      return;
    }
    setSubmitting(true);
    try {
      await createTenant(values);
      setValues({
        name: "",
        owner_email: "",
        whatsapp: "",
        timezone: "America/Sao_Paulo",
      });
      onOpenChange(false);
      await onCreated();
    } catch (requestError) {
      setFormError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível criar o tenant."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" showCloseButton={!submitting}>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Novo tenant</DialogTitle>
            <DialogDescription>
              Crie o tenant e envie ao proprietário o email para ativar a conta e definir a senha.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="tenant-name">Nome do tenant</Label>
              <Input
                id="tenant-name"
                value={values.name}
                onChange={(event) => updateValue("name", event.target.value)}
                minLength={2}
                maxLength={255}
                required
                disabled={submitting}
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tenant-owner-email">Email do proprietário</Label>
              <Input
                id="tenant-owner-email"
                type="email"
                value={values.owner_email}
                onChange={(event) => updateValue("owner_email", event.target.value)}
                maxLength={255}
                required
                disabled={submitting}
              />
            </div>
            <WhatsappField
              id="tenant-whatsapp"
              value={values.whatsapp}
              onChange={(value) => updateValue("whatsapp", value)}
            />
            <div className="space-y-2">
              <Label htmlFor="tenant-timezone">Fuso horário</Label>
              <select
                id="tenant-timezone"
                value={values.timezone}
                onChange={(event) => updateValue("timezone", event.target.value)}
                required
                disabled={submitting}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {TENANT_TIMEZONES.map((timezone) => (
                  <option key={timezone} value={timezone}>{timezone}</option>
                ))}
              </select>
            </div>
            {formError && <p className="text-sm text-destructive" role="alert">{formError}</p>}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Criando..." : "Criar e enviar ativação"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
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

function WhatsappNumberRow({
  tenant,
  saving,
  onSave,
}: {
  tenant: TenantSummary;
  saving: boolean;
  onSave: (whatsapp: string) => void;
}) {
  const [value, setValue] = useState(tenant.assistant_phone ?? "");
  const dirty = value.trim() !== "" && value.trim() !== tenant.assistant_phone;

  return (
    <div className="rounded-lg border border-border p-4">
      <h3 className="text-sm font-medium text-foreground">Número de WhatsApp</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Número que o instrutor usa com os alunos. Trocar o número desativa o
        assistente até uma nova ativação.
      </p>
      <div className="mt-3 space-y-3">
        <WhatsappField
          id={`tenant-whatsapp-${tenant.id}`}
          value={value}
          onChange={setValue}
          label=""
          hint={null}
        />
        <Button
          size="sm"
          disabled={saving || !dirty}
          onClick={() => onSave(value)}
        >
          {saving ? "Salvando…" : "Salvar número"}
        </Button>
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
  whatsappSaving,
  lifecycleSaving,
  onFeatureToggle,
  onAssistantSave,
  onWhatsappNumberSave,
  onLifecycleAction,
}: {
  tenant: TenantSummary;
  tab: SettingsTab;
  onTabChange: (tab: SettingsTab) => void;
  onClose: () => void;
  financialSaving: boolean;
  assistantSaving: boolean;
  whatsappSaving: boolean;
  lifecycleSaving: boolean;
  onFeatureToggle: () => void;
  onAssistantSave: (temperature: number, memoryWindowMessages: number) => void;
  onWhatsappNumberSave: (whatsapp: string) => void;
  onLifecycleAction: (action: LifecycleAction, reason?: string) => void;
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
          <SettingsTabButton active={tab === "lifecycle"} onClick={() => onTabChange("lifecycle")}>
            <ShieldOff className="h-4 w-4" />
            Ciclo de vida
          </SettingsTabButton>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {tab === "assistant" && (
            <div className="space-y-4">
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
              <WhatsappNumberRow
                tenant={tenant}
                saving={whatsappSaving}
                onSave={onWhatsappNumberSave}
              />
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

          {tab === "lifecycle" && (
            <LifecycleTab
              tenant={tenant}
              saving={lifecycleSaving}
              onAction={onLifecycleAction}
            />
          )}
        </div>
      </section>
    </div>
  );
}

function LifecycleTab({
  tenant,
  saving,
  onAction,
}: {
  tenant: TenantSummary;
  saving: boolean;
  onAction: (action: LifecycleAction, reason?: string) => void;
}) {
  const [suspendReason, setSuspendReason] = useState("");
  const [archiveReason, setArchiveReason] = useState("");
  const [archiveConfirm, setArchiveConfirm] = useState("");

  const changedAt = tenant.status_changed_at
    ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(
        new Date(tenant.status_changed_at)
      )
    : null;

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-border p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-foreground">Status atual</h3>
          <span
            className={cn(
              "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
              statusBadgeClass(tenant.status)
            )}
          >
            {statusLabel(tenant.status)}
          </span>
        </div>
        {tenant.status !== "active" && (
          <p className="mt-2 text-xs text-muted-foreground">
            Alterado {changedAt ?? "—"}
            {tenant.status_reason ? ` · ${tenant.status_reason}` : ""}
          </p>
        )}
      </div>

      {tenant.status === "suspended" && (
        <button
          type="button"
          disabled={saving}
          onClick={() => onAction("reactivate")}
          className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-60"
        >
          <RotateCcw className="h-4 w-4" />
          Reativar tenant
        </button>
      )}

      {tenant.status === "archived" ? (
        <button
          type="button"
          disabled={saving}
          onClick={() => onAction("restore")}
          className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground hover:bg-muted disabled:opacity-60"
        >
          <ArchiveRestore className="h-4 w-4" />
          Restaurar tenant
        </button>
      ) : (
        <>
          {tenant.status === "active" && (
            <div className="rounded-lg border border-border p-4">
              <h3 className="text-sm font-medium text-foreground">Suspender</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Bloqueia login, mensagens do agente e tarefas agendadas. Reversível.
              </p>
              <textarea
                value={suspendReason}
                onChange={(e) => setSuspendReason(e.target.value)}
                placeholder="Motivo (opcional)"
                rows={2}
                maxLength={500}
                className="mt-3 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
              />
              <button
                type="button"
                disabled={saving}
                onClick={() => onAction("suspend", suspendReason.trim() || undefined)}
                className="mt-3 flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm font-medium text-amber-700 hover:bg-amber-500/20 disabled:opacity-60"
              >
                <ShieldOff className="h-4 w-4" />
                Suspender tenant
              </button>
            </div>
          )}

          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
            <h3 className="text-sm font-medium text-foreground">Zona de risco</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Arquivar remove o tenant da grade e desconecta todos os seus usuários.
              Nenhum dado é apagado; a ação é reversível em Restaurar.
            </p>
            <textarea
              value={archiveReason}
              onChange={(e) => setArchiveReason(e.target.value)}
              placeholder="Motivo (opcional)"
              rows={2}
              maxLength={500}
              className="mt-3 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
            />
            <label className="mt-3 block text-xs text-muted-foreground">
              Digite <span className="font-medium text-foreground">{tenant.name}</span> para confirmar
              <input
                value={archiveConfirm}
                onChange={(e) => setArchiveConfirm(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
              />
            </label>
            <button
              type="button"
              disabled={saving || archiveConfirm.trim() !== tenant.name}
              onClick={() => onAction("archive", archiveReason.trim() || undefined)}
              className="mt-3 flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/20 disabled:opacity-50"
            >
              <Archive className="h-4 w-4" />
              Arquivar tenant
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function statusBadgeClass(status: string): string {
  if (status === "active") return "bg-emerald-500/10 text-emerald-600";
  if (status === "suspended") return "bg-amber-500/10 text-amber-700";
  if (status === "archived") return "bg-slate-500/10 text-slate-600";
  return "bg-muted text-muted-foreground";
}

function statusLabel(status: string): string {
  if (status === "active") return "ativo";
  if (status === "suspended") return "suspenso";
  if (status === "archived") return "arquivado";
  return status;
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
