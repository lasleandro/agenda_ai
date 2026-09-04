"use client";

import { useRef, useState } from "react";
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
import { Loader2, MapPin, Search } from "lucide-react";
import { AddressAutocomplete } from "./address-autocomplete";
import { createPlace, updatePlace } from "@/lib/api";
import { searchAddress, type GeocodeResult } from "@/lib/geocode";
import type { Place, PlaceInput } from "@/lib/types";

/** Create/edit dialog for a Place ("Local"). Reused by the "Meus Locais"
 * list page (create) and place detail page (edit).
 *
 * Flow: user types a place name → clicks "Buscar" → sees Photon results →
 * picks one → name + address auto-filled for confirmation. User can refine
 * the address manually in the Endereco field after. */
export function PlaceFormDialog({
  open,
  onOpenChange,
  place,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  place?: Place | null;
  onSaved: (place: Place) => void;
}) {
  const [name, setName] = useState(place?.name ?? "");
  const [address, setAddress] = useState<GeocodeResult | null>(null);
  const [addressText, setAddressText] = useState(
    [place?.address_line, place?.city, place?.state].filter(Boolean).join(", ") || ""
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Photon search state
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<GeocodeResult[]>([]);
  const [searchedQuery, setSearchedQuery] = useState("");
  const lastNameRef = useRef<string | null>(null);

  /** Called when the user picks a Photon result — fills name + address. */
  function handleSelectResult(result: GeocodeResult) {
    setName(result.name || searchedQuery);
    setAddress(result);
    const fullAddress = [result.address_line, result.city, result.state]
      .filter(Boolean)
      .join(", ");
    setAddressText(fullAddress);
    setSearchResults([]);
  }

  /** Explicit "Buscar" action — only search when the user clicks the button
   * and only if the query actually changed. */
  async function handleSearch() {
    const q = name.trim();
    if (q.length < 3) {
      setError("Digite pelo menos 3 caracteres para buscar");
      return;
    }
    if (q === lastNameRef.current) return; // same query, no re-search
    lastNameRef.current = q;
    setSearchedQuery(q);
    setError(null);
    setSearching(true);
    try {
      const results = await searchAddress(q);
      setSearchResults(results);
      if (results.length === 0) {
        setError("Nenhum local encontrado. Verifique o nome ou preencha o endereço manualmente.");
      }
    } catch {
      setError("Não foi possível buscar o endereço. Tente novamente.");
    } finally {
      setSearching(false);
    }
  }

  async function handleSave() {
    if (!name.trim()) {
      setError("Informe um nome para o local");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: PlaceInput = { name: name.trim() };
      if (address) {
        Object.assign(payload, {
          address_line: address.address_line,
          city: address.city,
          state: address.state,
          postal_code: address.postal_code,
          country: address.country,
          latitude: address.latitude,
          longitude: address.longitude,
        });
      } else if (addressText.trim()) {
        // Fallback: manually typed address with no Photon match
        payload.address_line = addressText.trim();
      }
      const saved = place
        ? await updatePlace(place.id, payload)
        : await createPlace(payload);
      onSaved(saved);
      onOpenChange(false);
      resetForm();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível salvar o local. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  function resetForm() {
    setName("");
    setAddress(null);
    setAddressText("");
    setSearchResults([]);
    setSearchedQuery("");
    setError(null);
    lastNameRef.current = null;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{place ? "Editar local" : "Novo local"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* ---- Nome + buscar ---- */}
          <div className="space-y-1.5">
            <Label htmlFor="place-name">Nome do local</Label>
            <div className="flex gap-2">
              <Input
                id="place-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: Clube Atlético Paulistano"
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
              <Button
                variant="secondary"
                size="icon"
                onClick={handleSearch}
                disabled={searching || name.trim().length < 3}
                title="Buscar endereço"
              >
                {searching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Digite o nome e clique em buscar — se o local for encontrado, o endereço
              sera preenchido para voce confirmar.
            </p>
          </div>

          {/* ---- Search results ---- */}
          {searchResults.length > 0 && (
            <div className="rounded-md border border-border max-h-40 overflow-auto">
              {searchResults.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleSelectResult(r)}
                  className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-muted border-b border-border last:border-b-0"
                >
                  <MapPin className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                  <div>
                    <p className="font-medium">{r.name || r.address_line}</p>
                    <p className="text-xs text-muted-foreground">{r.label}</p>
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* ---- Endereco (manual refinement) ---- */}
          <div className="space-y-1.5">
            <Label>Endereco</Label>
            <AddressAutocomplete
              value={addressText}
              onChange={setAddressText}
              onSelect={(result) => {
                setAddress(result);
                const fullAddress = [result.address_line, result.city, result.state]
                  .filter(Boolean)
                  .join(", ");
                setAddressText(fullAddress);
              }}
            />
            <p className="text-xs text-muted-foreground">
              Confirme ou ajuste o endereco manualmente.
            </p>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Salvando..." : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
