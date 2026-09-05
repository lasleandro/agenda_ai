import pytest

from scripts.db_sync import ForeignKey, TableMetadata, _cycle_columns, order_tables


def test_order_tables_places_parents_before_children() -> None:
    result = order_tables(
        {"appointments", "contacts", "professionals"},
        [("contacts", "professionals"), ("appointments", "contacts")],
    )

    assert result == ["professionals", "contacts", "appointments"]


def test_order_tables_cyclic_foreign_keys_refuses_sync() -> None:
    with pytest.raises(RuntimeError, match="cyclic foreign keys"):
        order_tables(
            {"contacts", "professionals"},
            [("contacts", "professionals"), ("professionals", "contacts")],
        )


def test_cycle_columns_defers_only_nullable_cycle_links() -> None:
    metadata = {
        "professionals": TableMetadata(
            ("id", "status_changed_by"),
            ("id",),
            frozenset({"status_changed_by"}),
            {"id": "uuid", "status_changed_by": "uuid"},
        ),
        "users": TableMetadata(
            ("id", "professional_id"),
            ("id",),
            frozenset({"professional_id"}),
            {"id": "uuid", "professional_id": "uuid"},
        ),
    }

    result = _cycle_columns(
        metadata,
        [
            ForeignKey("professionals", "users", ("status_changed_by",)),
            ForeignKey("users", "professionals", ("professional_id",)),
        ],
        metadata,
    )

    assert result == {
        "professionals": {"status_changed_by"},
        "users": {"professional_id"},
    }
