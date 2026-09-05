"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Calendar, Eye, EyeOff, Lock, Mail } from "lucide-react";
import { AccountRequestForm } from "@/components/auth/account-request-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BrandLogo } from "@/components/layout/brand-logo";
import { login, requestPasswordReset } from "@/lib/auth";

type AuthView = "login" | "signup" | "forgot";

const RESEND_COOLDOWN_SECONDS = 60;

export default function LoginPage() {
  const router = useRouter();
  const [view, setView] = useState<AuthView>("login");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [resetEmail, setResetEmail] = useState("");
  const [resetSubmitted, setResetSubmitted] = useState(false);
  const [resendSecondsRemaining, setResendSecondsRemaining] = useState(0);

  useEffect(() => {
    if (resendSecondsRemaining === 0) {
      return;
    }

    const interval = window.setInterval(() => {
      setResendSecondsRemaining((seconds) => Math.max(seconds - 1, 0));
    }, 1000);

    return () => window.clearInterval(interval);
  }, [resendSecondsRemaining]);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace("/agenda");
    } catch {
      setError("Email ou senha inválidos");
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePasswordReset(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await requestPasswordReset(resetEmail);
      setResetSubmitted(true);
      setResendSecondsRemaining(RESEND_COOLDOWN_SECONDS);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível solicitar a redefinição."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-dvh w-full">
      {/* Branding panel */}
      <div
        className="relative hidden w-1/2 flex-col justify-between overflow-hidden p-12 lg:flex"
        style={{ background: "var(--sidebar-bg)" }}
      >
        <div
          className="pointer-events-none absolute -top-24 -right-24 h-96 w-96 rounded-full opacity-30 blur-3xl"
          style={{ background: "radial-gradient(circle, #7c6cf7, transparent 70%)" }}
        />
        <div
          className="pointer-events-none absolute -bottom-32 -left-16 h-80 w-80 rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle, #4f46e5, transparent 70%)" }}
        />

        <Link href="/" className="relative flex items-center gap-2.5">
          <BrandLogo size={36} priority />
          <span className="text-[15px] font-semibold tracking-tight text-white">
            Tennis OS
          </span>
        </Link>

        <div className="relative max-w-md space-y-4">
          <h1 className="text-3xl font-semibold leading-tight text-white">
            Sua operação, organizada pelo WhatsApp.
          </h1>
          <p className="text-[15px] leading-relaxed text-[var(--sidebar-text)]">
            Confirmações, remarcações e cancelamentos processados
            automaticamente — tudo em um só lugar.
          </p>
        </div>

        <p className="relative text-xs text-[var(--sidebar-text)]">
          Versão {process.env.NEXT_PUBLIC_PLATFORM_VERSION}
        </p>
      </div>

      {/* Form panel */}
      <div className="flex w-full flex-col items-center justify-center bg-[var(--bg-page)] px-6 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center gap-3 lg:hidden">
            <BrandLogo size={40} priority />
            <span className="text-lg font-semibold tracking-tight text-foreground">
              Tennis OS
            </span>
          </div>

          <div className="rounded-2xl border border-border bg-card p-8 shadow-sm">
            {view !== "forgot" && (
              <div className="mb-6 flex gap-1 rounded-lg bg-secondary p-1">
                <button
                  type="button"
                  onClick={() => {
                    setView("login");
                    setError(null);
                  }}
                  className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    view === "login"
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Entrar
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setView("signup");
                    setError(null);
                  }}
                  className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    view === "signup"
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Solicitar uma conta
                </button>
              </div>
            )}

            {view === "login" && (
              <>
                <div className="mb-6 space-y-1">
                  <h2 className="text-xl font-semibold text-foreground">Entrar</h2>
                  <p className="text-sm text-muted-foreground">
                    Acesse sua agenda com suas credenciais.
                  </p>
                </div>

                <form onSubmit={handleLogin} className="space-y-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="email">Email</Label>
                    <div className="relative">
                      <Mail className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        autoComplete="username"
                        autoFocus
                        required
                        className="h-10 pl-9"
                      />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="password">Senha</Label>
                    <div className="relative">
                      <Lock className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="password"
                        type={passwordVisible ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="current-password"
                        required
                        className="h-10 pr-10 pl-9"
                      />
                      <button
                        type="button"
                        aria-label={passwordVisible ? "Ocultar senha" : "Mostrar senha"}
                        onClick={() => setPasswordVisible((visible) => !visible)}
                        className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {passwordVisible ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  </div>

                  {error && (
                    <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {error}
                    </p>
                  )}

                  <Button
                    type="submit"
                    className="h-10 w-full text-[15px]"
                    disabled={submitting}
                  >
                    {submitting ? "Entrando..." : "Entrar"}
                  </Button>
                </form>

                <button
                  type="button"
                  onClick={() => {
                    setResetEmail(email.trim());
                    setResetSubmitted(false);
                    setResendSecondsRemaining(0);
                    setError(null);
                    setView("forgot");
                  }}
                  className="mt-4 w-full text-center text-xs text-muted-foreground hover:text-foreground"
                >
                  Esqueci minha senha
                </button>
              </>
            )}

            {view === "signup" && (
              <>
                <div className="mb-6 space-y-1">
                  <h2 className="text-xl font-semibold text-foreground">
                    Solicitar uma conta
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Envie seus dados para análise. Se a solicitação for aprovada,
                    você receberá por email o link para configurar sua senha.
                  </p>
                </div>
                <AccountRequestForm idPrefix="login-request" autoFocus />
              </>
            )}

            {view === "forgot" && (
              <>
                <div className="mb-6 space-y-1">
                  <h2 className="text-xl font-semibold text-foreground">
                    Redefinir senha
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Informe seu e-mail. Se existir uma conta ativa, enviaremos as
                    instruções de redefinição.
                  </p>
                </div>

                <form className="space-y-4" onSubmit={handlePasswordReset}>
                  <div className="space-y-1.5">
                    <Label htmlFor="reset-email">Email</Label>
                    <div className="relative">
                      <Mail className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="reset-email"
                        type="email"
                        value={resetEmail}
                        onChange={(e) => setResetEmail(e.target.value)}
                        autoComplete="email"
                        autoFocus
                        required
                        className="h-10 pl-9"
                      />
                    </div>
                  </div>

                  {resetSubmitted && (
                    <p className="rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700">
                      Se houver uma conta ativa para este e-mail, enviaremos as
                      instruções em instantes.
                    </p>
                  )}
                  {error && (
                    <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {error}
                    </p>
                  )}
                  <Button
                    className="h-10 w-full text-[15px]"
                    type="submit"
                    disabled={submitting || resendSecondsRemaining > 0}
                  >
                    {submitting
                      ? "Enviando..."
                      : resendSecondsRemaining > 0
                        ? `Reenviar em ${resendSecondsRemaining}s`
                        : resetSubmitted
                          ? "Reenviar instruções"
                          : "Enviar instruções"}
                  </Button>
                </form>

                <button
                  type="button"
                  onClick={() => {
                    setView("login");
                    setError(null);
                    setResetSubmitted(false);
                    setResendSecondsRemaining(0);
                  }}
                  className="mt-4 flex w-full items-center justify-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Voltar para entrar
                </button>
              </>
            )}
          </div>

          <div className="mt-6 flex items-center justify-center gap-4 text-xs text-muted-foreground">
            <Link href="/" className="flex items-center gap-1.5 hover:text-foreground">
              <ArrowLeft className="h-3.5 w-3.5" />
              Voltar ao site
            </Link>
            <span className="flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" />
              Copiloto de agendamento via WhatsApp
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
