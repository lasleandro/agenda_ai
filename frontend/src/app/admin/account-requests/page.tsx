"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  ExternalLink,
  MailCheck,
  RotateCcw,
  X,
} from "lucide-react";

import { PlatformAdminHeader } from "@/components/admin/platform-admin-header";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { WhatsappField } from "@/components/ui/whatsapp-field";
import {
  approveAccountRequest,
  fetchAccountRequests,
  rejectAccountRequest,
  resendAccountActivation,
} from "@/lib/api";
import { fetchSession, impersonate } from "@/lib/auth";
import { TENANT_TIMEZONES } from "@/lib/tenant-timezones";
import type {
  AccountActivationState,
  AccountRequestAdminItem,
  AccountRequestAdminListResponse,
  AccountRequestStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

const statusCopy: Record<AccountRequestStatus, string> = {
  pending: "Pendente",
  approved: "Aprovada",
  rejected: "Rejeitada",
};

const activationCopy: Record<AccountActivationState, string> = {
  not_queued: "Não enviada",
  queued: "Na fila",
  processing: "Processando",
  retry_wait: "Nova tentativa",
  sent: "Enviada",
  failed: "Falhou",
  suppressed: "Suprimida",
  account_activated: "Conta ativada",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusClass(status: AccountRequestStatus): string {
  if (status === "approved") return "bg-emerald-500/10 text-emerald-700";
  if (status === "rejected") return "bg-destructive/10 text-destructive";
  return "bg-amber-500/10 text-amber-700";
}

function activationClass(state: AccountActivationState): string {
  if (state === "account_activated" || state === "sent") {
    return "bg-emerald-500/10 text-emerald-700";
  }
  if (state === "failed" || state === "suppressed") {
    return "bg-destructive/10 text-destructive";
  }
  return "bg-muted text-muted-foreground";
}

const ACTIVATION_IN_FLIGHT: AccountActivationState[] = [
  "queued",
  "processing",
  "retry_wait",
];

// The control stays visible on every approved row until the owner activates, so
// admins always see the affordance. It is only disabled while a delivery is
// already in flight — the backend no-ops in that case anyway.
function resendVisible(
  status: AccountRequestStatus,
  state: AccountActivationState | null
): boolean {
  return status === "approved" && state !== "account_activated";
}

function resendDisabled(state: AccountActivationState | null): boolean {
  return state === null || ACTIVATION_IN_FLIGHT.includes(state);
}

export default function AccountRequestsPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [adminEmail, setAdminEmail] = useState<string | null>(null);
  const [status, setStatus] = useState<AccountRequestStatus>("pending");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AccountRequestAdminListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selected, setSelected] = useState<AccountRequestAdminItem | null>(null);
  const [approving, setApproving] = useState<AccountRequestAdminItem | null>(null);
  const [rejecting, setRejecting] = useState<AccountRequestAdminItem | null>(null);
  const [tenantName, setTenantName] = useState("");
  const [approvalWhatsapp, setApprovalWhatsapp] = useState("");
  const [timezone, setTimezone] = useState<(typeof TENANT_TIMEZONES)[number]>(
    "America/Sao_Paulo"
  );
  const [rejectionReason, setRejectionReason] = useState("");
  const [pendingDecisionId, setPendingDecisionId] = useState<string | null>(null);
  const [createdTenant, setCreatedTenant] = useState<{ id: string; name: string } | null>(
    null
  );
  const latestRequest = useRef(0);

  const loadRequests = useCallback(
    async (nextStatus: AccountRequestStatus, nextPage: number) => {
      const requestId = ++latestRequest.current;
      setLoading(true);
      setError(null);
      try {
        const result = await fetchAccountRequests({
          status: nextStatus,
          page: nextPage,
          pageSize: PAGE_SIZE,
        });
        if (requestId !== latestRequest.current) return;
        if (result.total_pages > 0 && nextPage > result.total_pages) {
          setPage(result.total_pages);
          return;
        }
        setData(result);
      } catch (reason) {
        if (requestId === latestRequest.current) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Não foi possível carregar as solicitações."
          );
        }
      } finally {
        if (requestId === latestRequest.current) setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    let active = true;
    void fetchSession().then((user) => {
      if (!active) return;
      if (!user) {
        router.replace("/login");
      } else if (user.role !== "platform_admin") {
        router.replace("/agenda");
      } else {
        setAdminEmail(user.email);
        setAuthorized(true);
      }
    });
    return () => {
      active = false;
    };
  }, [router]);

  useEffect(() => {
    if (!authorized) return;
    const timer = window.setTimeout(() => void loadRequests(status, page), 0);
    return () => window.clearTimeout(timer);
  }, [authorized, loadRequests, page, status]);

  function selectStatus(nextStatus: AccountRequestStatus) {
    setStatus(nextStatus);
    setPage(1);
    setSuccess(null);
    setCreatedTenant(null);
  }

  function openApproval(request: AccountRequestAdminItem) {
    setTenantName(request.proposed_tenant_name);
    setApprovalWhatsapp(request.whatsapp ?? "");
    setTimezone("America/Sao_Paulo");
    setApproving(request);
    setError(null);
  }

  function applyOptimisticDecision(
    request: AccountRequestAdminItem,
    nextStatus: "approved" | "rejected"
  ): AccountRequestAdminListResponse | null {
    const snapshot = data;
    setData((current) => {
      if (!current) return current;
      const status_counts = {
        ...current.status_counts,
        pending: Math.max(0, current.status_counts.pending - 1),
        [nextStatus]: current.status_counts[nextStatus] + 1,
      };
      return {
        ...current,
        requests:
          status === "pending"
            ? current.requests.filter((item) => item.id !== request.id)
            : current.requests.map((item) =>
                item.id === request.id ? { ...item, status: nextStatus } : item
              ),
        total: status === "pending" ? Math.max(0, current.total - 1) : current.total,
        status_counts,
      };
    });
    return snapshot;
  }

  async function approve() {
    if (!approving || !tenantName.trim() || !approvalWhatsapp) return;
    const request = approving;
    const snapshot = applyOptimisticDecision(request, "approved");
    setApproving(null);
    setPendingDecisionId(request.id);
    setError(null);
    try {
      const result = await approveAccountRequest(request.id, {
        tenant_name: tenantName.trim(),
        whatsapp: approvalWhatsapp,
        timezone,
      });
      if (result.tenant) {
        setCreatedTenant({ id: result.tenant.id, name: result.tenant.name });
        setSuccess(
          `${result.tenant.name} foi criado. A ativação de ${result.request.email} está na fila.`
        );
      }
      await loadRequests(status, page);
    } catch (reason) {
      setData(snapshot);
      setError(
        reason instanceof Error ? reason.message : "Não foi possível aprovar a solicitação."
      );
    } finally {
      setPendingDecisionId(null);
    }
  }

  async function reject() {
    if (!rejecting) return;
    const request = rejecting;
    const snapshot = applyOptimisticDecision(request, "rejected");
    setRejecting(null);
    setPendingDecisionId(request.id);
    setError(null);
    try {
      await rejectAccountRequest(request.id, rejectionReason.trim());
      setSuccess(`Solicitação de ${request.email} rejeitada.`);
      await loadRequests(status, page);
    } catch (reason) {
      setData(snapshot);
      setError(
        reason instanceof Error ? reason.message : "Não foi possível rejeitar a solicitação."
      );
    } finally {
      setPendingDecisionId(null);
      setRejectionReason("");
    }
  }

  async function resend(request: AccountRequestAdminItem) {
    const previous = request.activation_state;
    setPendingDecisionId(request.id);
    setError(null);
    setData((current) =>
      current
        ? {
            ...current,
            requests: current.requests.map((item) =>
              item.id === request.id ? { ...item, activation_state: "queued" } : item
            ),
          }
        : current
    );
    try {
      const result = await resendAccountActivation(request.id);
      setData((current) =>
        current
          ? {
              ...current,
              requests: current.requests.map((item) =>
                item.id === request.id
                  ? { ...item, activation_state: result.activation_state }
                  : item
              ),
            }
          : current
      );
      setSuccess(`Ativação de ${request.email} colocada na fila.`);
    } catch (reason) {
      setData((current) =>
        current
          ? {
              ...current,
              requests: current.requests.map((item) =>
                item.id === request.id ? { ...item, activation_state: previous } : item
              ),
            }
          : current
      );
      setError(
        reason instanceof Error ? reason.message : "Não foi possível reenviar a ativação."
      );
    } finally {
      setPendingDecisionId(null);
    }
  }

  async function accessCreatedTenant() {
    if (!createdTenant) return;
    try {
      await impersonate(createdTenant.id);
      router.replace("/agenda");
    } catch {
      setError("Não foi possível acessar o tenant criado.");
    }
  }

  if (!authorized) return null;

  return (
    <main className="min-h-dvh w-full bg-[var(--bg-page)] px-4 py-8 sm:px-6 sm:py-10">
      <div className="mx-auto max-w-6xl">
        <PlatformAdminHeader
          active="requests"
          adminEmail={adminEmail}
          pendingCount={data?.status_counts.pending}
        />

        <div className="mb-7 flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-500 text-white">
            <ClipboardList className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Solicitações de conta
            </h1>
            <p className="text-sm text-muted-foreground">
              Analise pedidos antes de criar o tenant e enviar a ativação.
            </p>
          </div>
        </div>

        {success && (
          <div
            className="mb-4 flex flex-wrap items-center gap-3 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700"
            role="status"
          >
            <span>{success}</span>
            {createdTenant && (
              <>
                <button
                  type="button"
                  onClick={() => void accessCreatedTenant()}
                  className="inline-flex items-center gap-1 font-medium underline"
                >
                  Acessar tenant <ExternalLink className="h-3.5 w-3.5" />
                </button>
                <Link href="/admin/select-tenant" className="font-medium underline">
                  Ver tenants
                </Link>
              </>
            )}
          </div>
        )}
        {error && (
          <p
            className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
          >
            {error}
          </p>
        )}

        <nav className="mb-5 flex gap-1 overflow-x-auto border-b border-border" aria-label="Status das solicitações">
          {(["pending", "approved", "rejected"] as const).map((itemStatus) => (
            <button
              key={itemStatus}
              type="button"
              onClick={() => selectStatus(itemStatus)}
              aria-current={status === itemStatus ? "page" : undefined}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-4 py-2.5 text-sm font-medium",
                status === itemStatus
                  ? "border-indigo-500 text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {statusCopy[itemStatus]}
              {data && (
                <span className="ml-1.5 text-xs">({data.status_counts[itemStatus]})</span>
              )}
            </button>
          ))}
        </nav>

        <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead className="border-b border-border bg-muted/40 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Solicitante</th>
                  <th className="px-4 py-3">Enviada em</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Ativação</th>
                  <th className="px-4 py-3 text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {data?.requests.map((request) => (
                  <RequestRow
                    key={request.id}
                    request={request}
                    busy={pendingDecisionId === request.id}
                    onDetails={setSelected}
                    onApprove={openApproval}
                    onReject={(item) => {
                      setRejectionReason("");
                      setRejecting(item);
                    }}
                    onResend={(item) => void resend(item)}
                  />
                ))}
              </tbody>
            </table>
          </div>

          <div className="divide-y divide-border md:hidden">
            {data?.requests.map((request) => (
              <RequestCard
                key={request.id}
                request={request}
                busy={pendingDecisionId === request.id}
                onDetails={setSelected}
                onApprove={openApproval}
                onReject={(item) => {
                  setRejectionReason("");
                  setRejecting(item);
                }}
                onResend={(item) => void resend(item)}
              />
            ))}
          </div>

          {!loading && data?.requests.length === 0 && (
            <p className="px-5 py-12 text-center text-sm text-muted-foreground">
              Nenhuma solicitação {statusCopy[status].toLowerCase()}.
            </p>
          )}
          {loading && !data && (
            <p className="px-5 py-12 text-center text-sm text-muted-foreground">
              Carregando solicitações...
            </p>
          )}

          {data && data.total > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-sm text-muted-foreground">
              <span>
                {(data.page - 1) * data.page_size + 1}–
                {Math.min(data.page * data.page_size, data.total)} de {data.total}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  aria-label="Página anterior"
                  disabled={data.page <= 1 || loading}
                  onClick={() => setPage((current) => current - 1)}
                  className="rounded-md border border-border p-1.5 disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span>
                  {data.page} de {Math.max(data.total_pages, 1)}
                </span>
                <button
                  type="button"
                  aria-label="Próxima página"
                  disabled={data.page >= data.total_pages || loading}
                  onClick={() => setPage((current) => current + 1)}
                  className="rounded-md border border-border p-1.5 disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      <RequestDetailsDialog request={selected} onClose={() => setSelected(null)} />

      <Dialog open={approving !== null} onOpenChange={(open) => !open && setApproving(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Aprovar e criar tenant</DialogTitle>
            <DialogDescription>
              O tenant e seu proprietário serão criados juntos. A ativação será enviada
              para o email solicitado.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="approval-tenant-name">Nome do tenant</Label>
              <Input
                id="approval-tenant-name"
                value={tenantName}
                onChange={(event) => setTenantName(event.target.value)}
                minLength={2}
                maxLength={255}
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label>Email do proprietário</Label>
              <Input value={approving?.email ?? ""} readOnly disabled />
            </div>
            <WhatsappField
              id="approval-whatsapp"
              label="WhatsApp da operação"
              value={approvalWhatsapp}
              onChange={setApprovalWhatsapp}
              hint="Pré-preenchido com o número solicitado. Ajuste se necessário."
            />
            <div className="space-y-1.5">
              <Label htmlFor="approval-timezone">Fuso horário</Label>
              <select
                id="approval-timezone"
                value={timezone}
                onChange={(event) =>
                  setTimezone(event.target.value as (typeof TENANT_TIMEZONES)[number])
                }
                className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {TENANT_TIMEZONES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setApproving(null)}>
              Cancelar
            </Button>
            <Button
              type="button"
              disabled={tenantName.trim().length < 2 || !approvalWhatsapp}
              onClick={() => void approve()}
            >
              <Check className="h-4 w-4" /> Aprovar e criar tenant
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejecting !== null} onOpenChange={(open) => !open && setRejecting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rejeitar solicitação</DialogTitle>
            <DialogDescription>
              A rejeição não cria tenant, usuário ou email de ativação.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-2">
            <Label htmlFor="rejection-reason">Motivo interno (opcional)</Label>
            <textarea
              id="rejection-reason"
              value={rejectionReason}
              onChange={(event) => setRejectionReason(event.target.value)}
              maxLength={500}
              rows={4}
              autoFocus
              className="w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <p className="text-right text-xs text-muted-foreground">
              {rejectionReason.length}/500
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setRejecting(null)}>
              Cancelar
            </Button>
            <Button type="button" variant="destructive" onClick={() => void reject()}>
              <X className="h-4 w-4" /> Rejeitar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

interface RequestActionsProps {
  request: AccountRequestAdminItem;
  busy: boolean;
  onDetails: (request: AccountRequestAdminItem) => void;
  onApprove: (request: AccountRequestAdminItem) => void;
  onReject: (request: AccountRequestAdminItem) => void;
  onResend: (request: AccountRequestAdminItem) => void;
}

function RequestActions({
  request,
  busy,
  onDetails,
  onApprove,
  onReject,
  onResend,
}: RequestActionsProps) {
  return (
    <div className="flex flex-wrap justify-end gap-2">
      <button
        type="button"
        onClick={() => onDetails(request)}
        className="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
      >
        Detalhes
      </button>
      {request.status === "pending" && (
        <>
          <button
            type="button"
            disabled={busy}
            onClick={() => onReject(request)}
            className="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
          >
            Rejeitar
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onApprove(request)}
            className="rounded-md bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Aprovar
          </button>
        </>
      )}
      {resendVisible(request.status, request.activation_state) && (
        <button
          type="button"
          disabled={busy || resendDisabled(request.activation_state)}
          title={
            resendDisabled(request.activation_state)
              ? "Envio de ativação em andamento"
              : undefined
          }
          onClick={() => onResend(request)}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Reenviar ativação
        </button>
      )}
    </div>
  );
}

function RequestRow(props: RequestActionsProps) {
  const { request } = props;
  return (
    <tr className="border-b border-border/70 last:border-0">
      <td className="px-4 py-3">
        <span className="block font-medium text-foreground">
          {request.proposed_tenant_name}
        </span>
        <span className="text-xs text-muted-foreground">{request.email}</span>
      </td>
      <td className="px-4 py-3 text-muted-foreground">{formatDate(request.submitted_at)}</td>
      <td className="px-4 py-3">
        <span className={cn("rounded-full px-2 py-1 text-xs", statusClass(request.status))}>
          {statusCopy[request.status]}
        </span>
      </td>
      <td className="px-4 py-3">
        {request.activation_state ? (
          <span
            className={cn(
              "rounded-full px-2 py-1 text-xs",
              activationClass(request.activation_state)
            )}
          >
            {activationCopy[request.activation_state]}
          </span>
        ) : (
          "—"
        )}
      </td>
      <td className="px-4 py-3">
        <RequestActions {...props} />
      </td>
    </tr>
  );
}

function RequestCard(props: RequestActionsProps) {
  const { request } = props;
  return (
    <article className="space-y-3 p-4">
      <div>
        <h2 className="font-medium text-foreground">{request.proposed_tenant_name}</h2>
        <p className="text-sm text-muted-foreground">{request.email}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{formatDate(request.submitted_at)}</span>
        <span className={cn("rounded-full px-2 py-1", statusClass(request.status))}>
          {statusCopy[request.status]}
        </span>
        {request.activation_state && (
          <span className={cn("rounded-full px-2 py-1", activationClass(request.activation_state))}>
            {activationCopy[request.activation_state]}
          </span>
        )}
      </div>
      <RequestActions {...props} />
    </article>
  );
}

function RequestDetailsDialog({
  request,
  onClose,
}: {
  request: AccountRequestAdminItem | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Detalhes da solicitação</DialogTitle>
          <DialogDescription>
            Dados enviados pelo solicitante e histórico da decisão.
          </DialogDescription>
        </DialogHeader>
        {request && (
          <dl className="grid gap-4 py-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">Nome proposto</dt>
              <dd className="mt-1 font-medium text-foreground">
                {request.proposed_tenant_name}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Email</dt>
              <dd className="mt-1 break-all font-medium text-foreground">{request.email}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">WhatsApp</dt>
              <dd className="mt-1 font-medium text-foreground">{request.whatsapp ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Enviada em</dt>
              <dd className="mt-1">{formatDate(request.submitted_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Status</dt>
              <dd className="mt-1">{statusCopy[request.status]}</dd>
            </div>
            {request.message && (
              <div className="sm:col-span-2">
                <dt className="text-xs text-muted-foreground">Mensagem</dt>
                <dd className="mt-1 whitespace-pre-wrap rounded-md bg-muted p-3">
                  {request.message}
                </dd>
              </div>
            )}
            {request.reviewed_at && (
              <div>
                <dt className="text-xs text-muted-foreground">Revisada em</dt>
                <dd className="mt-1">{formatDate(request.reviewed_at)}</dd>
              </div>
            )}
            {request.reviewer_email && (
              <div>
                <dt className="text-xs text-muted-foreground">Revisada por</dt>
                <dd className="mt-1 break-all">{request.reviewer_email}</dd>
              </div>
            )}
            {request.decision_reason && (
              <div className="sm:col-span-2">
                <dt className="text-xs text-muted-foreground">Motivo interno</dt>
                <dd className="mt-1 whitespace-pre-wrap">{request.decision_reason}</dd>
              </div>
            )}
            {request.activation_state && (
              <div className="sm:col-span-2 flex items-center gap-2">
                <MailCheck className="h-4 w-4 text-muted-foreground" />
                <span>Ativação: {activationCopy[request.activation_state]}</span>
              </div>
            )}
          </dl>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Fechar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
