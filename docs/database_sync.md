# Additive database synchronization

## Purpose and safety contract

`scripts/local_to_azure.py` and `scripts/azure_to_local.py` copy rows in one
direction. They require matching Alembic revisions, synchronize all public
application tables in foreign-key order, and insert a row only when its primary
key is absent from the destination.

They never delete rows or overwrite existing destination rows. A conflict is
left unchanged, so these commands are safe for copying new data but are not a
bidirectional conflict-resolution system.

## Running a sync

Configure the `PG_LOCAL_*`, `AGENDA_LOCAL_DATABASE`, and `AZURE_PG_*` values
in `.env`. Both scripts dry-run by default and print source row counts without
changing either database.

```bash
conda run -n agenda python scripts/local_to_azure.py
conda run -n agenda python scripts/azure_to_local.py
```

After reviewing the output, add `--apply` to insert missing rows in the stated
direction:

```bash
conda run -n agenda python scripts/local_to_azure.py --apply
conda run -n agenda python scripts/azure_to_local.py --apply
```

Run only one direction at a time. If both databases have changed rows with the
same primary key, decide which copy is authoritative before syncing; the
scripts deliberately do not resolve that conflict automatically.

## Foreign-key cycles

The current `users` and `professionals` relationship is cyclic but nullable.
For newly inserted rows, the scripts insert the records first and fill only
those nullable links after every referenced row exists. They do not disable
foreign-key checks or update pre-existing destination rows. A future
non-nullable cycle causes the sync to stop before changing data.
