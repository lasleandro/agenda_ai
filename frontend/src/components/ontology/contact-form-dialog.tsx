"use client";

import { useState } from "react";
import PhoneInput from "react-phone-number-input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ContactCreateInput } from "@/lib/types";

export function ContactFormDialog({
  open,
  onOpenChange,
  initialValues,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialValues?: ContactCreateInput | null;
  onCreate: (input: ContactCreateInput) => void;
}) {
  const [displayName, setDisplayName] = useState(initialValues?.display_name ?? "");
  const [phone, setPhone] = useState(initialValues?.phone ?? "");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit() {
    const normalizedName = displayName.trim();
    if (!normalizedName) {
      setError("Informe o nome do cliente.");
      return;
    }
    if (!phone) {
      setError("Informe o celular ou WhatsApp do cliente.");
      return;
    }

    onCreate({ display_name: normalizedName, phone });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Novo cliente</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="contact-display-name">Nome</Label>
            <Input
              id="contact-display-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Ex.: Ana Martins"
              autoComplete="name"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="contact-phone">Celular / WhatsApp</Label>
            <PhoneInput
              defaultCountry="BR"
              international
              countryCallingCodeEditable={false}
              value={phone || undefined}
              onChange={(value) => setPhone(value ?? "")}
              className="flex h-9 w-full items-center gap-2 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs"
              numberInputProps={{
                id: "contact-phone",
                className:
                  "min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground",
                autoComplete: "tel",
                inputMode: "tel",
                placeholder: "(11) 99999-0000",
              }}
            />
            <p className="text-xs text-muted-foreground">
              Brasil já está selecionado. Para clientes de outros países, escolha o país antes de digitar.
            </p>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit}>Cadastrar cliente</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
