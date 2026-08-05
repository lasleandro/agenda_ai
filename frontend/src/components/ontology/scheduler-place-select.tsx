"use client";

import { useState } from "react";
import { Label } from "@/components/ui/label";
import type { Place } from "@/lib/types";
import { PlaceFormDialog } from "./place-form-dialog";

const CREATE_PLACE_VALUE = "__create_place__";

export function SchedulerPlaceSelect({
  id,
  value,
  places,
  onChange,
  onPlaceCreated,
}: {
  id: string;
  value: string;
  places: Place[];
  onChange: (placeId: string) => void;
  onPlaceCreated?: (place: Place) => void;
}) {
  const [availablePlaces, setAvailablePlaces] = useState(places);
  const [placeDialogOpen, setPlaceDialogOpen] = useState(false);

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>Local</Label>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          if (event.target.value === CREATE_PLACE_VALUE) {
            setPlaceDialogOpen(true);
            return;
          }
          onChange(event.target.value);
        }}
        className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
      >
        <option value="">Selecione um local</option>
        {availablePlaces.map((place) => (
          <option key={place.id} value={place.id}>
            {place.name}
          </option>
        ))}
        <option value={CREATE_PLACE_VALUE}>+ Cadastrar novo local</option>
      </select>

      {placeDialogOpen && (
        <PlaceFormDialog
          open
          onOpenChange={setPlaceDialogOpen}
          onSaved={(place) => {
            setAvailablePlaces((current) => [...current, place]);
            onChange(place.id);
            onPlaceCreated?.(place);
          }}
        />
      )}
    </div>
  );
}
