"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CircleDollarSign, MapPin, Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PlaceFormDialog } from "@/components/ontology/place-form-dialog";
import { fetchPlaces } from "@/lib/api";
import { fetchSession, sessionHasFeature } from "@/lib/auth";
import type { Place } from "@/lib/types";

export function PlacesSection() {
  const router = useRouter();
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [financialEnabled, setFinancialEnabled] = useState(false);

  useEffect(() => {
    fetchPlaces().then((res) => setPlaces(res.places));
    fetchSession().then((user) =>
      setFinancialEnabled(sessionHasFeature(user, "commercial_financials"))
    );
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Meus Locais</CardTitle>
        <CardDescription>
          Locais onde você atende — clubes, quadras, academias.
        </CardDescription>
        <CardAction>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Novo local
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {places === null && (
          <p className="text-sm text-muted-foreground">Carregando...</p>
        )}

        {places !== null && places.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Nenhum local cadastrado ainda. Clique em &quot;Novo local&quot; para
            começar.
          </p>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {places?.map((place) => (
            <div
              key={place.id}
              className="relative rounded-xl border border-border bg-card shadow-sm hover:border-indigo-400"
            >
              <button
                onClick={() => router.push(`/places/${place.id}`)}
                className="flex w-full flex-col gap-2 p-4 pr-20 text-left"
              >
                <p className="text-sm font-semibold text-foreground">{place.name}</p>
                {place.address_line && (
                  <span className="flex items-start gap-1.5 text-xs text-muted-foreground">
                    <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {place.address_line}
                    {place.city ? `, ${place.city}` : ""}
                  </span>
                )}
                {financialEnabled && (
                  <span className="flex items-center gap-1.5 text-xs font-medium text-primary">
                    <CircleDollarSign className="size-3.5" />
                    Configurar valores R$/hora
                  </span>
                )}
              </button>
              <Button
                variant="ghost"
                size="sm"
                className="absolute right-2 top-2"
                onClick={() => router.push(`/places/${place.id}`)}
              >
                <Pencil className="h-3.5 w-3.5" />
                Editar
              </Button>
            </div>
          ))}
        </div>
      </CardContent>

      {dialogOpen && (
        <PlaceFormDialog
          open
          onOpenChange={setDialogOpen}
          place={null}
          onSaved={(saved) =>
            setPlaces((current) => (current ? [...current, saved] : current))
          }
        />
      )}
    </Card>
  );
}
