"use client";

import { zxcvbn } from "@zxcvbn-ts/core";
import { Eye, EyeOff, Lock } from "lucide-react";
import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const strengthLabels = ["Muito fraca", "Fraca", "Razoável", "Forte", "Muito forte"];
const strengthColors = ["bg-destructive", "bg-destructive", "bg-amber-500", "bg-emerald-500", "bg-emerald-500"];

interface PasswordFieldProps {
  id: string;
  label: string;
  password: string;
  onChange: (password: string) => void;
  confirmation?: string;
  onConfirmationChange?: (password: string) => void;
}

export function PasswordField({
  id,
  label,
  password,
  onChange,
  confirmation,
  onConfirmationChange,
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const result = password ? zxcvbn(password) : null;
  const score = result?.score ?? 0;
  const isTooShort = password.length > 0 && password.length < 15;
  const feedback = isTooShort
    ? "Use pelo menos 15 caracteres. Uma frase longa é mais fácil de lembrar e mais segura."
    : score < 2
      ? "Use uma frase mais longa com palavras sem relação entre si."
      : score < 3
        ? "Uma frase mais longa pode tornar sua senha ainda mais resistente."
        : "Boa escolha: evite reutilizar esta senha em outros serviços.";
  const feedbackId = `${id}-feedback`;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor={id}>{label}</Label>
        <div className="relative">
          <Lock className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id={id}
            type={visible ? "text" : "password"}
            value={password}
            onChange={(event) => onChange(event.target.value)}
            autoComplete="new-password"
            required
            minLength={15}
            maxLength={128}
            aria-describedby={password ? feedbackId : undefined}
            className="h-10 pr-10 pl-9"
          />
          <button
            type="button"
            aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
            onClick={() => setVisible((current) => !current)}
            className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {password && (
          <div id={feedbackId} className="space-y-1.5 pt-1" aria-live="polite">
            <div className="flex gap-1" aria-label={`Força da senha: ${strengthLabels[score]}`}>
              {[0, 1, 2, 3].map((segment) => (
                <span
                  key={segment}
                  className={`h-1 flex-1 rounded-full ${segment <= score ? strengthColors[score] : "bg-border"}`}
                />
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {isTooShort ? "Senha muito curta" : `Força: ${strengthLabels[score]}`}
              {feedback ? ` — ${feedback}` : ""}
            </p>
          </div>
        )}
      </div>

      {onConfirmationChange && (
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-confirmation`}>Confirmar senha</Label>
          <Input
            id={`${id}-confirmation`}
            type={visible ? "text" : "password"}
            value={confirmation || ""}
            onChange={(event) => onConfirmationChange(event.target.value)}
            autoComplete="new-password"
            required
            minLength={15}
            maxLength={128}
            className="h-10"
          />
          {confirmation && confirmation !== password && (
            <p className="text-xs text-destructive">As senhas não coincidem.</p>
          )}
        </div>
      )}
    </div>
  );
}
