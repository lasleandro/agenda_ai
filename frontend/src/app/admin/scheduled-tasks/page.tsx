"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CalendarClock, CheckCircle2, ChevronLeft, ChevronRight,
  ListFilter, PlusCircle, Search, ScrollText, ShieldCheck,
} from "lucide-react";
import { fetchSession } from "@/lib/auth";
import {
  fetchScheduledTaskRuns, fetchScheduledTasks, searchScheduledTaskTenants,
  updateDailyAgendaTask, type ScheduledTaskQuery, type ScheduledTaskRunLogQuery,
} from "@/lib/api";
import type {
  ScheduledTaskAdminSummary, ScheduledTaskRunLogEntry, ScheduledTaskTenantSuggestion,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { PlatformAdminHeader } from "@/components/admin/platform-admin-header";

type Tab = "create" | "manage" | "logs";

function timeValue(value: string) { return value.slice(0, 5); }
function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
}
function statusLabel(status?: string) {
  return ({ queued: "Na fila", processing: "Processando", retry_wait: "Nova tentativa", provider_accepted: "Aceito", sent: "Enviado", delivered: "Entregue", read: "Lido", delivery_unknown: "Confirmação pendente", failed: "Falhou", skipped: "Ignorado" } as Record<string, string>)[status ?? ""] ?? "—";
}
function statusClass(status?: string) {
  if (status === "delivered" || status === "read") return "bg-emerald-500/10 text-emerald-700";
  if (status === "failed" || status === "delivery_unknown") return "bg-destructive/10 text-destructive";
  if (status === "skipped") return "bg-amber-500/10 text-amber-700";
  return "bg-muted text-muted-foreground";
}

function Pager({ page, pageSize, total, onChange }: { page: number; pageSize: number; total: number; onChange: (page: number) => void }) {
  const last = Math.max(1, Math.ceil(total / pageSize));
  if (!total) return null;
  return <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground"><span>{total} resultado{total === 1 ? "" : "s"}</span><div className="flex items-center gap-2"><button type="button" aria-label="Página anterior" disabled={page <= 1} onClick={() => onChange(page - 1)} className="rounded-md border border-border p-1.5 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button><span>{page} de {last}</span><button type="button" aria-label="Próxima página" disabled={page >= last} onClick={() => onChange(page + 1)} className="rounded-md border border-border p-1.5 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button></div></div>;
}

export default function ScheduledTasksPage() {
  // useSearchParams() must sit under a Suspense boundary for `next build` to
  // prerender the route shell.
  return (
    <Suspense fallback={null}>
      <ScheduledTasksPageInner />
    </Suspense>
  );
}

function ScheduledTasksPageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [authorized, setAuthorized] = useState(false);
  const [adminEmail, setAdminEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tab: Tab = ["create", "manage", "logs"].includes(params.get("tab") ?? "") ? params.get("tab") as Tab : "create";

  useEffect(() => {
    let active = true;
    void fetchSession().then((user) => {
      if (!active) return;
      if (!user) router.replace("/login");
      else if (user.role !== "platform_admin") router.replace("/agenda");
      else {
        setAdminEmail(user.email);
        setAuthorized(true);
      }
    });
    return () => { active = false; };
  }, [router]);

  function setParams(values: Record<string, string | undefined>) {
    const next = new URLSearchParams(params.toString());
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    router.replace(`/admin/scheduled-tasks${next.size ? `?${next}` : ""}`);
  }
  if (!authorized) return null;

  return <div className="min-h-dvh w-full bg-[var(--bg-page)] px-4 py-8 sm:px-6 sm:py-10"><div className="mx-auto max-w-6xl">
    <PlatformAdminHeader active="tasks" adminEmail={adminEmail} />
    <div className="mb-7 flex items-start gap-2.5"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500 text-white"><CalendarClock className="h-5 w-5" /></div><div><h1 className="text-xl font-semibold tracking-tight text-foreground">Tarefas agendadas</h1><p className="text-sm text-muted-foreground">Configure, gerencie e acompanhe tarefas por tenant.</p></div></div>
    <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-border" aria-label="Tarefas agendadas">
      <TabButton active={tab === "create"} icon={PlusCircle} onClick={() => setParams({ tab: "create" })}>Criar tarefa</TabButton>
      <TabButton active={tab === "manage"} icon={ListFilter} onClick={() => setParams({ tab: "manage" })}>Gerenciar tarefas</TabButton>
      <TabButton active={tab === "logs"} icon={ScrollText} onClick={() => setParams({ tab: "logs" })}>Log de execução</TabButton>
    </nav>
    {error && <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
    {tab === "create" && <CreateTab onError={setError} onManage={(tenant) => setParams({ tab: "manage", q: tenant, page: undefined })} />}
    {tab === "manage" && <ManageTab params={params} setParams={setParams} onError={setError} />}
    {tab === "logs" && <LogTab params={params} setParams={setParams} />}
  </div></div>;
}

function TabButton({ active, icon: Icon, onClick, children }: { active: boolean; icon: typeof PlusCircle; onClick: () => void; children: string }) {
  return <button type="button" onClick={onClick} className={cn("-mb-px flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium", active ? "border-indigo-500 text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}><Icon className="h-4 w-4" />{children}</button>;
}

function CreateTab({ onError, onManage }: { onError: (message: string | null) => void; onManage: (tenant: string) => void }) {
  const [query, setQuery] = useState("");
  const [tenants, setTenants] = useState<ScheduledTaskTenantSuggestion[]>([]);
  const [selected, setSelected] = useState<ScheduledTaskTenantSuggestion | null>(null);
  const [localTime, setLocalTime] = useState("07:00");
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      void searchScheduledTaskTenants(query).then((result) => { if (active) setTenants(result.tenants); }).catch(() => { if (active) setTenants([]); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query]);
  async function save() {
    if (!selected || selected.task_configured || !consent) return;
    setSaving(true); setSuccess(null); onError(null);
    try {
      await updateDailyAgendaTask(selected.id, { enabled: true, local_time: localTime, consent_confirmed: true });
      setSelected({ ...selected, task_configured: true }); setSuccess(`Resumo diário configurado para ${selected.name}.`);
    } catch (reason) { onError(reason instanceof Error ? reason.message : "Não foi possível criar a tarefa. Tente novamente."); }
    finally { setSaving(false); }
  }
  return <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
    <section><h2 className="text-sm font-semibold text-foreground">Repositório de tarefas</h2><p className="mt-1 text-sm text-muted-foreground">Escolha um tipo para configurar em um tenant.</p><button type="button" aria-pressed className="mt-4 w-full rounded-xl border-2 border-indigo-500 bg-card p-5 text-left shadow-sm"><div className="flex items-start justify-between gap-3"><div><p className="font-medium text-foreground">Resumo diário da agenda</p><p className="mt-1 text-sm text-muted-foreground">WhatsApp · todos os dias · aulas e eventos confirmados</p></div><CheckCircle2 className="h-5 w-5 shrink-0 text-indigo-500" /></div></button></section>
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm"><h2 className="text-sm font-semibold text-foreground">Configurar tenant</h2><label className="mt-4 block text-sm text-muted-foreground">Buscar tenant<div className="relative mt-1.5"><Search className="absolute left-3 top-2.5 h-4 w-4" /><input value={query} onChange={(event) => { setQuery(event.target.value); setSelected(null); }} placeholder="Digite o nome do tenant" className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-sm text-foreground" /></div></label>
      {!selected && tenants.length > 0 && <div className="mt-2 max-h-52 overflow-auto rounded-md border border-border bg-background">{tenants.map((tenant) => <button key={tenant.id} type="button" onClick={() => { setSelected(tenant); setQuery(tenant.name); }} className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm hover:bg-muted"><span><span className="block font-medium text-foreground">{tenant.name}</span><span className="text-xs text-muted-foreground">{tenant.timezone} · {tenant.status}</span></span>{tenant.task_configured && <span className="text-xs text-amber-700">Já configurada</span>}</button>)}</div>}
      {selected && <div className="mt-4"><div className="rounded-md bg-muted px-3 py-2 text-sm"><span className="font-medium text-foreground">{selected.name}</span><span className="ml-2 text-muted-foreground">{selected.timezone}</span></div>{selected.readiness_issues.length > 0 && <p className="mt-3 rounded-md bg-amber-500/10 p-2 text-xs text-amber-800">{selected.readiness_issues.join(" · ")}</p>}{selected.task_configured ? <div className="mt-4 rounded-md bg-amber-500/10 p-3 text-sm text-amber-800">Este tenant já possui esta tarefa. <button type="button" onClick={() => onManage(selected.name)} className="font-medium underline">Abrir em Gerenciar tarefas</button></div> : <><label className="mt-4 block text-sm text-muted-foreground">Horário local<input type="time" value={localTime} onChange={(event) => setLocalTime(event.target.value)} className="mt-1.5 block rounded-md border border-border bg-background px-2 py-1.5 text-foreground" /></label><label className="mt-4 flex items-start gap-2.5 text-sm text-muted-foreground"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-0.5 h-4 w-4" /><span><span className="flex items-center gap-1 font-medium text-foreground"><ShieldCheck className="h-4 w-4" />Consentimento confirmado</span>O administrador confirmou a autorização do instrutor.</span></label><button type="button" disabled={!consent || saving || selected.readiness_issues.length > 0} onClick={() => void save()} className="mt-5 inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"><PlusCircle className="h-4 w-4" />Criar tarefa</button></>}</div>}{success && <p className="mt-4 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700">{success}</p>}</section>
  </div>;
}

function ManageTab({ params, setParams, onError }: { params: ReturnType<typeof useSearchParams>; setParams: (values: Record<string, string | undefined>) => void; onError: (message: string | null) => void }) {
  const q = params.get("q") ?? ""; const enabled = params.get("enabled") ?? ""; const tenantStatus = params.get("tenant_status") ?? ""; const readiness = params.get("readiness") ?? ""; const latestRunStatus = params.get("latest_run_status") ?? ""; const page = Number(params.get("page") ?? "1");
  const [draft, setDraft] = useState(q); const [data, setData] = useState<{ tasks: ScheduledTaskAdminSummary[]; total: number; page: number; page_size: number } | null>(null); const [selected, setSelected] = useState<ScheduledTaskAdminSummary | null>(null);
  useEffect(() => { let active = true; const query: ScheduledTaskQuery = { q, page, page_size: 15, tenant_status: tenantStatus || undefined, latest_run_status: latestRunStatus || undefined }; if (enabled) query.enabled = enabled === "true"; if (readiness === "ready" || readiness === "blocked") query.readiness = readiness; void fetchScheduledTasks(query).then((result) => { if (active) setData(result); }).catch((reason) => { if (active) onError(reason instanceof Error ? reason.message : "Não foi possível carregar as tarefas. Tente novamente."); }); return () => { active = false; }; }, [enabled, latestRunStatus, onError, page, q, readiness, tenantStatus]);
  function update(task: ScheduledTaskAdminSummary) { setData((current) => current ? { ...current, tasks: current.tasks.map((item) => item.task_id === task.task_id ? task : item) } : current); setSelected(task); }
  return <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]"><section className="rounded-xl border border-border bg-card p-5 shadow-sm"><div className="flex flex-wrap gap-3"><div className="relative min-w-52 flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><input value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") setParams({ tab: "manage", q: draft || undefined, page: undefined }); }} placeholder="Buscar tenant" className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-sm" /></div><select value={enabled} onChange={(event) => setParams({ tab: "manage", enabled: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm"><option value="">Todos os estados</option><option value="true">Ativas</option><option value="false">Desativadas</option></select><select value={tenantStatus} onChange={(event) => setParams({ tab: "manage", tenant_status: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm"><option value="">Todos os tenants</option><option value="active">Ativos</option><option value="inactive">Inativos</option></select><select value={readiness} onChange={(event) => setParams({ tab: "manage", readiness: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm"><option value="">Toda prontidão</option><option value="ready">Prontas</option><option value="blocked">Com bloqueio</option></select><select value={latestRunStatus} onChange={(event) => setParams({ tab: "manage", latest_run_status: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm"><option value="">Toda última execução</option><option value="delivered">Entregue</option><option value="failed">Falhou</option><option value="skipped">Ignorada</option></select><button type="button" onClick={() => setParams({ tab: "manage", q: draft || undefined, page: undefined })} className="rounded-md bg-muted px-3 py-2 text-sm font-medium">Filtrar</button></div><div className="mt-5 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="border-b border-border text-xs uppercase text-muted-foreground"><tr><th className="px-2 py-3">Tenant</th><th className="px-2 py-3">Horário</th><th className="px-2 py-3">Estado</th><th className="px-2 py-3">Próxima</th><th className="px-2 py-3">Última</th></tr></thead><tbody>{data?.tasks.map((task) => <tr key={task.task_id} onClick={() => setSelected(task)} className={cn("cursor-pointer border-b border-border/70 hover:bg-muted/60", selected?.task_id === task.task_id && "bg-muted")}><td className="px-2 py-3"><span className="block font-medium text-foreground">{task.professional_name}</span><span className="text-xs text-muted-foreground">{task.timezone}</span></td><td className="px-2 py-3">{timeValue(task.local_time)}</td><td className="px-2 py-3"><span className={cn("rounded-full px-2 py-1 text-xs", task.enabled ? "bg-emerald-500/10 text-emerald-700" : "bg-muted text-muted-foreground")}>{task.enabled ? "Ativa" : "Desativada"}</span>{task.readiness_issues.length > 0 && <span className="ml-2 text-xs text-amber-700">Bloqueio</span>}</td><td className="px-2 py-3">{formatDate(task.next_run_at)}</td><td className="px-2 py-3">{statusLabel(task.latest_run?.status)}</td></tr>)}</tbody></table>{data?.tasks.length === 0 && <p className="py-10 text-center text-sm text-muted-foreground">Nenhuma tarefa encontrada.</p>}</div>{data && <Pager page={data.page} pageSize={data.page_size} total={data.total} onChange={(next) => setParams({ tab: "manage", page: String(next) })} />}</section><aside>{selected ? <TaskEditor key={`${selected.task_id}-${selected.local_time}-${selected.consent_confirmed}`} task={selected} onSaved={update} onError={onError} /> : <div className="rounded-xl border border-dashed border-border p-5 text-sm text-muted-foreground">Selecione uma tarefa para gerenciar sua configuração.</div>}</aside></div>;
}

function TaskEditor({ task, onSaved, onError }: { task: ScheduledTaskAdminSummary; onSaved: (task: ScheduledTaskAdminSummary) => void; onError: (message: string | null) => void }) {
  const [localTime, setLocalTime] = useState(timeValue(task.local_time)); const [consent, setConsent] = useState(task.consent_confirmed); const [saving, setSaving] = useState(false);
  async function save(enabled: boolean) { const optimistic = { ...task, enabled, local_time: `${localTime}:00`, consent_confirmed: consent }; onError(null); onSaved(optimistic); setSaving(true); try { onSaved(await updateDailyAgendaTask(task.professional_id, { enabled, local_time: localTime, consent_confirmed: consent })); } catch (reason) { onSaved(task); onError(reason instanceof Error ? reason.message : "Não foi possível atualizar a tarefa. Tente novamente."); } finally { setSaving(false); } }
  return <section className="rounded-xl border border-border bg-card p-5 shadow-sm"><h2 className="font-semibold text-foreground">{task.professional_name}</h2><p className="mt-1 text-sm text-muted-foreground">Resumo diário · {task.timezone}</p><label className="mt-5 block text-sm text-muted-foreground">Horário local<input type="time" value={localTime} disabled={saving} onChange={(event) => setLocalTime(event.target.value)} className="mt-1.5 block rounded-md border border-border bg-background px-2 py-1.5 text-foreground" /></label><label className="mt-4 flex items-start gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={consent} disabled={saving} onChange={(event) => setConsent(event.target.checked)} className="mt-0.5 h-4 w-4" /><span>Consentimento confirmado</span></label>{task.readiness_issues.length > 0 && <p className="mt-4 rounded-md bg-amber-500/10 p-2 text-xs text-amber-800">{task.readiness_issues.join(" · ")}</p>}<div className="mt-5 flex gap-2"><button type="button" disabled={saving} onClick={() => void save(!task.enabled)} className={cn("rounded-md px-3 py-2 text-sm font-medium text-white disabled:opacity-50", task.enabled ? "bg-slate-600" : "bg-indigo-600")}>{task.enabled ? "Desativar" : "Ativar"}</button><button type="button" disabled={saving} onClick={() => void save(task.enabled)} className="rounded-md border border-border px-3 py-2 text-sm disabled:opacity-50">Salvar</button></div></section>;
}

function LogTab({ params, setParams }: { params: ReturnType<typeof useSearchParams>; setParams: (values: Record<string, string | undefined>) => void }) {
  const q = params.get("q") ?? ""; const status = params.get("status") ?? ""; const providerKey = params.get("provider_key") ?? ""; const hasError = params.get("has_error") ?? ""; const dateFrom = params.get("date_from") ?? ""; const dateTo = params.get("date_to") ?? ""; const page = Number(params.get("page") ?? "1");
  const [draft, setDraft] = useState(q); const [data, setData] = useState<{ runs: ScheduledTaskRunLogEntry[]; total: number; page: number; page_size: number } | null>(null); const [error, setError] = useState<string | null>(null);
  useEffect(() => { let active = true; const query: ScheduledTaskRunLogQuery = { q, status: status || undefined, provider_key: providerKey || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined, page, page_size: 20 }; if (hasError) query.has_error = hasError === "true"; void fetchScheduledTaskRuns(query).then((result) => { if (active) setData(result); }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Não foi possível carregar o histórico. Tente novamente."); }); return () => { active = false; }; }, [dateFrom, dateTo, hasError, page, providerKey, q, status]);
  function apply() { setParams({ tab: "logs", q: draft || undefined, page: undefined }); }
  return <section className="rounded-xl border border-border bg-card p-5 shadow-sm"><div className="flex flex-wrap gap-3"><div className="relative min-w-52 flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><input value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") apply(); }} placeholder="Buscar tenant" className="w-full rounded-md border border-border bg-background py-2 pl-9 pr-3 text-sm" /></div><select value={status} onChange={(event) => setParams({ tab: "logs", status: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm"><option value="">Todos os status</option><option value="delivered">Entregue</option><option value="failed">Falhou</option><option value="sent">Enviado</option><option value="skipped">Ignorado</option></select><select value={providerKey} onChange={(event) => setParams({ tab: "logs", provider_key: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm"><option value="">Todos os provedores</option><option value="ycloud">YCloud</option></select><select value={hasError} onChange={(event) => setParams({ tab: "logs", has_error: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm"><option value="">Todos os erros</option><option value="true">Com erro</option><option value="false">Sem erro</option></select><input type="date" value={dateFrom} onChange={(event) => setParams({ tab: "logs", date_from: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm" /><input type="date" value={dateTo} onChange={(event) => setParams({ tab: "logs", date_to: event.target.value || undefined, page: undefined })} className="rounded-md border border-border bg-background px-3 py-2 text-sm" /><button type="button" onClick={apply} className="rounded-md bg-muted px-3 py-2 text-sm font-medium">Filtrar</button></div>{error && <p className="mt-4 rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}<div className="mt-5 overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead className="border-b border-border text-xs uppercase text-muted-foreground"><tr><th className="px-2 py-3">Data</th><th className="px-2 py-3">Tenant</th><th className="px-2 py-3">Horário</th><th className="px-2 py-3">Status</th><th className="px-2 py-3">Tentativas</th><th className="px-2 py-3">Itens</th><th className="px-2 py-3">Provedor</th><th className="px-2 py-3">Entrega</th><th className="px-2 py-3">Erro</th></tr></thead><tbody>{data?.runs.map((run) => <tr key={run.id} className="border-b border-border/70"><td className="px-2 py-3">{new Intl.DateTimeFormat("pt-BR").format(new Date(`${run.target_local_date}T12:00:00`))}</td><td className="px-2 py-3 font-medium text-foreground">{run.professional_name}</td><td className="px-2 py-3">{run.scheduled_local_time}</td><td className="px-2 py-3"><span className={cn("rounded-full px-2 py-1 text-xs", statusClass(run.status))}>{statusLabel(run.status)}</span></td><td className="px-2 py-3">{run.attempt_count}</td><td className="px-2 py-3">{run.agenda_item_count ?? "—"}</td><td className="px-2 py-3">{run.provider_key ?? "—"}</td><td className="px-2 py-3">{formatDate(run.delivered_at ?? run.sent_at ?? run.accepted_at)}</td><td className="max-w-48 truncate px-2 py-3 text-xs text-muted-foreground" title={run.last_error_detail ?? undefined}>{run.last_error_code ?? "—"}</td></tr>)}</tbody></table>{data?.runs.length === 0 && <p className="py-10 text-center text-sm text-muted-foreground">Nenhuma execução encontrada.</p>}</div>{data && <Pager page={data.page} pageSize={data.page_size} total={data.total} onChange={(next) => setParams({ tab: "logs", page: String(next) })} />}</section>;
}
