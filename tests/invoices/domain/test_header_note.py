from contabilizador.invoices.domain.header_note import HEADER_NOTE_MAX_LENGTH, build_header_note


def test_joins_descriptions_with_ampersand() -> None:
    assert build_header_note(["RESMA", "TONER"]) == "RESMA & TONER"


def test_single_description() -> None:
    assert build_header_note(["SILLA"]) == "SILLA"


def test_strips_each_description() -> None:
    assert build_header_note([" RESMA ", "TONER\n"]) == "RESMA & TONER"


def test_truncates_to_499_characters() -> None:
    note = build_header_note(["X" * 300, "Y" * 300])
    assert HEADER_NOTE_MAX_LENGTH == 499
    assert len(note) == 499
    assert note.startswith("X" * 300 + " & ")


def test_empty() -> None:
    assert build_header_note([]) == ""
