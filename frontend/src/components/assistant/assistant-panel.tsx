"use client";

import { useEffect, useRef, useState } from "react";
import { Check, SendHorizontal, Sparkles, X } from "lucide-react";

import {
  confirmAssistantCandidate,
  rejectAssistantCandidate,
  sendAssistantMessage,
} from "@/lib/api";
import { notifyAgendaChanged } from "@/lib/agenda-events";
import { cn } from "@/lib/utils";
import type {
  AssistantMessage,
  AssistantToolCallTrace,
  PendingActionCandidate,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

type CandidateStatus = "pending" | "executed" | "rejected" | "failed";

type DisplayMessage = AssistantMessage & {
  id: string;
  toolCalls?: AssistantToolCallTrace[];
  pendingCandidate?: PendingActionCandidate;
  candidateStatus?: CandidateStatus;
  candidateSummary?: string;
};

const EXAMPLE_PROMPTS = [
  "Quais alunos tenho marcado hoje?",
  "Amanhã de tarde tenho vaga? Que horários?",
];

const CANDIDATE_STATUS_LABELS: Record<CandidateStatus, string> = {
  pending: "Aguardando confirmação",
  executed: "Confirmado",
  rejected: "Cancelado",
  failed: "Falhou",
};

const CANDIDATE_STATUS_COLORS: Record<CandidateStatus, string> = {
  pending: "bg-amber-100 text-amber-800 border-amber-200",
  executed: "bg-emerald-100 text-emerald-800 border-emerald-200",
  rejected: "bg-gray-100 text-gray-600 border-gray-200",
  failed: "bg-red-100 text-red-800 border-red-200",
};

export function AssistantPanel({
  onClose,
}: {
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, sending]);

  async function handleSend(text: string) {
    const userMessage: DisplayMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setDraft("");
    setError(null);
    setSending(true);
    try {
      const recentCandidateIds = nextMessages
        .filter(
          (message) =>
            message.pendingCandidate &&
            message.candidateStatus &&
            ["executed", "rejected", "failed"].includes(message.candidateStatus)
        )
        .map((message) => message.pendingCandidate!.id)
        .slice(-5);
      const response = await sendAssistantMessage(
        nextMessages.map(({ role, content }) => ({ role, content })),
        recentCandidateIds
      );
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: response.reply,
          toolCalls: response.tool_calls,
          pendingCandidate: response.pending_candidate ?? undefined,
          candidateStatus: response.pending_candidate ? "pending" : undefined,
        },
      ]);
    } catch {
      setError("Não foi possível falar com o assistente. Tente novamente.");
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || sending) return;
    handleSend(draft.trim());
  }

  function handleCandidateResolved(
    messageId: string,
    status: CandidateStatus,
    summary: string
  ) {
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId
          ? { ...message, candidateStatus: status, candidateSummary: summary }
          : message
      )
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex h-16 shrink-0 items-center justify-between border-b px-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Assistente</span>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} title="Fechar">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1 p-3">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center">
            <p className="text-sm text-muted-foreground">
              Pergunte sobre sua agenda em português. Consultas respondem na
              hora; pedidos de alteração aparecem como uma proposta que você
              confirma antes de valer.
            </p>
            <div className="flex flex-col gap-1.5 w-full">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleSend(prompt)}
                  className="rounded-md border px-3 py-2 text-left text-xs text-muted-foreground hover:bg-muted"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onCandidateResolved={(status, summary) =>
                  handleCandidateResolved(message.id, status, summary)
                }
              />
            ))}
            {sending && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>

      {error && <p className="px-3 pb-1 text-xs text-destructive">{error}</p>}

      <form onSubmit={handleSubmit} className="flex shrink-0 gap-2 border-t p-3">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Pergunte algo sobre sua agenda..."
          disabled={sending}
        />
        <Button type="submit" size="icon" disabled={sending || !draft.trim()}>
          <SendHorizontal className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}

function MessageBubble({
  message,
  onCandidateResolved,
}: {
  message: DisplayMessage;
  onCandidateResolved: (status: CandidateStatus, summary: string) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex flex-col gap-1.5", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-3 py-1.5 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolTrace toolCalls={message.toolCalls} />
        )}
      </div>
      {message.pendingCandidate && (
        <ActionPreviewCard
          candidate={message.pendingCandidate}
          status={message.candidateStatus ?? "pending"}
          summary={message.candidateSummary}
          onResolved={onCandidateResolved}
        />
      )}
    </div>
  );
}

function ActionPreviewCard({
  candidate,
  status,
  summary,
  onResolved,
}: {
  candidate: PendingActionCandidate;
  status: CandidateStatus;
  summary?: string;
  onResolved: (status: CandidateStatus, summary: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirm() {
    setBusy(true);
    setError(null);
    try {
      const result = await confirmAssistantCandidate(candidate.id);
      if (result.status === "executed") {
        notifyAgendaChanged();
      }
      onResolved(result.status === "executed" ? "executed" : "failed", result.summary);
    } catch {
      setError("Não foi possível confirmar. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    setBusy(true);
    setError(null);
    try {
      const result = await rejectAssistantCandidate(candidate.id);
      onResolved("rejected", result.summary);
    } catch {
      setError("Não foi possível cancelar. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-[85%] rounded-lg border bg-card p-3 text-sm">
      <div className="flex items-center justify-between gap-2">
        <Badge
          variant="outline"
          className={cn("font-medium", CANDIDATE_STATUS_COLORS[status])}
        >
          {CANDIDATE_STATUS_LABELS[status]}
        </Badge>
      </div>
      <p className="mt-2 text-foreground">{candidate.preview_text}</p>
      {status === "pending" ? (
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={handleReject} disabled={busy}>
            <X className="h-3.5 w-3.5" />
            Cancelar
          </Button>
          <Button size="sm" onClick={handleConfirm} disabled={busy}>
            <Check className="h-3.5 w-3.5" />
            {busy ? "Confirmando..." : "Confirmar"}
          </Button>
        </div>
      ) : (
        summary && <p className="mt-2 text-xs text-muted-foreground">{summary}</p>
      )}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  );
}

function ToolTrace({ toolCalls }: { toolCalls: AssistantToolCallTrace[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="mt-1.5 border-t border-foreground/10 pt-1.5">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
      >
        {expanded ? "Ocultar" : "Ver"} ferramentas usadas ({toolCalls.length})
      </button>
      {expanded && (
        <ul className="mt-1 flex flex-col gap-1 text-[11px] text-muted-foreground">
          {toolCalls.map((call, index) => (
            <li key={`${call.name}-${index}`}>
              <span className="font-mono">{call.name}</span>(
              {JSON.stringify(call.arguments)}) → {call.result_summary}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex w-fit items-center gap-1 self-start rounded-lg bg-muted px-3 py-2">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-foreground/40 [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-foreground/40 [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-foreground/40" />
    </div>
  );
}
