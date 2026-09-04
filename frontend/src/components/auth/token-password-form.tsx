"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { PasswordField } from "@/components/auth/password-field";
import { Button } from "@/components/ui/button";
import { activateAccount, resetPassword } from "@/lib/auth";

interface TokenPasswordFormProps {
  mode: "activate" | "reset";
}

export function TokenPasswordForm({ mode }: TokenPasswordFormProps) {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tokenStateKey = `tennisOs${mode}Token`;
    const historyState = (window.history.state ?? {}) as Record<string, unknown>;
    const tokenFromHistory = historyState[tokenStateKey];
    const tokenFromUrl = params.get("token");
    const parsedToken = tokenFromUrl || (typeof tokenFromHistory === "string" ? tokenFromHistory : "");
    if (tokenFromUrl) {
      window.history.replaceState(
        { ...historyState, [tokenStateKey]: tokenFromUrl },
        "",
        window.location.pathname
      );
    }
    const timer = window.setTimeout(() => setToken(parsedToken), 0);
    return () => window.clearTimeout(timer);
  }, [mode]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!token) {
      setError("Este link não é válido.");
      return;
    }
    if (password !== confirmation) {
      setError("As senhas não coincidem.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "activate") {
        await activateAccount(token, password, confirmation);
      } else {
        await resetPassword(token, password, confirmation);
      }
      const tokenStateKey = `tennisOs${mode}Token`;
      const historyState = { ...(window.history.state ?? {}) } as Record<string, unknown>;
      delete historyState[tokenStateKey];
      window.history.replaceState(historyState, "", window.location.pathname);
      setCompleted(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível atualizar a senha.");
    } finally {
      setSubmitting(false);
    }
  }

  const title = mode === "activate" ? "Ative sua conta" : "Crie uma nova senha";
  const description = mode === "activate"
    ? "Escolha uma senha para confirmar seu e-mail e liberar o acesso."
    : "Escolha uma senha nova para voltar a acessar sua agenda.";

  return (
    <main className="flex min-h-dvh items-center justify-center bg-[var(--bg-page)] px-6">
      <section className="w-full max-w-sm rounded-2xl border border-border bg-card p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>

        {completed ? (
          <div className="mt-6 space-y-4">
            <p className="rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700">
              {mode === "activate" ? "Conta ativada com sucesso." : "Senha redefinida com sucesso."}
            </p>
            <Button className="w-full" nativeButton={false} render={<Link href="/login" />}>Entrar</Button>
          </div>
        ) : token === null ? (
          <p className="mt-6 text-sm text-muted-foreground">Validando link…</p>
        ) : !token ? (
          <div className="mt-6 space-y-4">
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Este link está incompleto ou não é mais válido.
            </p>
            <p className="text-center text-xs text-muted-foreground">
              <a className="underline hover:text-foreground" href="mailto:contato@tennisos.com.br?subject=Novo%20link%20de%20acesso">
                Falar com o suporte para solicitar um novo link
              </a>
              {" "}se ele expirou.
            </p>
            <Button className="w-full" variant="outline" nativeButton={false} render={<Link href="/login" />}>Voltar para entrar</Button>
          </div>
        ) : (
          <form className="mt-6 space-y-5" onSubmit={handleSubmit}>
            <PasswordField
              id="new-password"
              label="Nova senha"
              password={password}
              onChange={setPassword}
              confirmation={confirmation}
              onConfirmationChange={setConfirmation}
            />
            {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
            <Button className="w-full" type="submit" disabled={submitting}>
              {submitting ? "Salvando..." : mode === "activate" ? "Ativar conta" : "Redefinir senha"}
            </Button>
          </form>
        )}
      </section>
    </main>
  );
}
