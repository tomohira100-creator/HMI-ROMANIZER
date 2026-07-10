"""Context-sensitive override tests (Phase 1.5).

The mechanism exists for proper nouns. 私 is the fixture that proves it,
because its compounds are the sharpest available negative test: a naive
raw-text substitution rewrites 私立 as "Watashi Ri".
"""

import json

import pytest

from romanizer import core, dictionary


def make_dict(tmp_path, overrides, abbrev=None):
    (tmp_path / "custom_terms.json").write_text(
        json.dumps(overrides, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "abbreviations.json").write_text(
        json.dumps({"abbreviations": abbrev or []}, ensure_ascii=False), encoding="utf-8"
    )
    return dictionary.load(tmp_path)


@pytest.fixture
def watashi(tmp_path):
    return make_dict(tmp_path, {"私": {"romaji": "Watashi", "pos": "代名詞"}})


# --- Span match, single token ---------------------------------------------

def test_standalone_pronoun_is_overridden(watashi):
    assert core.romanize("私", watashi) == "Watashi"


def test_pronoun_overridden_in_a_sentence(watashi):
    assert core.romanize("私は学生です", watashi) == "Watashi wa Gakusei desu"


# --- Negative: single-token compounds must survive -------------------------
#
# UniDic emits each of these as ONE token whose surface is the whole compound.
# No run of tokens concatenates to 私, so the override cannot reach inside.

@pytest.mark.parametrize(
    "source,expected",
    [
        ("私立", "Shiritsu"),
        ("私鉄", "Shitetsu"),
        ("私服", "Shifuku"),
        ("私道", "Shidō"),
    ],
)
def test_compounds_survive_the_pronoun_override(watashi, source, expected):
    assert core.romanize(source, watashi) == expected


def test_compounds_are_unchanged_by_the_override(watashi):
    """The override must make no difference at all to these."""
    for source in ("私立", "私鉄", "私服", "私道"):
        assert core.romanize(source, watashi) == core.romanize(
            source, dictionary.Dictionary.empty()
        )


# --- The honest limit: 私生活 tokenizes as 私 + 生活 ------------------------

def test_shiseikatsu_fires_the_pronoun_override_without_a_longer_entry(watashi):
    """Documents the failure mode rather than hiding it."""
    assert core.romanize("私生活", watashi) == "Watashi Seikatsu"


def test_longer_entry_wins_over_shorter(tmp_path):
    dic = make_dict(
        tmp_path,
        {"私": {"romaji": "Watashi", "pos": "代名詞"}, "私生活": "Shiseikatsu"},
    )
    assert core.romanize("私生活", dic) == "Shiseikatsu"
    assert core.romanize("私は", dic) == "Watashi wa"


# --- Span match across several tokens --------------------------------------
#
# MeCab does not know 白良浜. It emits 白(接頭辞) + 良(名詞) + 浜(名詞).
# A single-token override could never repair it.

def test_multi_token_span_override(tmp_path):
    dic = make_dict(tmp_path, {"白良浜": "Shirarahama"})
    assert core.romanize("白良浜", dic) == "Shirarahama"


def test_multi_token_span_requires_the_whole_span(tmp_path):
    dic = make_dict(tmp_path, {"白良浜": "Shirarahama"})
    # 白良 without 浜 must not match the three-token key.
    assert core.romanize("白良", dic) == core.romanize("白良", dictionary.Dictionary.empty())


def test_span_override_composes_with_surrounding_text(tmp_path):
    dic = make_dict(tmp_path, {"白良浜": "Shirarahama"})
    assert core.romanize("白良浜ホテル", dic) == "Shirarahama Hoteru"


# --- Negative: surname vs common-noun compound -----------------------------
#
# 比較 and 対比 are single tokens; 比べる is a verb. None can be reached by
# a 比良 override.

@pytest.mark.parametrize(
    "source,expected",
    [("比較", "Hikaku"), ("対比", "Taihi"), ("比べる", "Kuraberu")],
)
def test_surname_override_does_not_corrupt_compounds(tmp_path, source, expected):
    dic = make_dict(tmp_path, {"比良": "Hira"})
    assert core.romanize(source, dic) == expected


def test_hira_already_reads_correctly_without_an_override():
    """比良 is a known place name reading ヒラ. It needs no entry."""
    assert core.romanize("比良", dictionary.Dictionary.empty()) == "Hira"


# --- Surname, single token -------------------------------------------------

def test_taira_default_reading():
    assert core.romanize("平良", dictionary.Dictionary.empty()) == "Taira"


def test_taira_can_be_overridden(tmp_path):
    dic = make_dict(tmp_path, {"平良": "Hirara"})
    assert core.romanize("平良", dic) == "Hirara"
    assert core.romanize("平良さん", dic) == "Hirara San"


def test_taira_override_leaves_constituent_kanji_alone(tmp_path):
    dic = make_dict(tmp_path, {"平良": "Hirara"})
    assert core.romanize("良", dic) == core.romanize("良", dictionary.Dictionary.empty())


# --- Overlap ---------------------------------------------------------------

def test_longest_leftmost_wins_on_dates():
    """二十四日 must beat 四日; both are shipped-adjacent shapes."""
    from romanizer import romanize

    assert romanize("二十四日") == "Nijūyokka"
    assert romanize("十四日") == "Jūyokka"


def test_consumed_tokens_are_not_reconsidered(tmp_path):
    dic = make_dict(tmp_path, {"東京タワー": "Tokyo Tower", "タワー": "Tower"})
    assert core.romanize("東京タワー", dic) == "Tokyo Tower"


# --- POS constraint --------------------------------------------------------

def test_pos_constraint_matches(tmp_path):
    dic = make_dict(tmp_path, {"私": {"romaji": "Watashi", "pos": "代名詞"}})
    assert core.romanize("私", dic) == "Watashi"


def test_pos_constraint_that_does_not_match_is_inert(tmp_path):
    dic = make_dict(tmp_path, {"私": {"romaji": "Watashi", "pos": "名詞"}})
    assert core.romanize("私", dic) == "Watakushi"


def test_flat_and_object_forms_are_equivalent(tmp_path):
    flat = make_dict(tmp_path, {"東京": "TOKYO"})
    assert core.romanize("東京", flat) == "TOKYO"
    obj = make_dict(tmp_path, {"東京": {"romaji": "TOKYO"}})
    assert core.romanize("東京", obj) == "TOKYO"


# --- Precedence ------------------------------------------------------------

def test_override_beats_the_counter_table(tmp_path):
    dic = make_dict(tmp_path, {"21日": "Twenty First"})
    assert core.romanize("21日", dic) == "Twenty First"


def test_counter_table_applies_when_no_override(tmp_path):
    dic = make_dict(tmp_path, {})
    assert core.romanize("21日", dic) == "21 Nichi"


def test_override_value_bypasses_title_case(tmp_path):
    dic = make_dict(tmp_path, {"東京": "tOkYo"})
    assert core.romanize("東京", dic) == "tOkYo"


def test_override_value_bypasses_the_abbreviation_list(tmp_path):
    dic = make_dict(tmp_path, {"東京": "hmi"}, abbrev=["HMI"])
    assert core.romanize("東京", dic) == "hmi"


# --- Migration: the five shipped keys still fire ---------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("株式会社", "Kabushiki Gaisha"),
        ("有限会社", "Yūgen Gaisha"),
        ("合同会社", "Gōdō Gaisha"),
        ("十四日", "Jūyokka"),
        ("二十四日", "Nijūyokka"),
    ],
)
def test_shipped_keys_still_fire_in_context(source, expected):
    from romanizer import romanize

    assert romanize(source) == expected
    assert romanize(source + "ホテル").startswith(expected)


def test_shipped_keys_do_not_fire_where_they_should_not():
    from romanizer import romanize

    assert romanize("株式市場") == "Kabushiki Shijō"


# --- Dead entries ----------------------------------------------------------

@pytest.mark.parametrize("key", ["HMI", "abc", "東京 タワー", "東京、大阪", "！"])
def test_dead_entry_raises_under_strict(tmp_path, key):
    (tmp_path / "custom_terms.json").write_text(
        json.dumps({key: "X"}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "abbreviations.json").write_text(
        '{"abbreviations": []}', encoding="utf-8"
    )
    with pytest.raises(dictionary.DictionaryError, match="can never match"):
        dictionary.load(tmp_path, strict=True)


def test_dead_entry_is_collected_under_non_strict(tmp_path):
    (tmp_path / "custom_terms.json").write_text(
        json.dumps({"HMI": "X", "東京": "TOKYO"}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "abbreviations.json").write_text(
        '{"abbreviations": []}', encoding="utf-8"
    )
    dic = dictionary.load(tmp_path, strict=False)
    assert len(dic.warnings) == 1
    assert "HMI" in dic.warnings[0]
    # The healthy entry still loads and still fires.
    assert core.romanize("東京", dic) == "TOKYO"


def test_object_form_requires_romaji(tmp_path):
    (tmp_path / "custom_terms.json").write_text(
        json.dumps({"東京": {"pos": "名詞"}}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "abbreviations.json").write_text(
        '{"abbreviations": []}', encoding="utf-8"
    )
    with pytest.raises(dictionary.DictionaryError, match="needs a non-empty string"):
        dictionary.load(tmp_path)


def test_object_form_rejects_non_string_pos(tmp_path):
    (tmp_path / "custom_terms.json").write_text(
        json.dumps({"東京": {"romaji": "T", "pos": 5}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "abbreviations.json").write_text(
        '{"abbreviations": []}', encoding="utf-8"
    )
    with pytest.raises(dictionary.DictionaryError, match="non-string 'pos'"):
        dictionary.load(tmp_path)


# --- Lint ------------------------------------------------------------------

def test_lint_reports_ok_for_shipped_entries():
    results = dictionary.lint()
    statuses = {key: status for key, status, _ in results}
    assert statuses["株式会社"] == "ok"
    assert statuses["十四日"] == "ok"
    assert "dead" not in statuses.values()


def test_lint_flags_redundant_entry(tmp_path):
    make_dict(tmp_path, {"比良": "Hira"})
    results = dictionary.lint(tmp_path)
    assert results == [("比良", "redundant", "MeCab already produces 'Hira'")]


def test_lint_flags_dead_entry(tmp_path):
    (tmp_path / "custom_terms.json").write_text('{"HMI": "X"}', encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    results = dictionary.lint(tmp_path)
    assert results[0][0] == "HMI"
    assert results[0][1] == "dead"


def test_lint_flags_shadowed_entry(tmp_path):
    """A shorter entry fully covered by a longer one on its own key."""
    make_dict(tmp_path, {"生活": "Seikatsu-X", "私生活": "Shiseikatsu"})
    results = dictionary.lint(tmp_path)
    statuses = {key: status for key, status, _ in results}
    assert statuses["私生活"] == "ok"


# --- lint-dictionary via the CLI -------------------------------------------

def test_cli_lint_shipped_dictionary_exits_zero(capsys):
    from romanizer import cli

    assert cli.main(["lint-dictionary"]) == 0
    out = capsys.readouterr().out
    assert "株式会社" in out
    assert "5 entries: 5 ok" in out


def test_cli_lint_exits_nonzero_on_dead_entry(capsys, tmp_path):
    from romanizer import cli

    (tmp_path / "custom_terms.json").write_text('{"HMI": "X"}', encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    assert cli.main(["lint-dictionary", "--dict-dir", str(tmp_path)]) == 1
    assert "dead" in capsys.readouterr().out


def test_cli_lint_empty_dictionary(capsys, tmp_path):
    from romanizer import cli

    (tmp_path / "custom_terms.json").write_text("{}", encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    assert cli.main(["lint-dictionary", "--dict-dir", str(tmp_path)]) == 0
    assert "empty" in capsys.readouterr().out


def test_cli_lint_reports_malformed_json(capsys, tmp_path):
    from romanizer import cli

    (tmp_path / "custom_terms.json").write_text("{bad", encoding="utf-8")
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    assert cli.main(["lint-dictionary", "--dict-dir", str(tmp_path)]) == 1
    assert "dictionary error" in capsys.readouterr().err


# --- Corpus seam -----------------------------------------------------------

def test_empty_dictionary_exposes_mecab_baseline():
    """Phase 10 corpus tooling depends on this seam."""
    empty = dictionary.Dictionary.empty()
    assert core.romanize("株式会社", empty) == "Kabushiki Kaisha"
    from romanizer import romanize

    assert romanize("株式会社") == "Kabushiki Gaisha"
