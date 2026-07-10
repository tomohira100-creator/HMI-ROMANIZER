"""Dictionary loading, validation, and override behaviour."""

import json

import pytest

from romanizer import core, dictionary, romanize


def write_dicts(tmp_path, custom, abbrev=None):
    (tmp_path / "custom_terms.json").write_text(
        json.dumps(custom, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "abbreviations.json").write_text(
        json.dumps({"abbreviations": abbrev or []}, ensure_ascii=False), encoding="utf-8"
    )
    return dictionary.load(tmp_path)


# --- Shipped dictionary ----------------------------------------------------

def test_company_forms_use_rendaku_from_custom_dictionary():
    # Rendaku is lexical, not rule-governed: 株式会社 is Gaisha, 株式市場 is Shijō.
    assert romanize("株式会社") == "Kabushiki Gaisha"
    assert romanize("有限会社") == "Yūgen Gaisha"
    assert romanize("合同会社") == "Gōdō Gaisha"
    assert romanize("株式市場") == "Kabushiki Shijō"


def test_company_form_composes_with_following_text():
    assert romanize("株式会社ホテル") == "Kabushiki Gaisha Hoteru"


def test_custom_terms_correct_mecab_kanji_date_readings():
    # MeCab reads 十四日 as ジュウ・ヨ・ニチ. Corrected by dictionary, not in code.
    assert romanize("十四日") == "Jūyokka"
    assert romanize("二十四日") == "Nijūyokka"


def test_decoration_name_overrides_the_everyday_reading():
    """旭日中綬章 is the Order of the Rising Sun, Gold Rays with Neck Ribbon.

    MeCab splits it into 旭日 + 中 + 綬章 and reads 旭日 as アサヒ, the everyday
    reading of the characters, giving "Asahijū Jushō". In the name of the
    decoration it is キョクジツ. No override on the parts can repair this: only
    an override on the whole span can. See the compound-splitting limitation
    in ARCHITECTURE.md.
    """
    assert romanize("旭日中綬章") == "Kyokujitsu Chūjushō"
    assert romanize("旭日中綬章受章") == "Kyokujitsu Chūjushō Jushō"
    # The constituent words keep their own readings.
    assert romanize("綬章") == "Jushō"


def test_shipped_dictionaries_load():
    dic = dictionary.load()
    assert "株式会社" in dic.custom_terms
    assert dic.is_abbreviation("hmi")
    assert not dic.is_abbreviation("hotel")


# --- Override semantics ----------------------------------------------------

def test_custom_term_overrides_mecab(tmp_path):
    dic = write_dicts(tmp_path, {"東京": "TOKYO"})
    assert core.romanize("東京", dic) == "TOKYO"


def test_longest_match_wins(tmp_path):
    dic = write_dicts(tmp_path, {"東京": "Short", "東京タワー": "Long"})
    assert core.romanize("東京タワー", dic) == "Long"


def test_literal_value_is_immune_to_title_case(tmp_path):
    dic = write_dicts(tmp_path, {"東京": "tOkYo"})
    assert core.romanize("東京", dic) == "tOkYo"


def test_empty_dictionary_is_a_no_op(tmp_path):
    dic = write_dicts(tmp_path, {})
    assert core.romanize("東京", dic) == "Tōkyō"


def test_custom_term_adjacent_to_japanese_gets_a_space(tmp_path):
    dic = write_dicts(tmp_path, {"株式会社": "Kabushiki Gaisha"})
    assert core.romanize("株式会社ホテル", dic) == "Kabushiki Gaisha Hoteru"


# --- Validation ------------------------------------------------------------

def test_malformed_json_raises(tmp_path):
    (tmp_path / "custom_terms.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    with pytest.raises(dictionary.DictionaryError, match="invalid JSON"):
        dictionary.load(tmp_path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(dictionary.DictionaryError, match="not found"):
        dictionary.load(tmp_path)


def test_non_string_value_raises(tmp_path):
    (tmp_path / "custom_terms.json").write_text('{"東京": 5}', encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    with pytest.raises(dictionary.DictionaryError, match="must be strings"):
        dictionary.load(tmp_path)


def test_empty_key_raises(tmp_path):
    (tmp_path / "custom_terms.json").write_text('{"": "x"}', encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    with pytest.raises(dictionary.DictionaryError, match="empty key"):
        dictionary.load(tmp_path)


def test_abbreviations_reject_non_strings(tmp_path):
    (tmp_path / "custom_terms.json").write_text("{}", encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": [1]}', encoding="utf-8")
    with pytest.raises(dictionary.DictionaryError, match="non-empty strings"):
        dictionary.load(tmp_path)
