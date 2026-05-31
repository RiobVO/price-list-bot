"""Тесты доменных типов data-слоя."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.data.models import Catalog, Product, RowIssue, SchemaError


def _make_product(**overrides: object) -> Product:
    """Фабрика Product с валидными дефолтами; overrides переопределяют поля."""
    base: dict[str, object] = {
        "id": "p1",
        "category": "cat",
        "subcategory": "sub",
        "name_ru": "Товар",
        "name_uz": "Mahsulot",
        "desc_ru": "опт",
        "desc_uz": "tavsif",
        "price_wholesale": Decimal("100"),
        "price_retail": Decimal("120"),
        "currency": "UZS",
        "packaging": "1 кг",
        "photo": "file_id",
        "is_active": True,
    }
    base.update(overrides)
    return Product(**base)  # type: ignore[arg-type]


def test_product_holds_all_fields() -> None:
    p = _make_product()
    assert p.id == "p1"
    assert p.category == "cat"
    assert p.subcategory == "sub"
    assert p.name_ru == "Товар"
    assert p.name_uz == "Mahsulot"
    assert p.price_wholesale == Decimal("100")
    assert p.price_retail == Decimal("120")
    assert p.currency == "UZS"
    assert p.is_active is True


def test_product_optional_fields_accept_none() -> None:
    p = _make_product(
        desc_ru=None,
        desc_uz=None,
        price_wholesale=None,  # цена по запросу
        price_retail=None,
        packaging=None,
        photo=None,
    )
    assert p.desc_ru is None
    assert p.desc_uz is None
    assert p.price_wholesale is None
    assert p.price_retail is None
    assert p.packaging is None
    assert p.photo is None


def test_product_is_frozen() -> None:
    p = _make_product()
    with pytest.raises(FrozenInstanceError):
        p.id = "other"  # type: ignore[misc]


def test_product_uses_slots_no_dict() -> None:
    """slots=True → нет __dict__ (защита памяти/опечаток в полях)."""
    p = _make_product()
    assert not hasattr(p, "__dict__")


def test_rowissue_holds_fields_and_optional_product_id() -> None:
    issue = RowIssue(row_number=3, product_id=None, reason="missing_required", detail="empty id")
    assert issue.row_number == 3
    assert issue.product_id is None
    assert issue.reason == "missing_required"
    assert issue.detail == "empty id"


def test_rowissue_is_frozen() -> None:
    issue = RowIssue(row_number=1, product_id="p1", reason="bad_number", detail="abc")
    with pytest.raises(FrozenInstanceError):
        issue.reason = "duplicate_id"  # type: ignore[misc]


def test_schema_error_is_exception() -> None:
    assert issubclass(SchemaError, Exception)
    with pytest.raises(SchemaError):
        raise SchemaError("missing column 'currency'")


def test_catalog_build_indexes_by_id() -> None:
    a = _make_product(id="a")
    b = _make_product(id="b")
    catalog = Catalog.build([a, b])
    assert catalog.products == (a, b)  # порядок сохранён
    assert catalog.by_id["a"] is a
    assert catalog.by_id["b"] is b
    assert set(catalog.by_id) == {"a", "b"}


def test_catalog_by_id_is_read_only_mapping() -> None:
    """by_id — MappingProxyType: запись запрещена (атомарность/иммутабельность снимка)."""
    catalog = Catalog.build([_make_product(id="a")])
    with pytest.raises(TypeError):
        catalog.by_id["x"] = _make_product(id="x")  # type: ignore[index]


def test_catalog_build_does_not_dedup() -> None:
    """build НЕ дедупит — дедуп делает parse. Последний дубль id перетирает в by_id,
    но в products остаются оба (документированный контракт)."""
    first = _make_product(id="dup", name_ru="первый")
    second = _make_product(id="dup", name_ru="второй")
    catalog = Catalog.build([first, second])
    assert catalog.products == (first, second)  # оба товара сохранены
    assert catalog.by_id["dup"] is second  # by_id: последний wins (как обычный dict)


def test_catalog_build_empty() -> None:
    catalog = Catalog.build([])
    assert catalog.products == ()
    assert dict(catalog.by_id) == {}


def test_catalog_is_frozen() -> None:
    catalog = Catalog.build([_make_product(id="a")])
    with pytest.raises(FrozenInstanceError):
        catalog.products = ()  # type: ignore[misc]
