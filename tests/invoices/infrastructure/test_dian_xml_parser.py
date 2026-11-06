import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine
from contabilizador.invoices.domain.errors import InvalidDocumentError, UnsupportedDocumentError
from contabilizador.invoices.domain.totals import check_totals
from contabilizador.invoices.infrastructure.dian_xml_parser import LxmlDianParser


def cufe(name: str) -> str:
    return hashlib.sha384(name.encode()).hexdigest()


def parse_fixture(xml_fixtures_dir: Path, name: str) -> ParsedDocument:
    path = xml_fixtures_dir / name
    return LxmlDianParser().parse(path.read_bytes(), path)


def test_invoice_plain(xml_fixtures_dir: Path) -> None:
    doc = parse_fixture(xml_fixtures_dir, "invoice_plain.xml")
    assert doc.kind is DocumentKind.INVOICE
    assert doc.cufe == cufe("invoice_plain")
    assert doc.supplier_nit == "900123456"
    assert doc.supplier_name == "COMERCIALIZADORA EJEMPLO S.A.S."
    assert (doc.supplier_prefix, doc.supplier_number) == ("FEV", "1001")
    assert doc.issue_date == date(2026, 8, 31)
    assert doc.due_date == date(2026, 9, 30)
    assert doc.lines == (
        ParsedLine("RESMA PAPEL CARTA 75G", Decimal("3"), Decimal("30000"), Decimal("19")),
        ParsedLine("TONER IMPRESORA LASER", Decimal("1"), Decimal("125000"), Decimal("19")),
    )
    assert doc.payable_amount == Decimal("184450.00")
    assert doc.billing_reference_cufe is None
    assert doc.source_file == xml_fixtures_dir / "invoice_plain.xml"


def test_credit_note(xml_fixtures_dir: Path) -> None:
    doc = parse_fixture(xml_fixtures_dir, "credit_note.xml")
    assert doc.kind is DocumentKind.CREDIT_NOTE
    assert doc.cufe == cufe("credit_note")
    assert doc.supplier_nit == "900123456"
    assert (doc.supplier_prefix, doc.supplier_number) == ("NC", "125")
    assert doc.issue_date == date(2026, 9, 5)
    assert doc.due_date is None
    assert doc.effective_due_date == date(2026, 9, 5)
    assert doc.lines == (
        ParsedLine("RESMA PAPEL CARTA 75G", Decimal("1"), Decimal("10000"), Decimal("19")),
    )
    assert doc.payable_amount == Decimal("11900.00")
    assert doc.billing_reference_cufe == cufe("invoice_plain")


def test_invoice_with_discount_uses_net_line_extension(xml_fixtures_dir: Path) -> None:
    doc = parse_fixture(xml_fixtures_dir, "invoice_with_discount.xml")
    assert (doc.supplier_prefix, doc.supplier_number) == ("FEV", "1002")
    assert doc.cufe == cufe("invoice_with_discount")
    assert doc.issue_date == date(2026, 9, 2)
    assert doc.due_date == date(2026, 10, 2)
    (line,) = doc.lines
    assert line == ParsedLine(
        "SILLA ERGONOMICA OFICINA", Decimal("2"), Decimal("90000"), Decimal("19")
    )
    assert line.unit_value == Decimal("45000")
    assert doc.payable_amount == Decimal("107100.00")


def test_invoice_mixed_iva(xml_fixtures_dir: Path) -> None:
    doc = parse_fixture(xml_fixtures_dir, "invoice_mixed_iva.xml")
    assert (doc.supplier_prefix, doc.supplier_number) == ("FEV", "1003")
    assert doc.due_date == date(2026, 10, 3)
    assert [
        (ln.description, ln.quantity, ln.line_extension_amount, ln.tax_percent) for ln in doc.lines
    ] == [
        ("PORTATIL 14 PULGADAS", Decimal("1"), Decimal("100000"), Decimal("19")),
        ("CAFE MOLIDO 500G", Decimal("2"), Decimal("50000"), Decimal("5")),
        ("LIBRO CONTABILIDAD BASICA", Decimal("1"), Decimal("30000"), Decimal("0")),
    ]
    assert doc.payable_amount == Decimal("201500.00")


def test_invoice_without_due_date_and_without_line_tax(xml_fixtures_dir: Path) -> None:
    doc = parse_fixture(xml_fixtures_dir, "invoice_without_due_date.xml")
    assert doc.cufe == cufe("invoice_without_due_date")
    assert doc.supplier_nit == "1017000111"
    assert doc.supplier_name == "PEDRO PRUEBA RESTREPO"
    # Se conservan los ceros a la izquierda del número
    assert (doc.supplier_prefix, doc.supplier_number) == ("FE", "00450")
    assert doc.issue_date == date(2026, 9, 4)
    assert doc.due_date is None
    assert doc.lines == (
        ParsedLine("ALMUERZO EJECUTIVO", Decimal("4"), Decimal("10000"), Decimal("0")),
    )
    assert doc.payable_amount == Decimal("10000.00")


def test_attached_document_unwraps_embedded_invoice(xml_fixtures_dir: Path) -> None:
    doc = parse_fixture(xml_fixtures_dir, "attached_document_invoice.xml")
    assert doc.kind is DocumentKind.INVOICE
    assert doc.cufe == cufe("attached_document_invoice")
    assert doc.supplier_nit == "800987654"
    assert doc.supplier_name == "SERVICIOS TECNICOS DEMO LTDA"
    # No toma el cbc:ID del contenedor (AD-0099887766)
    assert (doc.supplier_prefix, doc.supplier_number) == ("SETT", "2045")
    assert doc.issue_date == date(2026, 8, 31)
    assert doc.due_date == date(2026, 9, 15)
    assert doc.lines == (
        ParsedLine("SERVICIO TECNICO", Decimal("1"), Decimal("168067.23"), Decimal("19")),
    )
    assert doc.payable_amount == Decimal("200000.00")
    assert doc.source_file == xml_fixtures_dir / "attached_document_invoice.xml"


@pytest.mark.parametrize(
    "name",
    [
        "invoice_plain.xml",
        "credit_note.xml",
        "invoice_with_discount.xml",
        "invoice_mixed_iva.xml",
        "invoice_without_due_date.xml",
        "attached_document_invoice.xml",
    ],
)
def test_every_fixture_totals_match_payable(xml_fixtures_dir: Path, name: str) -> None:
    doc = parse_fixture(xml_fixtures_dir, name)
    assert check_totals(doc.lines, doc.payable_amount).matches


def test_application_response_is_unsupported(xml_fixtures_dir: Path) -> None:
    with pytest.raises(UnsupportedDocumentError, match="ApplicationResponse"):
        parse_fixture(xml_fixtures_dir, "application_response.xml")


def test_malformed_xml_is_invalid() -> None:
    with pytest.raises(InvalidDocumentError):
        LxmlDianParser().parse(b"<Invoice><broken", Path("x.xml"))


def test_empty_content_is_invalid() -> None:
    with pytest.raises(InvalidDocumentError):
        LxmlDianParser().parse(b"", Path("x.xml"))


def test_invoice_missing_uuid_is_invalid(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_plain.xml").read_bytes()
    broken = content.replace(b"<cbc:UUID", b"<cbc:NotUUID").replace(
        b"</cbc:UUID>", b"</cbc:NotUUID>"
    )
    with pytest.raises(InvalidDocumentError, match="UUID"):
        LxmlDianParser().parse(broken, Path("x.xml"))


def test_invoice_without_lines_is_invalid(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_plain.xml").read_bytes()
    broken = content.replace(b"cac:InvoiceLine>", b"cac:OtherLine>")
    with pytest.raises(InvalidDocumentError):
        LxmlDianParser().parse(broken, Path("x.xml"))


def test_zero_quantity_line_is_invalid(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_without_due_date.xml").read_bytes()
    broken = content.replace(b'unitCode="94">4.00<', b'unitCode="94">0.00<')
    assert broken != content
    with pytest.raises(InvalidDocumentError):
        LxmlDianParser().parse(broken, Path("x.xml"))


def test_non_numeric_amount_is_invalid(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_plain.xml").read_bytes()
    broken = content.replace(b">184450.00</cbc:PayableAmount>", b">abc</cbc:PayableAmount>")
    with pytest.raises(InvalidDocumentError):
        LxmlDianParser().parse(broken, Path("x.xml"))


def test_supplier_nit_with_dash_dv_drops_it(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_plain.xml").read_bytes()
    patched = content.replace(b">900123456</cbc:CompanyID>", b">900123456-7</cbc:CompanyID>")
    doc = LxmlDianParser().parse(patched, Path("x.xml"))
    assert doc.supplier_nit == "900123456"


def test_prefix_derived_when_sts_prefix_missing(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_plain.xml").read_bytes()
    patched = content.replace(b"<sts:Prefix>FEV</sts:Prefix>", b"")
    doc = LxmlDianParser().parse(patched, Path("x.xml"))
    assert (doc.supplier_prefix, doc.supplier_number) == ("FEV", "1001")


def test_numeric_only_id_has_empty_prefix(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_plain.xml").read_bytes()
    patched = content.replace(b"<sts:Prefix>FEV</sts:Prefix>", b"").replace(
        b"<cbc:ID>FEV1001</cbc:ID>", b"<cbc:ID>1001</cbc:ID>"
    )
    doc = LxmlDianParser().parse(patched, Path("x.xml"))
    assert (doc.supplier_prefix, doc.supplier_number) == ("", "1001")


def test_due_date_falls_back_to_payment_due_date(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_plain.xml").read_bytes()
    patched = content.replace(b"<cbc:DueDate>2026-09-30</cbc:DueDate>", b"").replace(
        b"<cbc:PaymentDueDate>2026-09-30", b"<cbc:PaymentDueDate>2026-10-10"
    )
    doc = LxmlDianParser().parse(patched, Path("x.xml"))
    assert doc.due_date == date(2026, 10, 10)


def test_line_tax_ignores_non_iva_schemes(xml_fixtures_dir: Path) -> None:
    content = (xml_fixtures_dir / "invoice_without_due_date.xml").read_bytes()
    # Línea con impuesto al consumo (04) pero sin IVA -> 0%
    inc_tax = (
        b"<cac:TaxTotal><cbc:TaxAmount>800.00</cbc:TaxAmount><cac:TaxSubtotal>"
        b"<cac:TaxCategory><cbc:Percent>8.00</cbc:Percent>"
        b"<cac:TaxScheme><cbc:ID>04</cbc:ID><cbc:Name>INC</cbc:Name></cac:TaxScheme>"
        b"</cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal><cac:Item>"
    )
    patched = content.replace(b"<cac:Item>", inc_tax, 1)
    assert patched != content
    doc = LxmlDianParser().parse(patched, Path("x.xml"))
    assert doc.lines[0].tax_percent == Decimal("0")


def test_external_entities_are_not_resolved(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    xml = (
        f'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "{secret.as_uri()}">]>'
        '<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">&x;</Invoice>'
    ).encode()
    with pytest.raises(InvalidDocumentError) as info:
        LxmlDianParser().parse(xml, Path("x.xml"))
    assert "TOPSECRET" not in str(info.value)


def test_attached_document_without_embedded_document_is_invalid() -> None:
    xml = (
        b'<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:'
        b'AttachedDocument-2"/>'
    )
    with pytest.raises(InvalidDocumentError):
        LxmlDianParser().parse(xml, Path("x.xml"))


def test_attached_document_with_unsupported_embedded_is_unsupported(
    xml_fixtures_dir: Path,
) -> None:
    inner = (xml_fixtures_dir / "application_response.xml").read_text(encoding="utf-8")
    xml = (
        '<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:'
        'AttachedDocument-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:'
        'CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:'
        'xsd:CommonBasicComponents-2"><cac:Attachment><cac:ExternalReference>'
        f"<cbc:Description><![CDATA[{inner}]]></cbc:Description>"
        "</cac:ExternalReference></cac:Attachment></AttachedDocument>"
    ).encode()
    with pytest.raises(UnsupportedDocumentError):
        LxmlDianParser().parse(xml, Path("x.xml"))
