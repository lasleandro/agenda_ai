"""Safe, additive PostgreSQL data synchronization helpers.

The sync copies rows only when the destination has no row with the same primary
key. It never updates or deletes destination data.
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import execute_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BATCH_SIZE = 500


@dataclass(frozen=True)
class TableMetadata:
    """Columns and primary-key columns required for a safe insert."""

    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    nullable_columns: frozenset[str]
    column_types: dict[str, str]


@dataclass(frozen=True)
class ForeignKey:
    """A foreign key from ``child`` columns to ``parent``."""

    child: str
    parent: str
    columns: tuple[str, ...]


def _load_environment() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def connect(endpoint: str):
    """Connect to ``local`` or ``azure`` using only environment configuration."""
    _load_environment()
    if endpoint == "local":
        required = {
            "host": "PG_LOCAL_HOST",
            "port": "PG_LOCAL_PORT",
            "user": "PG_LOCAL_USER",
            "password": "PG_LOCAL_PASSWORD",
            "dbname": "AGENDA_LOCAL_DATABASE",
        }
        options = {key: os.getenv(name, "").strip() for key, name in required.items()}
    elif endpoint == "azure":
        required = {
            "host": "AZURE_PG_HOST",
            "user": "AZURE_PG_USER",
            "password": "AZURE_PG_PASSWORD",
            "dbname": "AZURE_PG_DATABASE",
        }
        options = {key: os.getenv(name, "").strip() for key, name in required.items()}
        options["port"] = os.getenv("AZURE_PG_PORT", "5432").strip()
        options["sslmode"] = os.getenv("AZURE_PG_SSLMODE", "require").strip()
    else:
        raise ValueError(f"Unknown endpoint: {endpoint}")

    missing = [name for key, name in required.items() if not options[key]]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    return psycopg2.connect(**options, connect_timeout=10)


def _revision(connection) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Database has no Alembic revision")
    return row[0]


def _table_metadata(connection) -> dict[str, TableMetadata]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT columns.table_name, columns.column_name, columns.is_nullable, columns.udt_name
            FROM information_schema.columns AS columns
            JOIN information_schema.tables AS tables
              ON tables.table_schema = columns.table_schema
             AND tables.table_name = columns.table_name
            WHERE columns.table_schema = 'public'
              AND tables.table_type = 'BASE TABLE'
              AND columns.table_name <> 'alembic_version'
            ORDER BY columns.table_name, columns.ordinal_position
            """
        )
        columns: dict[str, list[str]] = defaultdict(list)
        nullable_columns: dict[str, set[str]] = defaultdict(set)
        column_types: dict[str, dict[str, str]] = defaultdict(dict)
        for table_name, column_name, is_nullable, udt_name in cursor.fetchall():
            columns[table_name].append(column_name)
            if is_nullable == "YES":
                nullable_columns[table_name].add(column_name)
            column_types[table_name][column_name] = udt_name

        cursor.execute(
            """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY tc.table_name, kcu.ordinal_position
            """
        )
        primary_keys: dict[str, list[str]] = defaultdict(list)
        for table_name, column_name in cursor.fetchall():
            primary_keys[table_name].append(column_name)

    missing_primary_key = sorted(set(columns) - set(primary_keys))
    if missing_primary_key:
        raise RuntimeError(
            "Refusing to sync tables without primary keys: "
            + ", ".join(missing_primary_key)
        )
    return {
        table: TableMetadata(
            tuple(table_columns),
            tuple(primary_keys[table]),
            frozenset(nullable_columns[table]),
            dict(column_types[table]),
        )
        for table, table_columns in columns.items()
    }


def _foreign_keys(connection) -> list[ForeignKey]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT child.relname, parent.relname,
                   array_agg(child_column.attname ORDER BY child_key.ordinality)
            FROM pg_constraint AS fk
            JOIN pg_class AS child ON child.oid = fk.conrelid
            JOIN pg_namespace AS child_schema ON child_schema.oid = child.relnamespace
            JOIN pg_class AS parent ON parent.oid = fk.confrelid
            JOIN pg_namespace AS parent_schema ON parent_schema.oid = parent.relnamespace
            JOIN LATERAL unnest(fk.conkey) WITH ORDINALITY AS child_key(attnum, ordinality)
              ON TRUE
            JOIN pg_attribute AS child_column
              ON child_column.attrelid = child.oid
             AND child_column.attnum = child_key.attnum
            WHERE fk.contype = 'f'
              AND child_schema.nspname = 'public'
              AND parent_schema.nspname = 'public'
            GROUP BY fk.oid, child.relname, parent.relname
            """
        )
        return [ForeignKey(child, parent, tuple(columns)) for child, parent, columns in cursor.fetchall()]


def order_tables(
    tables: Iterable[str], dependencies: Iterable[tuple[str, str]]
) -> list[str]:
    """Return tables in parent-before-child foreign-key order."""
    table_set = set(tables)
    prerequisites: dict[str, set[str]] = {table: set() for table in table_set}
    children: dict[str, set[str]] = {table: set() for table in table_set}
    for child, parent in dependencies:
        if child not in table_set or parent not in table_set:
            continue
        prerequisites[child].add(parent)
        children[parent].add(child)

    ready = sorted(table for table, parents in prerequisites.items() if not parents)
    ordered: list[str] = []
    while ready:
        table = ready.pop(0)
        ordered.append(table)
        for child in sorted(children[table]):
            prerequisites[child].remove(table)
            if not prerequisites[child]:
                ready.append(child)
        ready.sort()

    if len(ordered) != len(table_set):
        cyclic = sorted(table_set - set(ordered))
        raise RuntimeError(f"Refusing to sync cyclic foreign keys: {', '.join(cyclic)}")
    return ordered


def _cycle_columns(
    tables: Iterable[str], foreign_keys: Iterable[ForeignKey], metadata: dict[str, TableMetadata]
) -> dict[str, set[str]]:
    """Return nullable foreign-key columns that must be filled after insert."""
    table_set = set(tables)
    edges: dict[str, set[str]] = {table: set() for table in table_set}
    reverse_edges: dict[str, set[str]] = {table: set() for table in table_set}
    foreign_keys = [fk for fk in foreign_keys if fk.child in table_set and fk.parent in table_set]
    for foreign_key in foreign_keys:
        edges[foreign_key.child].add(foreign_key.parent)
        reverse_edges[foreign_key.parent].add(foreign_key.child)

    visited: set[str] = set()
    finishing_order: list[str] = []

    def visit(table: str) -> None:
        visited.add(table)
        for parent in edges[table]:
            if parent not in visited:
                visit(parent)
        finishing_order.append(table)

    for table in sorted(table_set):
        if table not in visited:
            visit(table)

    components: dict[str, frozenset[str]] = {}
    visited.clear()

    def collect(table: str, component: set[str]) -> None:
        visited.add(table)
        component.add(table)
        for child in reverse_edges[table]:
            if child not in visited:
                collect(child, component)

    for table in reversed(finishing_order):
        if table in visited:
            continue
        component: set[str] = set()
        collect(table, component)
        frozen_component = frozenset(component)
        for member in component:
            components[member] = frozen_component

    cyclic_columns: dict[str, set[str]] = defaultdict(set)
    for foreign_key in foreign_keys:
        component = components[foreign_key.child]
        is_cycle = len(component) > 1 or foreign_key.child == foreign_key.parent
        if is_cycle and foreign_key.parent in component:
            non_nullable = set(foreign_key.columns) - metadata[foreign_key.child].nullable_columns
            if non_nullable:
                raise RuntimeError(
                    f"Cannot safely sync non-nullable cyclic foreign key on "
                    f"{foreign_key.child}: {', '.join(sorted(non_nullable))}"
                )
            cyclic_columns[foreign_key.child].update(foreign_key.columns)
    return cyclic_columns


def _row_count(connection, table: str) -> int:
    query = sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(table))
    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchone()[0]


def _copy_table(
    source, target, table: str, metadata: TableMetadata, deferred_columns: set[str]
) -> list[tuple]:
    copied_columns = tuple(column for column in metadata.columns if column not in deferred_columns)
    columns = sql.SQL(", ").join(sql.Identifier(column) for column in copied_columns)
    primary_key = sql.SQL(", ").join(sql.Identifier(column) for column in metadata.primary_key)
    select_query = sql.SQL("SELECT {} FROM public.{} ORDER BY {}").format(
        columns, sql.Identifier(table), primary_key
    )
    insert_query = sql.SQL(
        "INSERT INTO public.{} ({}) VALUES %s ON CONFLICT ({}) DO NOTHING RETURNING {}"
    ).format(sql.Identifier(table), columns, primary_key, primary_key)

    inserted: list[tuple] = []
    with source.cursor(name=f"sync_{table}") as source_cursor, target.cursor() as target_cursor:
        source_cursor.itersize = BATCH_SIZE
        source_cursor.execute(select_query)
        while rows := source_cursor.fetchmany(BATCH_SIZE):
            execute_values(target_cursor, insert_query.as_string(target), rows, page_size=BATCH_SIZE)
            inserted.extend(target_cursor.fetchall())
    return inserted


def _fill_deferred_columns(
    source,
    target,
    table: str,
    metadata: TableMetadata,
    deferred_columns: set[str],
    inserted_primary_keys: list[tuple],
) -> None:
    if not deferred_columns or not inserted_primary_keys:
        return

    source_columns = (*metadata.primary_key, *sorted(deferred_columns))
    columns = sql.SQL(", ").join(sql.Identifier(column) for column in source_columns)
    primary_key = sql.SQL(", ").join(sql.Identifier(column) for column in metadata.primary_key)
    select_query = sql.SQL("SELECT {} FROM public.{} ORDER BY {}").format(
        columns, sql.Identifier(table), primary_key
    )
    raw_incoming = sql.SQL(", ").join(sql.Identifier(column) for column in source_columns)
    typed_incoming = sql.SQL(", ").join(
        sql.SQL("{}::{} AS {}").format(
            sql.Identifier(column), sql.Identifier(metadata.column_types[column]), sql.Identifier(column)
        )
        for column in source_columns
    )
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = incoming.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in sorted(deferred_columns)
    )
    joins = sql.SQL(" AND ").join(
        sql.SQL("target.{} = incoming.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in metadata.primary_key
    )
    update_query = sql.SQL(
        "UPDATE public.{} AS target SET {} "
        "FROM (SELECT {} FROM (VALUES %s) AS raw ({})) AS incoming WHERE {}"
    ).format(sql.Identifier(table), assignments, typed_incoming, raw_incoming, joins)
    inserted_key_set = set(inserted_primary_keys)

    with source.cursor(name=f"deferred_{table}") as source_cursor, target.cursor() as target_cursor:
        source_cursor.itersize = BATCH_SIZE
        source_cursor.execute(select_query)
        while rows := source_cursor.fetchmany(BATCH_SIZE):
            matching_rows = [row for row in rows if tuple(row[: len(metadata.primary_key)]) in inserted_key_set]
            if matching_rows:
                execute_values(target_cursor, update_query.as_string(target), matching_rows, page_size=BATCH_SIZE)


def synchronize(source_name: str, target_name: str, apply: bool) -> None:
    """Synchronize new rows from one configured database to another."""
    source = connect(source_name)
    target = connect(target_name)
    try:
        source_revision = _revision(source)
        target_revision = _revision(target)
        if source_revision != target_revision:
            raise RuntimeError(
                f"Alembic revisions differ: {source_name}={source_revision}, "
                f"{target_name}={target_revision}"
            )

        source_metadata = _table_metadata(source)
        if source_metadata != _table_metadata(target):
            raise RuntimeError("Source and target schemas differ")
        foreign_keys = _foreign_keys(source)
        deferred_columns = _cycle_columns(source_metadata, foreign_keys, source_metadata)
        dependencies = [
            (foreign_key.child, foreign_key.parent)
            for foreign_key in foreign_keys
            if not set(foreign_key.columns).issubset(deferred_columns[foreign_key.child])
        ]
        tables = order_tables(source_metadata, dependencies)

        if not apply:
            print(f"Dry run: {source_name} -> {target_name} ({len(tables)} tables)")
            if deferred_columns:
                print("  cyclic nullable foreign keys will be filled after inserts")
            for table in tables:
                print(f"  {table}: {_row_count(source, table)} source rows")
            print("No data was changed. Re-run with --apply to insert missing rows.")
            return

        inserted_primary_keys: dict[str, list[tuple]] = {}
        for table in tables:
            inserted = _copy_table(
                source, target, table, source_metadata[table], deferred_columns[table]
            )
            inserted_primary_keys[table] = inserted
            print(f"  {table}: inserted {len(inserted)} rows")
        for table in tables:
            _fill_deferred_columns(
                source,
                target,
                table,
                source_metadata[table],
                deferred_columns[table],
                inserted_primary_keys[table],
            )
        target.commit()
        print(f"Completed additive sync: {source_name} -> {target_name}")
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def run_cli(source: str, target: str) -> None:
    """Run a direction-specific sync command."""
    parser = argparse.ArgumentParser(
        description=f"Safely copy new rows from {source} to {target}."
    )
    parser.add_argument(
        "--apply", action="store_true", help="insert missing rows; default is dry-run"
    )
    args = parser.parse_args()
    synchronize(source, target, apply=args.apply)
