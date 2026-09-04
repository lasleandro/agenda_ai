"use client";

import PhoneInput from "react-phone-number-input";

import { Label } from "@/components/ui/label";

const DEFAULT_HINT =
  "Brasil já está selecionado. Para operações de outros países, escolha o país antes de digitar.";

interface WhatsappFieldProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  label?: string;
  hint?: string | null;
  required?: boolean;
  autoFocus?: boolean;
}

/**
 * Shared E.164 WhatsApp number input (Brazil default). Used by the public
 * account-request form, the admin "Novo tenant" dialog, and request approval.
 */
export function WhatsappField({
  id,
  value,
  onChange,
  label = "WhatsApp da operação",
  hint = DEFAULT_HINT,
  required = true,
  autoFocus = false,
}: WhatsappFieldProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <PhoneInput
        defaultCountry="BR"
        international
        countryCallingCodeEditable={false}
        value={value || undefined}
        onChange={(next) => onChange(next ?? "")}
        className="flex h-10 w-full items-center gap-2 rounded-lg border border-input bg-transparent px-3 text-sm shadow-xs"
        numberInputProps={{
          id,
          required,
          autoFocus,
          className:
            "min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground",
          autoComplete: "tel",
          inputMode: "tel",
          placeholder: "(11) 99999-0000",
        }}
      />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
