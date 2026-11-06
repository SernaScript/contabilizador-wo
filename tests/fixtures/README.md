# Test fixtures

## `xml/` — SYNTHETIC DIAN UBL 2.1 documents

All XML files here are **synthetic and anonymized**: fake NITs, fake names, fake CUFE/CUDE
(SHA-384 of the fixture name). They mimic the real DIAN structure (namespaces, `ext:UBLExtensions`
with `sts:DianExtensions`, `ds:Signature` stub, supplier/customer parties, taxes, totals).

Real supplier XMLs go in `ejemplos/xml/` (git-ignored, never committed). When real samples arrive,
add anonymized copies here instead of replacing these.

Common traps the parser must handle:

- Many `cbc:ID` elements appear **before** the document `cbc:ID` (`sts:ProviderID`,
  `sts:SoftwareID`, address IDs, tax scheme IDs...). Never use `//cbc:ID`.
- Supplier NIT: `cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID`;
  the verification digit is in `@schemeID` and must be dropped. The customer party has
  another NIT (`901000001`) that must NOT be used.
- Invoice prefix: `sts:DianExtensions/sts:InvoiceControl/sts:AuthorizedInvoices/sts:Prefix`;
  number = `cbc:ID` without that prefix (keep leading zeros). Credit notes have no
  `InvoiceControl`: split the leading letters of `cbc:ID` as prefix.
- `cac:WithholdingTaxTotal` (ReteRenta) does not change `PayableAmount`; ignore it.
- Lines may have no `cac:TaxTotal` (excluded items) -> `tax_percent = 0`.

| File | Kind | CUFE (first 8) | Supplier NIT / name | Prefix / number | Issue / due | Lines (desc, qty, line ext, %IVA) | Payable |
|---|---|---|---|---|---|---|---|
| `invoice_plain.xml` | Invoice | `718b2e03` | 900123456 (DV 7) COMERCIALIZADORA EJEMPLO S.A.S. | FEV / 1001 | 2026-08-31 / 2026-09-30 | RESMA PAPEL CARTA 75G, 3, 30000.00, 19 · TONER IMPRESORA LASER, 1, 125000.00, 19 | 184450.00 |
| `credit_note.xml` | CreditNote | `893b685b` | 900123456 COMERCIALIZADORA EJEMPLO S.A.S. | NC / 125 | 2026-09-05 / none | RESMA PAPEL CARTA 75G, 1, 10000.00, 19 | 11900.00 |
| `invoice_with_discount.xml` | Invoice | `3f907567` | 900123456 | FEV / 1002 | 2026-09-02 / 2026-10-02 | SILLA ERGONOMICA OFICINA, 2, 90000.00 (100000 − 10000 line `AllowanceCharge`), 19 | 107100.00 |
| `invoice_mixed_iva.xml` | Invoice | `ff593798` | 900123456 | FEV / 1003 | 2026-09-03 / 2026-10-03 | PORTATIL 14 PULGADAS, 1, 100000.00, 19 · CAFE MOLIDO 500G, 2, 50000.00, 5 · LIBRO CONTABILIDAD BASICA, 1, 30000.00, 0 | 201500.00 |
| `invoice_without_due_date.xml` | Invoice | `457aa951` | 1017000111 (DV 3) PEDRO PRUEBA RESTREPO | FE / 00450 | 2026-09-04 / none | ALMUERZO EJECUTIVO, 4, 10000.00, no TaxTotal (0) | 10000.00 |
| `attached_document_invoice.xml` | AttachedDocument wrapping Invoice | `41d4556c` | 800987654 (DV 1) SERVICIOS TECNICOS DEMO LTDA | SETT / 2045 | 2026-08-31 / 2026-09-15 | SERVICIO TECNICO, 1, 168067.23, 19 | 200000.00 |
| `application_response.xml` | ApplicationResponse | — | — | — | — | must be ignored (UnsupportedDocumentError) | — |
| `invoices_bundle.zip` | zip | — | — | — | — | `invoice_plain.xml` + `septiembre/credit_note.xml` | — |

Details:

- `credit_note.xml`: `cac:BillingReference/cac:InvoiceDocumentReference/cbc:UUID` = CUFE of
  `invoice_plain.xml` (`718b2e03...`); `cbc:UUID@schemeName = CUDE-SHA384`; line tag
  `cac:CreditNoteLine` with `cbc:CreditedQuantity`.
- `attached_document_invoice.xml`: root `AttachedDocument` has its own `cbc:ID`
  (`AD-0099887766`) and `cbc:ParentDocumentID` (`SETT2045`) before the embedded invoice. The
  invoice is a CDATA in `cac:Attachment/cac:ExternalReference/cbc:Description`. A second
  CDATA (an `ApplicationResponse`) lives in
  `cac:ParentDocumentLineReference/cac:DocumentReference/cac:Attachment/.../cbc:Description`
  and must NOT be taken as the document.
- Full CUFEs: read them from the XML (`cbc:UUID`), or compute
  `hashlib.sha384(b"<fixture name without .xml>").hexdigest()`.

Fixtures were generated once by a throwaway script; edit the XML directly if needed and keep
this table in sync.

## `world_office_golden.xlsx`

Official World Office purchase import workbook (26 FC documents / 145 inventory lines),
the export contract: sheets `Encabezados` and `Movimiento inventarios`, 14 columns each.
