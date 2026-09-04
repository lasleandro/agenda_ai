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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { updateCancellationNoticeHours } from "@/lib/api";
import type { CancellationNoticeHoursDetail } from "@/lib/types";

export function CancellationNoticeSection({
  detail,
  onSaved,
}: {
  detail: CancellationNoticeHoursDetail;
  onSaved: (detail: CancellationNoticeHoursDetail) => void;
}) {
  const [hours, setHours] = useState(detail.cancellation_notice_hours);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(
    null
  );

  async function handleSave() {
    setSaving(true);
    setNotice({ text: "Configuração salva.", error: false });
    try {
      onSaved(await updateCancellationNoticeHours(hours));
    } catch (caught) {
      setHours(detail.cancellation_notice_hours);
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
        <CardTitle>Aviso prévio para reposição</CardTitle>
        <CardDescription>
          Prazo mínimo, em horas, para que um cancelamento gere crédito de
          reposição.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-1.5">
        <div className="max-w-xs space-y-1.5">
          <Label htmlFor="cancellation-notice-hours">Horas de aviso prévio</Label>
          <Input
            id="cancellation-notice-hours"
            type="number"
            min={0}
            max={168}
            value={hours}
            onChange={(event) => setHours(Number(event.target.value))}
          />
          <p className="text-xs text-muted-foreground">
            Cancelamentos dentro deste prazo não geram crédito de reposição.
          </p>
        </div>
        {notice && (
          <p className={notice.error ? "text-sm text-destructive" : "text-sm text-emerald-600"}>
            {notice.text}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Salvando..." : "Salvar"}
        </Button>
      </CardFooter>
    </Card>
  );
}
