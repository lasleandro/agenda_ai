/**
 * Address autocomplete via Photon (Komoot's open-source OSM geocoder).
 * MVP choice: free, no API key, public demo API — see
 * docs/ROADMAPS/customer_ontology_places_roadmap_v0.1_2026-08-05.md for the
 * assessment. Swap PHOTON_BASE_URL for a self-hosted instance or a
 * different provider later without touching call sites.
 */

const PHOTON_BASE_URL = "https://photon.komoot.io/api/";

export interface GeocodeResult {
  label: string; // full display string for the dropdown row
  name: string | null; // venue/POI name, when Photon has one (e.g. a club)
  address_line: string;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
}

interface PhotonFeature {
  geometry: { coordinates: [number, number] };
  properties: {
    name?: string;
    street?: string;
    housenumber?: string;
    city?: string;
    state?: string;
    postcode?: string;
    country?: string;
  };
}

function toResult(feature: PhotonFeature): GeocodeResult {
  const p = feature.properties;
  const [longitude, latitude] = feature.geometry.coordinates;
  const streetPart = [p.street, p.housenumber].filter(Boolean).join(", ");
  const addressLine = [p.name, streetPart].filter(Boolean).join(" — ") || streetPart || p.name || "";
  const label = [addressLine, p.city, p.state].filter(Boolean).join(", ");

  return {
    label: label || addressLine,
    name: p.name ?? null,
    address_line: addressLine,
    city: p.city ?? null,
    state: p.state ?? null,
    postal_code: p.postcode ?? null,
    country: p.country ?? null,
    latitude,
    longitude,
  };
}

/** Bias results near a lat/lon (e.g. the professional's own city) — optional. */
export async function searchAddress(
  query: string,
  bias?: { lat: number; lon: number }
): Promise<GeocodeResult[]> {
  if (query.trim().length < 3) return [];

  const params = new URLSearchParams({ q: query, limit: "5", lang: "pt" });
  if (bias) {
    params.set("lat", String(bias.lat));
    params.set("lon", String(bias.lon));
  }

  const res = await fetch(`${PHOTON_BASE_URL}?${params.toString()}`);
  if (!res.ok) return [];

  const data: { features: PhotonFeature[] } = await res.json();
  return data.features.map(toResult);
}
