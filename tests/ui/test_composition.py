from pathlib import Path

from sqlalchemy import inspect

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.shared.db import create_engine_for
from contabilizador.ui.composition import Services, build_services


def test_build_services_migrates_database_and_wires_use_cases(
    tmp_path: Path, xml_fixtures_dir: Path
) -> None:
    db_path = tmp_path / "data" / "app.db"

    services = build_services(db_path)

    assert isinstance(services, Services)
    engine = create_engine_for(db_path)
    assert "invoices" in inspect(engine).get_table_names()
    engine.dispose()

    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    assert company.id is not None
    report = services.import_invoices.execute(company.id, [xml_fixtures_dir])
    assert len(report.imported) == 6  # 6 documentos; el zip repite dos CUFE
    pending = services.list_pending.execute(company.id)
    assert len(pending.documents) == 6
    assert len(report.duplicates) == 2
    assert len(pending.unconfigured_suppliers) == 3
    services.close()


def test_build_services_wires_the_redesign_use_cases(
    tmp_path: Path, xml_fixtures_dir: Path
) -> None:
    services = build_services(tmp_path / "app.db")
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    assert company.id is not None
    services.import_invoices.execute(company.id, [xml_fixtures_dir])
    pending = services.list_pending.execute(company.id)
    cufes = [document.invoice.document.cufe for document in pending.documents]

    blocked = services.preview_export.execute(company.id, cufes)
    assert [assessment.cufe for assessment in blocked.documents] == cufes
    assert blocked.exportable_cufes == ()  # proveedores sin configurar

    services.save_product.execute(company.id, "P-1", "Papeleria")
    services.save_cost_center.execute(company.id, "CC-1", "Administracion")
    for supplier in pending.unconfigured_suppliers:
        services.configure_supplier.execute(company.id, supplier.nit, supplier.name, ["P-1"], "P-1")
    services.assign_document_mapping.execute(
        company.id, [document.invoice.id for document in pending.documents], cost_center_code="CC-1"
    )
    ready = services.preview_export.execute(company.id, cufes)
    assert set(ready.exportable_cufes) == set(cufes)

    template = tmp_path / "plantilla.xlsx"
    services.write_catalog_template.execute(template, CatalogKind.PRODUCT)
    assert template.is_file()
    services.close()
