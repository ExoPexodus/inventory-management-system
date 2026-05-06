import pytest

VALID_TYPES = ["physical", "digital", "service", "donation", "gift_card"]


def test_is_shippable_true_for_physical() -> None:
    from app.services.product_type_service import is_shippable
    assert is_shippable("physical") is True


def test_is_shippable_false_for_non_physical_types() -> None:
    from app.services.product_type_service import is_shippable
    for t in ["digital", "service", "donation", "gift_card"]:
        assert is_shippable(t) is False, f"Expected {t} to not be shippable"


def test_is_inventory_tracked_depends_on_track_quantity_flag() -> None:
    from app.services.product_type_service import is_inventory_tracked
    assert is_inventory_tracked("physical", track_quantity=True) is True
    assert is_inventory_tracked("physical", track_quantity=False) is False


def test_is_inventory_tracked_false_for_service_donation_gift_card() -> None:
    from app.services.product_type_service import is_inventory_tracked
    for t in ["service", "donation", "gift_card"]:
        assert is_inventory_tracked(t, track_quantity=True) is False, f"Expected {t} not tracked"


def test_is_inventory_tracked_digital_respects_flag() -> None:
    from app.services.product_type_service import is_inventory_tracked
    assert is_inventory_tracked("digital", track_quantity=True) is True
    assert is_inventory_tracked("digital", track_quantity=False) is False


def test_is_variable_amount_true_only_for_donation() -> None:
    from app.services.product_type_service import is_variable_amount
    assert is_variable_amount("donation") is True
    for t in ["physical", "digital", "service", "gift_card"]:
        assert is_variable_amount(t) is False


def test_is_tax_exempt_by_default_true_only_for_donation() -> None:
    from app.services.product_type_service import is_tax_exempt_by_default
    assert is_tax_exempt_by_default("donation") is True
    for t in ["physical", "digital", "service", "gift_card"]:
        assert is_tax_exempt_by_default(t) is False


def test_all_valid_types_handled_by_all_functions() -> None:
    from app.services.product_type_service import (
        is_inventory_tracked, is_shippable, is_tax_exempt_by_default, is_variable_amount,
    )
    for t in VALID_TYPES:
        is_shippable(t)
        is_inventory_tracked(t, track_quantity=True)
        is_variable_amount(t)
        is_tax_exempt_by_default(t)
