"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Check, Clock, MessageSquare, ShieldCheck, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  fetchAgentBindingState,
  fetchWhatsappConnectionRequestState,
  requestAgentBindingChallenge,
  revokeAgentBinding,
  submitWhatsappConnectionRequest,
} from "@/lib/api";
import type {
  AgentBindingChallengeResponse,
  AgentBindingState,
} from "@/lib/types";
import whatsappCircular from "../../../../../assets/whatsapp_circular.png";

const WHATSAPP_BUSINESS_HELP_URL = "https://faq.whatsapp.com/1344487902959714";

const connectionSteps: { label: React.ReactNode; upcoming?: boolean }[] = [
  {
    label: (
      <>
        Transforme o número que você usa com seus alunos em uma conta do WhatsApp
        Business.{" "}
        <a
          href={WHATSAPP_BUSINESS_HELP_URL}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-foreground"
        >
          Veja como
        </a>
        .
      </>
    ),
  },
  {
    label: "Solicite a conexão à nossa equipe, que ativa o número para você.",
  },
  {
    label: "Conecte e autorize o número direto por aqui, sem precisar da nossa equipe.",
    upcoming: true,
  },
];

export default function WhatsAppPage() {
  const [requested, setRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [binding, setBinding] = useState<AgentBindingState | null>(null);
  const [challenge, setChallenge] =
    useState<AgentBindingChallengeResponse | null>(null);
  const [bindingError, setBindingError] = useState<string | null>(null);

  useEffect(() => {
    fetchWhatsappConnectionRequestState()
      .then((state) => setRequested(state.requested))
      .catch(() => {});
    fetchAgentBindingState()
      .then(setBinding)
      .catch(() => {});
  }, []);

  const handleRequestConnection = () => {
    setError(null);
    setRequested(true);
    submitWhatsappConnectionRequest().catch(() => {
      setRequested(false);
      setError("Não foi possível enviar sua solicitação agora. Tente novamente.");
    });
  };

  const handleGenerateCode = () => {
    setBindingError(null);
    requestAgentBindingChallenge()
      .then(setChallenge)
      .catch(() =>
        setBindingError(
          "Não foi possível gerar o código agora. Tente novamente."
        )
      );
  };

  const handleCheckBinding = () => {
    fetchAgentBindingState()
      .then((state) => {
        setBinding(state);
        if (state.bound) setChallenge(null);
      })
      .catch(() => {});
  };

  const handleRevokeBinding = () => {
    const previous = binding;
    setBinding(
      previous
        ? { ...previous, bound: false, confirmed_at: null }
        : previous
    );
    setChallenge(null);
    revokeAgentBinding()
      .then(setBinding)
      .catch(() => {
        setBinding(previous);
        setBindingError("Não foi possível desativar agora. Tente novamente.");
      });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-auto p-4 md:p-6">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        <header>
          <div className="flex items-center gap-3">
            <Image
              src={whatsappCircular}
              alt=""
              width={40}
              height={40}
              priority
              className="size-10"
            />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold tracking-tight">WhatsApp</h1>
                <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/5 text-emerald-800 dark:text-emerald-200">
                  Conexão manual disponível
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Conecte seu WhatsApp Business ao Tennis OS.
              </p>
            </div>
          </div>
        </header>

        <Card className="border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 via-background to-background">
          <CardHeader className="gap-3">
            <div className="flex size-10 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
              <Sparkles className="size-5" />
            </div>
            <CardTitle className="text-xl">Sua rotina já acontece no WhatsApp</CardTitle>
            <CardDescription className="max-w-2xl text-sm leading-6">
              A conexão automática, feita por você mesmo, ainda está em desenvolvimento.
              Por enquanto, nossa equipe conecta o WhatsApp à sua conta — leva pouco tempo.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-medium">Como funciona:</p>
            <ul className="mt-3 space-y-3 text-sm text-muted-foreground">
              {connectionSteps.map((step, index) => (
                <li key={index} className="flex gap-3">
                  {step.upcoming ? (
                    <Clock className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <Check className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  )}
                  <span>
                    {step.label}
                    {step.upcoming && (
                      <span className="ml-2 text-xs text-muted-foreground">(em breve)</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card size="sm">
          <CardContent className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
            <div className="flex-1">
              <p className="font-medium">Solicite já sua conexão</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Garanta que o número já esteja convertido para WhatsApp Business e
                envie a solicitação. Nossa equipe conecta o número à sua conta.
              </p>
              <Button
                size="sm"
                className="mt-3"
                disabled={requested}
                onClick={handleRequestConnection}
              >
                {requested ? "Em breve será atendido" : "Solicitar conexão"}
              </Button>
              {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
            </div>
          </CardContent>
        </Card>

        {binding?.platform_number && (
          <Card size="sm">
            <CardContent className="flex items-start gap-3">
              <MessageSquare className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
              <div className="flex-1">
                <p className="font-medium">Assistente por WhatsApp</p>
                {binding.bound ? (
                  <>
                    <p className="mt-1 flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300">
                      <Check className="size-4 shrink-0" />
                      Ativado neste número. Fale com o assistente enviando
                      mensagens para {binding.platform_number}.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-3"
                      onClick={handleRevokeBinding}
                    >
                      Desativar
                    </Button>
                  </>
                ) : challenge ? (
                  <>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Do seu WhatsApp, envie o código abaixo para{" "}
                      <span className="font-medium text-foreground">
                        {challenge.platform_number}
                      </span>
                      . O código vale por alguns minutos.
                    </p>
                    <p className="mt-3 select-all rounded-md bg-muted px-3 py-2 text-lg font-semibold tracking-wider">
                      {challenge.code}
                    </p>
                    <div className="mt-3 flex gap-2">
                      <Button size="sm" onClick={handleCheckBinding}>
                        Já enviei
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={handleGenerateCode}
                      >
                        Gerar outro código
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Ative o assistente para pedir sua agenda e agendar aulas
                      conversando pelo WhatsApp.
                    </p>
                    <Button
                      size="sm"
                      className="mt-3"
                      onClick={handleGenerateCode}
                    >
                      Ativar assistente
                    </Button>
                  </>
                )}
                {bindingError && (
                  <p className="mt-2 text-sm text-destructive">{bindingError}</p>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        <p className="text-center text-xs text-muted-foreground">
          Processo de conexão automática do WhatsApp será disponibilizado em breve!
        </p>
      </div>
    </div>
  );
}
