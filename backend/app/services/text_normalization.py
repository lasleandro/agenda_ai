"""Shared name-normalization helper for deterministic entity resolution.

Used to build searchable `normalized_*` columns (e.g. Place.normalized_name,
EntityAlias.normalized_alias) so lookups are case/whitespace-insensitive.
"""


def normalize_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())
