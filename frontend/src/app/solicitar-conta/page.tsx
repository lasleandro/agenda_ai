import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Calendar } from "lucide-react";

import { AccountRequestForm } from "@/components/auth/account-request-form";
import { BrandLogo } from "@/components/layout/brand-logo";

export const metadata: Metadata = {
  title: "Solicitar uma conta — Tennis OS",
  description: "Solicite acesso ao Tennis OS para sua operação de tênis.",
};

export default function RequestAccountPage() {
  return (
    <main className="flex min-h-dvh w-full items-center justify-center bg-[var(--bg-page)] px-6 py-10">
      <div className="w-full max-w-md">
        <Link
          href="/"
          className="mb-6 flex items-center justify-center gap-2.5"
          aria-label="Tennis OS, início"
        >
          <BrandLogo size={40} priority />
          <span className="text-lg font-semibold tracking-tight text-foreground">
            Tennis OS
          </span>
        </Link>

        <section className="rounded-2xl border border-border bg-card p-8 shadow-sm">
          <div className="mb-6 space-y-1">
            <h1 className="text-xl font-semibold text-foreground">
              Solicitar uma conta
            </h1>
            <p className="text-sm text-muted-foreground">
              Envie seus dados para análise. Se a solicitação for aprovada,
              você receberá por email o link para configurar sua senha.
            </p>
          </div>
          <AccountRequestForm idPrefix="request-page" autoFocus />
        </section>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-4 text-xs text-muted-foreground">
          <Link href="/login" className="flex items-center gap-1.5 hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" />
            Já tenho uma conta
          </Link>
          <span className="flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5" />
            Copiloto de agendamento via WhatsApp
          </span>
        </div>
      </div>
    </main>
  );
}
