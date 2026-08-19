"use client";

import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import { Input } from "@/components/ui/input";
import { searchAddress, type GeocodeResult } from "@/lib/geocode";

/** Reusable address field with Photon-backed search-as-you-type suggestions.
 * Used by both the Place ("Meus Locais") and Contact ("Clientes") forms. */
export function AddressAutocomplete({
  value,
  placeholder,
  onSelect,
  onChange,
}: {
  value: string;
  placeholder?: string;
  onSelect: (result: GeocodeResult) => void;
  /** Fires on every keystroke, before any suggestion is picked — use this to
   * keep freehand-typed text (no Photon match) as the source of truth. */
  onChange?: (text: string) => void;
}) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(value), 0);
    return () => window.clearTimeout(timer);
  }, [value]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      searchAddress(query).then((r) => {
        setResults(r);
        setOpen(r.length > 0);
      });
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  function handleSelect(result: GeocodeResult) {
    setQuery(result.label);
    setResults([]);
    setOpen(false);
    onSelect(result);
  }

  return (
    <div className="relative">
      <Input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          onChange?.(e.target.value);
        }}
        placeholder={placeholder ?? "Buscar endereço..."}
        onFocus={() => results.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-card shadow-md max-h-60 overflow-auto">
          {results.map((r, i) => (
            <button
              key={i}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handleSelect(r)}
              className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
            >
              <MapPin className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
              <span>{r.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
