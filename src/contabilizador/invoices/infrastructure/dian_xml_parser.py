"""lxml adapter that reads DIAN UBL 2.1 Invoice / CreditNote / AttachedDocument XML."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine
from contabilizador.invoices.domain.errors import InvalidDocumentError, UnsupportedDocumentError

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
}
INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CREDIT_NOTE_NS = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
ATTACHED_DOCUMENT_NS = "urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"

IVA_SCHEME_ID = "01"

# Todas las rutas son relativas al elemento (nunca //cbc:ID global: el bug del parser Java)
_PREFIX_PATH = (
    "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sts:DianExtensions/"
    "sts:InvoiceControl/sts:AuthorizedInvoices/sts:Prefix"
)
_SUPPLIER_PARTY = "cac:AccountingSupplierParty/cac:Party"
_EMBEDDED_DOCUMENT_PATH = "cac:Attachment/cac:ExternalReference/cbc:Description"
_XML_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>")
_DERIVED_PREFIX = re.compile(r"^([A-Za-z]*)[-\s]*(.*)$")


def _secure_parser() -> etree.XMLParser:
    # Sin red, sin expansión de entidades (XXE) y sin árboles gigantes
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        load_dtd=False,
        dtd_validation=False,
    )


class LxmlDianParser:
    """Implements ``DocumentParser`` with namespace-aware, element-scoped lookups."""

    def parse(self, content: bytes, source_file: Path) -> ParsedDocument:
        root = self._parse_root(content)
        namespace = etree.QName(root).namespace
        if namespace == ATTACHED_DOCUMENT_NS:
            root = self._unwrap_attached_document(root)
            namespace = etree.QName(root).namespace
        if namespace == INVOICE_NS:
            return _DocumentReader(root, DocumentKind.INVOICE, source_file).read()
        if namespace == CREDIT_NOTE_NS:
            return _DocumentReader(root, DocumentKind.CREDIT_NOTE, source_file).read()
        raise UnsupportedDocumentError(
            f"Tipo de documento no soportado: {etree.QName(root).localname}"
        )

    @staticmethod
    def _parse_root(content: bytes) -> etree._Element:
        if not content.strip():
            raise InvalidDocumentError("El archivo XML está vacío")
        try:
            root = etree.fromstring(content, parser=_secure_parser())
        except etree.XMLSyntaxError as error:
            raise InvalidDocumentError(f"XML mal formado: {error}") from error
        if root is None:
            raise InvalidDocumentError("El archivo XML no tiene elemento raíz")
        return root

    def _unwrap_attached_document(self, root: etree._Element) -> etree._Element:
        # El documento real viaja como CDATA en cac:Attachment (no en ParentDocumentLineReference)
        embedded = root.findtext(_EMBEDDED_DOCUMENT_PATH, namespaces=NS)
        if embedded is None or not embedded.strip():
            raise InvalidDocumentError("AttachedDocument sin documento embebido")
        # La declaración XML puede traer encoding; se quita y se reencoda en UTF-8
        text = _XML_DECLARATION.sub("", embedded.strip(), count=1)
        inner = self._parse_root(text.encode("utf-8"))
        if etree.QName(inner).namespace == ATTACHED_DOCUMENT_NS:
            raise UnsupportedDocumentError("AttachedDocument anidado no soportado")
        return inner


class _DocumentReader:
    def __init__(self, root: etree._Element, kind: DocumentKind, source_file: Path) -> None:
        self._root = root
        self._kind = kind
        self._source_file = source_file

    def read(self) -> ParsedDocument:
        root = self._root
        document_id = _required_text(root, "cbc:ID")
        prefix, number = _split_number(document_id, root.findtext(_PREFIX_PATH, namespaces=NS))
        due_text = _optional_text(root, "cbc:DueDate") or _optional_text(
            root, "cac:PaymentMeans/cbc:PaymentDueDate"
        )
        billing_reference = (
            _optional_text(root, "cac:BillingReference/cac:InvoiceDocumentReference/cbc:UUID")
            if self._kind is DocumentKind.CREDIT_NOTE
            else None
        )
        return ParsedDocument(
            cufe=_required_text(root, "cbc:UUID"),
            kind=self._kind,
            supplier_nit=self._supplier_nit(),
            supplier_name=self._supplier_name(),
            supplier_prefix=prefix,
            supplier_number=number,
            issue_date=_to_date(_required_text(root, "cbc:IssueDate"), "IssueDate"),
            due_date=_to_date(due_text, "DueDate") if due_text else None,
            lines=self._lines(),
            payable_amount=_to_decimal(
                _required_text(root, "cac:LegalMonetaryTotal/cbc:PayableAmount"),
                "PayableAmount",
            ),
            billing_reference_cufe=billing_reference,
            source_file=self._source_file,
        )

    def _supplier_nit(self) -> str:
        raw = _required_text(self._root, f"{_SUPPLIER_PARTY}/cac:PartyTaxScheme/cbc:CompanyID")
        # El DV va en @schemeID; algunos proveedores lo pegan con guion (900123456-7)
        nit = re.sub(r"\D", "", raw.split("-", 1)[0])
        if not nit:
            raise InvalidDocumentError(f"NIT de proveedor inválido: {raw!r}")
        return nit

    def _supplier_name(self) -> str:
        for path in (
            "cac:PartyTaxScheme/cbc:RegistrationName",
            "cac:PartyLegalEntity/cbc:RegistrationName",
            "cac:PartyName/cbc:Name",
        ):
            name = _optional_text(self._root, f"{_SUPPLIER_PARTY}/{path}")
            if name:
                return name
        raise InvalidDocumentError("Falta el nombre del proveedor")

    def _lines(self) -> tuple[ParsedLine, ...]:
        if self._kind is DocumentKind.INVOICE:
            line_tag, quantity_tag = "cac:InvoiceLine", "cbc:InvoicedQuantity"
        else:
            line_tag, quantity_tag = "cac:CreditNoteLine", "cbc:CreditedQuantity"
        elements = self._root.findall(line_tag, namespaces=NS)
        if not elements:
            raise InvalidDocumentError("El documento no tiene líneas")
        return tuple(_read_line(element, quantity_tag) for element in elements)


def _read_line(element: etree._Element, quantity_tag: str) -> ParsedLine:
    # Un ítem puede traer varias cbc:Description; se unen con espacio
    descriptions = [
        (node.text or "").strip()
        for node in element.findall("cac:Item/cbc:Description", namespaces=NS)
    ]
    quantity = _to_decimal(_required_text(element, quantity_tag), quantity_tag)
    try:
        return ParsedLine(
            description=" ".join(d for d in descriptions if d),
            quantity=quantity,
            line_extension_amount=_to_decimal(
                _required_text(element, "cbc:LineExtensionAmount"), "LineExtensionAmount"
            ),
            tax_percent=_iva_percent(element),
        )
    except ValueError as error:
        raise InvalidDocumentError(f"Línea inválida: {error}") from error


def _iva_percent(line: etree._Element) -> Decimal:
    for category in line.findall("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory", namespaces=NS):
        if category.findtext("cac:TaxScheme/cbc:ID", namespaces=NS, default="").strip() == (
            IVA_SCHEME_ID
        ):
            return _to_decimal(_required_text(category, "cbc:Percent"), "Percent")
    # Línea excluida o sin IVA
    return Decimal(0)


def _split_number(document_id: str, authorized_prefix: str | None) -> tuple[str, str]:
    prefix = (authorized_prefix or "").strip()
    if prefix and document_id.startswith(prefix) and len(document_id) > len(prefix):
        return prefix, document_id[len(prefix) :].lstrip("- ")
    # Sin sts:Prefix (p. ej. notas crédito): las letras iniciales son el prefijo
    match = _DERIVED_PREFIX.match(document_id)
    if match is None or not match.group(2):
        return "", document_id
    return match.group(1), match.group(2)


def _optional_text(element: etree._Element, path: str) -> str | None:
    text = element.findtext(path, namespaces=NS)
    if text is None:
        return None
    return text.strip() or None


def _required_text(element: etree._Element, path: str) -> str:
    text = _optional_text(element, path)
    if text is None:
        raise InvalidDocumentError(f"Falta el elemento requerido {path}")
    return text


def _to_decimal(text: str, field: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as error:
        raise InvalidDocumentError(f"Valor numérico inválido en {field}: {text!r}") from error
    if not value.is_finite():
        raise InvalidDocumentError(f"Valor numérico inválido en {field}: {text!r}")
    return value


def _to_date(text: str, field: str) -> date:
    try:
        return date.fromisoformat(text[:10])
    except ValueError as error:
        raise InvalidDocumentError(f"Fecha inválida en {field}: {text!r}") from error
