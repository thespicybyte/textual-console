import textual_console


def test_import() -> None:
    assert textual_console.__all__ == ["CommandHistory", "strip_ansi"]
