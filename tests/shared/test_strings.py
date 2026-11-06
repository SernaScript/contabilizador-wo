from datetime import UTC, datetime

from contabilizador.shared import strings


def test_unconfigured_suppliers_banner_says_what_it_blocks() -> None:
    assert strings.unconfigured_suppliers_banner(1, 2) == (
        "1 proveedor sin configurar bloquea 2 facturas."
    )
    assert strings.unconfigured_suppliers_banner(2, 4) == (
        "2 proveedores sin configurar bloquean 4 facturas."
    )
    assert strings.unconfigured_suppliers_banner(1, 1) == (
        "1 proveedor sin configurar bloquea 1 factura."
    )


def test_app_title() -> None:
    assert strings.APP_TITLE == "Contabilizador WO"


def test_export_default_filename_is_unique_per_moment() -> None:
    first = strings.export_default_filename(datetime(2026, 9, 30, 14, 5, 9, tzinfo=UTC))
    second = strings.export_default_filename(datetime(2026, 9, 30, 14, 5, 10, tzinfo=UTC))

    assert first == "world-office-compras-20260930-140509.xlsx"
    assert first != second
