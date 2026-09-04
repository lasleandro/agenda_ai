"use client";

import { useState, type FormEvent } from "react";
import { Mail, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { WhatsappField } from "@/components/ui/whatsapp-field";
import { submitAccountRequest } from "@/lib/api";

interface AccountRequestFormProps {
  idPrefix: string;
  autoFocus?: boolean;
}

export function AccountRequestForm({
  idPrefix,
  autoFocus = false,
}: AccountRequestFormProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!whatsapp) {
      setError("Informe o número de WhatsApp da operação.");
      return;
    }
    setSubmitting(true);
    try {
      await submitAccountRequest({
        proposed_tenant_name: name,
        email,
        whatsapp,
        message: message || null,
      });
      setSubmitted(true);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível enviar a solicitação."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div
        className="rounded-lg bg-emerald-500/10 px-4 py-4 text-sm text-emerald-700"
        role="status"
        aria-live="polite"
      >
        <p className="font-medium">Solicitação recebida.</p>
        <p className="mt-1">
          Se os dados estiverem corretos, nossa equipe entrará em contato ou
          enviará as instruções de acesso.
        </p>
      </div>
    );
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-name`}>Nome profissional ou da operação</Label>
        <div className="relative">
          <User className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id={`${idPrefix}-name`}
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="name"
            autoFocus={autoFocus}
            minLength={2}
            maxLength={255}
            required
            className="h-10 pl-9"
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-email`}>Email</Label>
        <div className="relative">
          <Mail className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id={`${idPrefix}-email`}
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            maxLength={255}
            required
            className="h-10 pl-9"
          />
        </div>
      </div>

      <WhatsappField
        id={`${idPrefix}-whatsapp`}
        value={whatsapp}
        onChange={setWhatsapp}
      />

      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-message`}>Mensagem (opcional)</Label>
        <textarea
          id={`${idPrefix}-message`}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          maxLength={1000}
          rows={3}
          className="w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />
        <p className="text-right text-xs text-muted-foreground">
          {message.length}/1000
        </p>
      </div>

      {error && (
        <p
          className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}

      <Button
        className="h-10 w-full text-[15px]"
        type="submit"
        disabled={submitting}
      >
        {submitting ? "Enviando..." : "Enviar solicitação"}
      </Button>
    </form>
  );
}

