"""Unit tests for the XLSX handler's pure reference-rewriting logic.

The dangerous case is a sheet name with a trailing space (表紙 ), which appears
QUOTED in references ('表紙 '!A1) and whose romanization also gains an internal
space (見積条件 -> Mitsumori Jōken), forcing the rewritten reference to be quoted
too. That is exactly where naive string replacement breaks.
"""

import pytest

from romanizer.handlers import xlsx_handler as X


# --- rewrite_sheet_refs ----------------------------------------------------

NAME_MAP = {
    "内訳": "Uchiwake",
    "表紙 ": "Hyōshi",            # trailing space in the original name
    "見積条件": "Mitsumori Jōken",  # romaji gains an internal space
}


def test_unquoted_reference_becomes_quoted():
    assert X.rewrite_sheet_refs("内訳!G22", NAME_MAP) == "'Uchiwake'!G22"


def test_quoted_trailing_space_reference():
    assert X.rewrite_sheet_refs("'表紙 '!$B$1:$M$23", NAME_MAP) == "'Hyōshi'!$B$1:$M$23"


def test_reference_to_name_whose_romaji_has_a_space_is_quoted():
    assert X.rewrite_sheet_refs("見積条件!$1:$1", NAME_MAP) == "'Mitsumori Jōken'!$1:$1"


def test_reference_inside_a_larger_formula():
    assert X.rewrite_sheet_refs("SUM(内訳!A1,内訳!A2)", NAME_MAP) == (
        "SUM('Uchiwake'!A1,'Uchiwake'!A2)"
    )


def test_non_reference_text_is_untouched():
    assert X.rewrite_sheet_refs("A1+B2*3", NAME_MAP) == "A1+B2*3"


def test_double_quoted_literal_is_not_treated_as_a_reference():
    # "内訳" here is a string literal (double quotes), not a sheet ref.
    assert X.rewrite_sheet_refs('A1&"内訳"', NAME_MAP) == 'A1&"内訳"'


def test_empty_and_none():
    assert X.rewrite_sheet_refs("", NAME_MAP) == ""
    assert X.rewrite_sheet_refs(None, NAME_MAP) is None


# --- romanize_formula_literals ---------------------------------------------

def test_literal_is_romanized(dic=None):
    from romanizer import dictionary
    d = dictionary.default()
    assert X.romanize_formula_literals('B52&"合計"', d) == 'B52&"Gōkei"'


def test_multiple_literals():
    from romanizer import dictionary
    d = dictionary.default()
    assert X.romanize_formula_literals('"東京"&"大阪"', d) == '"Tōkyō"&"Ōsaka"'


def test_non_japanese_literal_untouched():
    from romanizer import dictionary
    d = dictionary.default()
    assert X.romanize_formula_literals('IF(A1>0,"OK","NG")', d) == 'IF(A1>0,"OK","NG")'


def test_reference_is_not_treated_as_a_literal():
    from romanizer import dictionary
    d = dictionary.default()
    # Single-quoted sheet ref must be left alone by the literal pass.
    assert X.romanize_formula_literals("'内訳'!A1", d) == "'内訳'!A1"


# --- sheet_name_map --------------------------------------------------------

def test_sheet_name_map_trims_whitespace():
    from lxml import etree

    xml = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheets><sheet name="内訳"/><sheet name="表紙 "/><sheet name="Sheet1"/></sheets>'
        "</workbook>"
    )
    from romanizer import dictionary

    mapping = X.sheet_name_map(etree.fromstring(xml), dictionary.default())
    assert mapping["内訳"] == "Uchiwake"
    assert mapping["表紙 "] == "Hyōshi"       # trailing space trimmed
    assert "Sheet1" not in mapping             # no Japanese, not remapped
