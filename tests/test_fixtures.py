import zipfile

from lxml import etree

EXPECTED_XML = {
    "attached_document_invoice.xml",
    "invoice_plain.xml",
    "credit_note.xml",
    "invoice_with_discount.xml",
    "invoice_mixed_iva.xml",
    "invoice_without_due_date.xml",
    "application_response.xml",
}


def test_xml_fixtures_are_well_formed(xml_fixtures_dir) -> None:
    names = {path.name for path in xml_fixtures_dir.glob("*.xml")}
    assert names >= EXPECTED_XML
    for name in EXPECTED_XML:
        etree.parse(str(xml_fixtures_dir / name))


def test_zip_fixture_contains_two_documents(xml_fixtures_dir) -> None:
    with zipfile.ZipFile(xml_fixtures_dir / "invoices_bundle.zip") as bundle:
        assert len([n for n in bundle.namelist() if n.endswith(".xml")]) == 2


def test_golden_workbook_is_present(golden_workbook_path) -> None:
    assert golden_workbook_path.is_file()
