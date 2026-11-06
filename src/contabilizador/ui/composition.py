"""Composition root: builds the database, repositories and use cases the UI needs.

The UI depends only on this module and the application layer; infrastructure
adapters are chosen here.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from contabilizador.catalog.application.catalog_template import WriteCatalogTemplate
from contabilizador.catalog.application.import_catalog import ImportCatalogFromExcel
from contabilizador.catalog.application.ports import CostCenterRepository, ProductRepository
from contabilizador.catalog.application.use_cases import (
    DeleteCostCenter,
    DeleteProduct,
    ListCostCenters,
    ListProducts,
    SaveCostCenter,
    SaveProduct,
)
from contabilizador.catalog.infrastructure.excel_reader import OpenpyxlCatalogSheetReader
from contabilizador.catalog.infrastructure.repository import (
    SqlAlchemyCostCenterRepository,
    SqlAlchemyProductRepository,
)
from contabilizador.catalog.infrastructure.template_writer import OpenpyxlCatalogTemplateWriter
from contabilizador.companies.application.ports import CompanyRepository
from contabilizador.companies.application.use_cases import (
    CreateCompany,
    DeleteCompany,
    ListCompanies,
    UpdateCompany,
)
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository
from contabilizador.exports.application.export_batch import ExportBatch
from contabilizador.exports.application.manage_batches import (
    ListBatches,
    ReleaseDocuments,
    VoidBatch,
)
from contabilizador.exports.application.plan_consecutives import PlanConsecutives
from contabilizador.exports.application.preview_export import PreviewExport
from contabilizador.exports.infrastructure.invoice_candidate_source import (
    InvoiceExportCandidateSource,
)
from contabilizador.exports.infrastructure.repositories import (
    SqlAlchemyBatchRepository,
    SqlAlchemyConsecutiveRepository,
)
from contabilizador.exports.infrastructure.workbook_writer import WorldOfficeWorkbookWriter
from contabilizador.invoices.application.assign_document_mapping import AssignDocumentMapping
from contabilizador.invoices.application.assign_line_mapping import AssignLineMapping
from contabilizador.invoices.application.import_invoice_files import ImportInvoiceFiles
from contabilizador.invoices.application.list_pending_documents import ListPendingDocuments
from contabilizador.invoices.application.ports import InvoiceRepository
from contabilizador.invoices.infrastructure.dian_xml_parser import LxmlDianParser
from contabilizador.invoices.infrastructure.file_document_source import FileDocumentSource
from contabilizador.invoices.infrastructure.sqlalchemy_invoice_repository import (
    SqlAlchemyInvoiceRepository,
)
from contabilizador.invoices.infrastructure.sqlalchemy_mapping_memory_repository import (
    SqlAlchemyMappingMemoryRepository,
)
from contabilizador.shared.db import (
    SqlAlchemyUnitOfWork,
    create_engine_for,
    create_session_factory,
)
from contabilizador.shared.migrations_runner import upgrade_to_head
from contabilizador.suppliers.application.ports import SupplierConfigRepository
from contabilizador.suppliers.application.use_cases import (
    ConfigureSupplier,
    DeleteSupplierConfig,
    ListSupplierConfigs,
)
from contabilizador.suppliers.infrastructure.repository import SqlAlchemySupplierConfigRepository


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Services:
    """Every use case the screens call, plus the repositories some dialogs read."""

    engine: Engine
    companies: CompanyRepository
    suppliers: SupplierConfigRepository
    products: ProductRepository
    cost_centers: CostCenterRepository
    invoices: InvoiceRepository
    # Empresas
    create_company: CreateCompany
    update_company: UpdateCompany
    list_companies: ListCompanies
    delete_company: DeleteCompany
    # Proveedores
    configure_supplier: ConfigureSupplier
    list_supplier_configs: ListSupplierConfigs
    delete_supplier_config: DeleteSupplierConfig
    # Catalogos
    save_product: SaveProduct
    list_products: ListProducts
    delete_product: DeleteProduct
    save_cost_center: SaveCostCenter
    list_cost_centers: ListCostCenters
    delete_cost_center: DeleteCostCenter
    import_catalog: ImportCatalogFromExcel
    write_catalog_template: WriteCatalogTemplate
    # Documentos
    import_invoices: ImportInvoiceFiles
    list_pending: ListPendingDocuments
    assign_mapping: AssignLineMapping
    assign_document_mapping: AssignDocumentMapping
    # Exportacion
    plan_consecutives: PlanConsecutives
    preview_export: PreviewExport
    export_batch: ExportBatch
    void_batch: VoidBatch
    release_documents: ReleaseDocuments
    list_batches: ListBatches

    def close(self) -> None:
        self.engine.dispose()


def build_services(db_path: Path) -> Services:
    """Runs pending migrations on ``db_path`` and wires every adapter and use case."""
    upgrade_to_head(db_path)
    engine = create_engine_for(db_path)
    sessions = create_session_factory(engine)

    companies = SqlAlchemyCompanyRepository(sessions)
    suppliers = SqlAlchemySupplierConfigRepository(sessions)
    products = SqlAlchemyProductRepository(sessions)
    cost_centers = SqlAlchemyCostCenterRepository(sessions)
    invoices = SqlAlchemyInvoiceRepository(sessions)
    memory = SqlAlchemyMappingMemoryRepository(sessions)
    consecutives = SqlAlchemyConsecutiveRepository(sessions)
    batches = SqlAlchemyBatchRepository(sessions)
    unit_of_work = SqlAlchemyUnitOfWork(sessions)

    planner = PlanConsecutives(consecutives=consecutives, batches=batches)
    # la vista previa y la exportacion leen los documentos con la misma fuente
    candidates = InvoiceExportCandidateSource(invoices, memory, suppliers)
    return Services(
        engine=engine,
        companies=companies,
        suppliers=suppliers,
        products=products,
        cost_centers=cost_centers,
        invoices=invoices,
        create_company=CreateCompany(companies),
        update_company=UpdateCompany(companies),
        list_companies=ListCompanies(companies),
        delete_company=DeleteCompany(companies),
        configure_supplier=ConfigureSupplier(suppliers),
        list_supplier_configs=ListSupplierConfigs(suppliers),
        delete_supplier_config=DeleteSupplierConfig(suppliers),
        save_product=SaveProduct(products),
        list_products=ListProducts(products),
        delete_product=DeleteProduct(products),
        save_cost_center=SaveCostCenter(cost_centers),
        list_cost_centers=ListCostCenters(cost_centers),
        delete_cost_center=DeleteCostCenter(cost_centers),
        import_catalog=ImportCatalogFromExcel(OpenpyxlCatalogSheetReader(), products, cost_centers),
        write_catalog_template=WriteCatalogTemplate(OpenpyxlCatalogTemplateWriter()),
        import_invoices=ImportInvoiceFiles(
            FileDocumentSource(LxmlDianParser()), invoices, unit_of_work
        ),
        list_pending=ListPendingDocuments(invoices, memory, suppliers),
        assign_mapping=AssignLineMapping(invoices, memory, unit_of_work),
        assign_document_mapping=AssignDocumentMapping(invoices, memory, suppliers, unit_of_work),
        plan_consecutives=planner,
        preview_export=PreviewExport(
            companies=companies,
            candidates=candidates,
            suppliers=suppliers,
            products=products,
            cost_centers=cost_centers,
            planner=planner,
        ),
        export_batch=ExportBatch(
            companies=companies,
            candidates=candidates,
            suppliers=suppliers,
            products=products,
            cost_centers=cost_centers,
            consecutives=consecutives,
            planner=planner,
            batches=batches,
            exporter=WorldOfficeWorkbookWriter(),
            invoice_status=invoices,
            clock=utc_now,
            unit_of_work=unit_of_work,
        ),
        void_batch=VoidBatch(
            batches=batches,
            consecutives=consecutives,
            invoice_status=invoices,
            unit_of_work=unit_of_work,
        ),
        release_documents=ReleaseDocuments(
            batches=batches, invoice_status=invoices, unit_of_work=unit_of_work
        ),
        list_batches=ListBatches(batches=batches),
    )
