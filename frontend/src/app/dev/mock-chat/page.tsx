"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  createMockCustomer,
  fetchConversation,
  fetchConversations,
  fetchMockConversation,
  fetchMockCustomers,
  processConversationNow,
  resetMockConversation,
  sendMockMessage,
} from "@/lib/api";
import { fetchSession } from "@/lib/auth";
import type { CandidateDetail, ConversationDetail, ConversationSummary, MockCustomer } from "@/lib/types";
import { AppShell } from "@/components/layout/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

const POLL_INTERVAL_MS = 1500;

export default function MockChatPage() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    let active = true;
    fetchSession().then((user) => {
      if (!active) return;
      if (!user) {
        router.replace("/login");
        return;
      }
      if (user.role === "platform_admin" && !user.professional_id) {
        router.replace("/admin/select-tenant");
        return;
      }
      setAuthed(!!user);
      setAuthChecked(true);
    });
    return () => {
      active = false;
    };
  }, [router]);

  if (!authChecked) return null;
  if (!authed) return null;
  return (
    <AppShell>
      <MockChat />
    </AppShell>
  );
}

function MockChat() {
  const [mode, setMode] = useState<"mock" | "live">("mock");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [instructorPhone, setInstructorPhone] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [mockCustomers, setMockCustomers] = useState<MockCustomer[]>([]);
  const [liveConversations, setLiveConversations] = useState<ConversationSummary[]>([]);
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [processing, setProcessing] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [creatingCustomer, setCreatingCustomer] = useState(false);

  // Polling and post-send refreshes can overlap; fetch responses aren't
  // guaranteed to resolve in request order. Only apply the response from
  // the most recently *initiated* request, so a slow stale response can't
  // clobber a newer one that already landed.
  const latestRequestId = useRef(0);
  const latestMockLoadId = useRef(0);

  const refresh = useCallback(async (id: string) => {
    const requestId = ++latestRequestId.current;
    const data = await fetchConversation(id);
    if (requestId === latestRequestId.current) {
      setConversation(data);
    }
  }, []);

  useEffect(() => {
    if (mode !== "mock") return;

    let active = true;
    Promise.all([fetchMockCustomers(), fetchMockConversation()]).then(([{ customers }, info]) => {
      if (!active) return;
      setMockCustomers(customers);
      setConversationId(info.conversation_id);
      setInstructorPhone(info.instructor_phone);
      setCustomerPhone(info.customer_phone);
      refresh(info.conversation_id);
    });
    return () => {
      active = false;
    };
  }, [mode, refresh]);

  useEffect(() => {
    if (mode !== "live") return;

    let active = true;
    fetchConversations().then(({ conversations }) => {
      if (!active) return;
      setLiveConversations(conversations);
      const latestConversation = conversations[0];
      if (!latestConversation) {
        setConversationId(null);
        return;
      }
      setConversationId(latestConversation.id);
      setCustomerPhone(latestConversation.contact_phone ?? "");
      setInstructorPhone("Conta WhatsApp Business");
      refresh(latestConversation.id);
    });
    return () => {
      active = false;
    };
  }, [mode, refresh]);

  useEffect(() => {
    if (!conversationId) return;
    const interval = setInterval(() => refresh(conversationId), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [conversationId, refresh]);

  async function handleSend(sender: "instructor" | "customer", text: string) {
    if (!customerPhone) return;
    await sendMockMessage(sender, text, customerPhone);
    if (conversationId) await refresh(conversationId);
  }

  async function handleProcessNow() {
    if (!conversationId) return;
    setProcessing(true);
    try {
      await processConversationNow(conversationId);
      await refresh(conversationId);
    } finally {
      setProcessing(false);
    }
  }

  async function handleRestart() {
    if (!conversationId) return;

    latestRequestId.current += 1;
    setConversation((current) => (current ? { ...current, messages: [], candidates: [] } : current));
    setRestarting(true);
    try {
      await resetMockConversation(customerPhone);
      await refresh(conversationId);
    } catch {
      await refresh(conversationId);
    } finally {
      setRestarting(false);
    }
  }

  async function handleMockCustomerChange(phone: string) {
    const loadId = ++latestMockLoadId.current;
    latestRequestId.current += 1;
    setConversationId(null);
    setConversation(null);
    setCustomerPhone(phone);
    const info = await fetchMockConversation(phone);
    if (loadId !== latestMockLoadId.current) return;
    setConversationId(info.conversation_id);
    setInstructorPhone(info.instructor_phone);
    setCustomerPhone(info.customer_phone);
    await refresh(info.conversation_id);
  }

  async function handleCreateMockCustomer() {
    setCreatingCustomer(true);
    try {
      const customer = await createMockCustomer();
      setMockCustomers((current) => [...current, customer]);
      await handleMockCustomerChange(customer.customer_phone);
    } finally {
      setCreatingCustomer(false);
    }
  }

  function handleLiveConversationChange(id: string) {
    const selectedConversation = liveConversations.find((conversation) => conversation.id === id);
    if (!selectedConversation) return;

    setConversationId(selectedConversation.id);
    setCustomerPhone(selectedConversation.contact_phone ?? "");
    setConversation(null);
    refresh(selectedConversation.id);
  }

  function handleModeChange(nextMode: "mock" | "live") {
    if (nextMode === mode) return;

    latestRequestId.current += 1;
    setConversationId(null);
    setConversation(null);
    setInstructorPhone("");
    setCustomerPhone("");
    setMockCustomers([]);
    setMode(nextMode);
  }

  const messages = conversation?.messages ?? [];
  const isMock = mode === "mock";
  const selectedMockCustomer = mockCustomers.find(
    (customer) => customer.customer_phone === customerPhone
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">WhatsApp Chat Inspector (dev)</h1>
          <p className="text-sm text-muted-foreground">
            {isMock
              ? "Simula ambos os lados da conversa para testar a extração, sem depender do WhatsApp real."
              : "Exibe conversas reais recebidas via webhook. Este modo é somente leitura."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border p-0.5">
            <Button size="sm" variant={isMock ? "default" : "ghost"} onClick={() => handleModeChange("mock")}>
              Mock
            </Button>
            <Button size="sm" variant={isMock ? "ghost" : "default"} onClick={() => handleModeChange("live")}>
              Ao vivo
            </Button>
          </div>
          {!isMock && (
            <select
              aria-label="Conversa ao vivo"
              className="h-8 max-w-64 rounded-lg border border-input bg-background px-2 text-sm"
              value={conversationId ?? ""}
              onChange={(event) => handleLiveConversationChange(event.target.value)}
            >
              {liveConversations.length === 0 ? (
                <option value="">Nenhuma conversa encontrada</option>
              ) : (
                liveConversations.map((liveConversation) => (
                  <option key={liveConversation.id} value={liveConversation.id}>
                    {liveConversation.contact_name}
                  </option>
                ))
              )}
            </select>
          )}
          {isMock && (
            <>
              <select
                aria-label="Cliente simulado"
                className="h-8 max-w-64 rounded-lg border border-input bg-background px-2 text-sm"
                value={customerPhone}
                onChange={(event) => handleMockCustomerChange(event.target.value)}
                disabled={creatingCustomer || restarting}
              >
                {mockCustomers.map((customer) => (
                  <option key={customer.customer_phone} value={customer.customer_phone}>
                    {customer.customer_name}
                  </option>
                ))}
              </select>
              <Button variant="outline" onClick={handleCreateMockCustomer} disabled={creatingCustomer}>
                {creatingCustomer ? "Gerando..." : "Novo cliente"}
              </Button>
              <Button
                variant="outline"
                onClick={handleRestart}
                disabled={!conversationId || restarting}
              >
                {restarting ? "Reiniciando..." : "Reiniciar conversa"}
              </Button>
            </>
          )}
          <Button onClick={handleProcessNow} disabled={!conversationId || processing || restarting}>
            {processing ? "Processando..." : "Processar agora"}
          </Button>
        </div>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <ChatPanel
          title={isMock ? selectedMockCustomer?.customer_name ?? "Cliente" : conversation?.contact_name ?? "Cliente"}
          phone={customerPhone}
          selfDirection="inbound"
          messages={messages}
          disabled={restarting}
          readOnly={!isMock}
          onSend={(text) => handleSend("customer", text)}
        />
        <ChatPanel
          title="Instrutor"
          phone={instructorPhone}
          selfDirection="outbound"
          messages={messages}
          disabled={restarting}
          readOnly={!isMock}
          onSend={(text) => handleSend("instructor", text)}
        />
      </div>

      <CandidatePanel candidates={conversation?.candidates ?? []} />
    </div>
  );
}

function ChatPanel({
  title,
  phone,
  selfDirection,
  messages,
  disabled,
  readOnly,
  onSend,
}: {
  title: string;
  phone: string;
  selfDirection: "inbound" | "outbound";
  messages: ConversationDetail["messages"];
  disabled: boolean;
  readOnly: boolean;
  onSend: (text: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    onSend(draft.trim());
    setDraft("");
  }

  return (
    <Card className="flex h-[28rem] flex-col">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <p className="text-xs text-muted-foreground">{phone}</p>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
        <ScrollArea className="min-h-0 flex-1 rounded-lg bg-muted/30 p-2">
          <div className="flex flex-col gap-1.5">
            {messages.map((m) => {
              const isSelf = m.direction === selfDirection;
              return (
                <div
                  key={m.id}
                  className={`max-w-[75%] rounded-lg px-3 py-1.5 text-sm ${
                    isSelf
                      ? "self-end bg-primary text-primary-foreground"
                      : "self-start bg-card ring-1 ring-foreground/10"
                  }`}
                >
                  {m.text}
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
        {readOnly ? (
          <p className="text-xs text-muted-foreground">Modo ao vivo: somente leitura.</p>
        ) : (
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Mensagem..."
              disabled={disabled}
            />
            <Button type="submit" disabled={disabled}>Enviar</Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function CandidatePanel({ candidates }: { candidates: CandidateDetail[] }) {
  const latestCandidate = candidates[0];

  return (
    <Card className="flex min-h-[32rem] shrink-0 flex-col">
      <CardHeader>
        <CardTitle>Última extração</CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-hidden">
        {!latestCandidate ? (
          <p className="text-sm text-muted-foreground">
            Nenhum candidato detectado ainda. Envie mensagens e clique em &quot;Processar agora&quot;.
          </p>
        ) : (
          <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-2">
            <ExtractionColumn candidates={candidates} />
            <CandidateColumn candidate={latestCandidate} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ExtractionColumn({ candidates }: { candidates: CandidateDetail[] }) {
  return (
    <section className="flex min-h-0 flex-col rounded-lg border p-3">
      <h2 className="text-sm font-medium">Eventos extraídos pelo LLM</h2>
      <p className="mt-1 text-xs text-muted-foreground">Histórico de intenções e entidades, do mais recente ao mais antigo</p>
      <ScrollArea className="mt-3 min-h-0 flex-1 pr-3">
        <div className="flex flex-col gap-2 text-sm">
          {candidates.map((candidate) => (
            <div key={candidate.id} className="rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{candidate.action}</Badge>
                <Badge variant="outline">confiança {candidate.confidence?.toFixed(2)}</Badge>
                <span className="text-xs text-muted-foreground">
                  {new Date(candidate.created_at).toLocaleString("pt-BR")}
                </span>
              </div>
              <div className="mt-2 flex flex-col gap-1">
                <ExtractionField label="Início" value={formatDateTime(candidate.proposed_start_at)} />
                <ExtractionField label="Fim" value={formatDateTime(candidate.proposed_end_at)} />
                <ExtractionField label="Serviço" value={candidate.service} />
                <Ambiguities ambiguities={candidate.ambiguities} />
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </section>
  );
}

function CandidateColumn({ candidate }: { candidate: CandidateDetail }) {
  return (
    <section className="flex min-h-0 flex-col rounded-lg border p-3">
      <h2 className="text-sm font-medium">Evidências do pipeline</h2>
      <p className="mt-1 text-xs text-muted-foreground">Mensagens que sustentam o evento detectado</p>
      <ScrollArea className="mt-3 min-h-0 flex-1 pr-3">
        <div className="flex flex-col gap-2 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge>{candidate.action}</Badge>
            <Badge variant="outline">confiança {candidate.confidence?.toFixed(2)}</Badge>
            <Badge variant="secondary">{candidate.status}</Badge>
          </div>
          <div>
            <p className="text-muted-foreground">Evidências:</p>
            <ul className="mt-1 list-disc pl-5">
              {candidate.evidence.map((e) => (
                <li key={e.message_id}>
                  [{e.direction}] {e.text}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </ScrollArea>
    </section>
  );
}

function ExtractionField({ label, value }: { label: string; value: string | null }) {
  return (
    <p>
      <span className="text-muted-foreground">{label}: </span>
      {value ?? "—"}
    </p>
  );
}

function Ambiguities({ ambiguities }: { ambiguities: CandidateDetail["ambiguities"] }) {
  if (ambiguities.length === 0) return null;

  return (
    <div>
      <p className="text-muted-foreground">Ambiguidades:</p>
      <ul className="mt-1 list-disc pl-5">
        {ambiguities.map((ambiguity, index) => (
          <li key={`${ambiguity.field}-${index}`}>
            <span className="font-medium">{ambiguity.field}</span>: {ambiguity.description}
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatDateTime(value: string | null): string | null {
  return value ? new Date(value).toLocaleString("pt-BR") : null;
}
