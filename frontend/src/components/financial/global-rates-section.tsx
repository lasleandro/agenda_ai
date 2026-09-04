"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { updateFinancialSettings } from "@/lib/api";
import type { CommercialStatus, FinancialSettingsDetail } from "@/lib/types";

export function GlobalRatesSection({
  settings,
  onSaved,
}: {
  settings: FinancialSettingsDetail;
  onSaved: (settings: FinancialSettingsDetail) => void;
}) {
  const [defaultStatus, setDefaultStatus] = useState(
    settings.default_commercial_status
  );
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(
    null
  );

  async function handleSave() {
    setSaving(true);
    try {
      onSaved(
        await updateFinancialSettings({
          default_commercial_status: defaultStatus,
        })
      );
      setNotice({ text: "Configuração salva.", error: false });
    } catch (caught) {
      setDefaultStatus(settings.default_commercial_status);
      setNotice({
        text: caught instanceof Error ? caught.message : "Não foi possível salvar a configuração. Tente novamente.",
        error: true,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Status comercial padrão</CardTitle>
        <CardDescription>
          Vale para todos os clientes e grupos que não tenham um status próprio
          definido. Na ficha de cada cliente ou grupo, ele aparece como
          &quot;Padrão da conta&quot;.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="max-w-xs space-y-1.5">
          <Label htmlFor="financial-default-status">Status padrão</Label>
          <select
            id="financial-default-status"
            value={defaultStatus}
            onChange={(event) =>
              setDefaultStatus(event.target.value as CommercialStatus)
            }
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          >
            <option value="active">Ativo</option>
            <option value="waiting">Em espera</option>
            <option value="paused">Pausado</option>
          </select>
        </div>
        {notice && (
          <p className={notice.error ? "text-sm text-destructive" : "text-sm text-emerald-600"}>
            {notice.text}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Salvando..." : "Salvar configuração"}
        </Button>
      </CardFooter>
    </Card>
  );
}
