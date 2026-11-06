"""Spanish UI copy, centralized by area. Never hardcode user-facing text in widgets.

Each area module owns the names of one page; this package re-exports all of them so
``from contabilizador.shared import strings`` keeps working. A test fails when a public
name is defined in two area modules.
"""

from contabilizador.shared.strings.batches import *
from contabilizador.shared.strings.catalogs import *
from contabilizador.shared.strings.common import *
from contabilizador.shared.strings.companies import *
from contabilizador.shared.strings.errors import *
from contabilizador.shared.strings.export import *
from contabilizador.shared.strings.invoices import *
from contabilizador.shared.strings.onboarding import *
from contabilizador.shared.strings.shortcuts import *
from contabilizador.shared.strings.suppliers import *
