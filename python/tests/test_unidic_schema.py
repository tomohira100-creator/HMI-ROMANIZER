"""Guard the UniDic feature-vector layout.

core.py reads the pron and kana readings by numeric index. Those indices are
not stable across UniDic releases: kana sits at field 20 in UniDic 3.1.0 and
at field 17 in unidic-lite's UniDic 2.x. Reading the wrong index does not
raise, it silently returns an unrelated field, and every long vowel loses its
macron. These tests fail loudly if the layout shifts under us.
"""

import csv

import pytest

from romanizer import core


def _features(text):
    node = core._get_tagger().parseToNode(text)
    while node:
        if node.surface:
            return next(csv.reader([node.feature]))
        node = node.next
    raise AssertionError("no node produced for {!r}".format(text))


def test_feature_vector_is_csv_not_comma_split():
    """The accent-condition fields are quoted and contain commas."""
    naive = _features("年")
    assert len(naive) == 29, (
        "expected 29 CSV fields for 年, got {}. UniDic layout changed.".format(len(naive))
    )
    # Splitting on commas instead of parsing CSV yields 30 and misaligns kana.
    node = core._get_tagger().parseToNode("年")
    while node and not node.surface:
        node = node.next
    assert len(node.feature.split(",")) == 30


def test_pron_index_is_9():
    assert _features("東京")[core._PRON] == "トーキョー"


def test_kana_index_is_20():
    assert _features("東京")[core._KANA] == "トウキョウ"


def test_field_17_is_not_kana():
    """Explicitly assert the trap: field 17 is the unidic-lite index."""
    assert _features("東京")[17] != "トウキョウ"


def test_numerals_emit_short_vector_without_reading():
    fields = _features("2026")
    assert len(fields) < core._MIN_FIELDS_WITH_READING
    assert fields[core._POS2] == "数詞"


@pytest.mark.parametrize(
    "text,pron,kana",
    [
        ("学生", "ガクセー", "ガクセイ"),
        ("大阪", "オーサカ", "オオサカ"),
        ("こんにちは", "コンニチワ", "コンニチハ"),
    ],
)
def test_pron_and_kana_diverge_as_expected(text, pron, kana):
    fields = _features(text)
    assert fields[core._PRON] == pron
    assert fields[core._KANA] == kana
