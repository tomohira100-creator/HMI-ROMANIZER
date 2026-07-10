"""Core romanization tests, one section per category from the Phase 1 plan."""

import pytest

from romanizer import romanize


def r(text):
    return romanize(text)


# --- 1. Hiragana -----------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("こんにちは", "Konnichiwa"),
        ("おおきい", "Ōkii"),
        ("さくら", "Sakura"),
        ("ひらがな", "Hiragana"),
    ],
)
def test_hiragana(source, expected):
    assert r(source) == expected


# --- 2. Katakana -----------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("ホテル", "Hoteru"),
        ("コーヒー", "Kōhī"),
        ("ビール", "Bīru"),
        ("ラーメン", "Rāmen"),
        ("マッチ", "Matchi"),
        ("グループ", "Gurūpu"),
    ],
)
def test_katakana(source, expected):
    assert r(source) == expected


# --- 3. Kanji --------------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("東京", "Tōkyō"),
        ("大阪", "Ōsaka"),
        ("京都", "Kyōto"),
        ("空港", "Kūkō"),
        ("新聞", "Shinbun"),   # modified Hepburn: n, not m
        ("日本橋", "Nihonbashi"),
        ("新宿", "Shinjuku"),
    ],
)
def test_kanji(source, expected):
    assert r(source) == expected


def test_syllabic_n_before_vowel_takes_apostrophe():
    assert r("新一") == "Shin'ichi"


# --- Requirement 2: おお vs おう both yield macrons -------------------------

def test_oo_and_ou_both_produce_macron():
    assert r("大阪") == "Ōsaka"   # kana オオサカ
    assert r("東京") == "Tōkyō"   # kana トウキョウ


# --- Requirement 3: 日本 romanizes consistently ----------------------------
#
# UniDic 3.1.0 reads 日本 as ニッポン, so it romanizes as Nippon. Both Nihon
# and Nippon are correct readings; we take the dictionary's rather than
# override it, per the standing rule not to silently correct MeCab. The
# compound 日本橋 is a distinct lexeme read ニホンバシ and is unaffected.

def test_nihon_reading_is_consistent():
    assert r("日本") == "Nippon"
    assert r("日本の") == "Nippon no"
    assert r("日本語") == "Nippon Go"
    assert r("日本橋") == "Nihonbashi"


# --- 4. Mixed script -------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("お姉さん", "Onēsan"),
        ("読んだ", "Yonda"),
        ("新しい", "Atarashii"),
        ("東京タワー", "Tōkyō Tawā"),
    ],
)
def test_mixed_script(source, expected):
    assert r(source) == expected


# --- 5. English mixed ------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("Hello 世界", "Hello Sekai"),
        ("HMI ホテル", "HMI Hoteru"),
        ("Hello world", "Hello world"),
        ("iPhone", "iPhone"),
    ],
)
def test_english_passthrough(source, expected):
    assert r(source) == expected


def test_english_prose_is_never_upcased_by_abbreviation_list():
    # "It" collides with the IT abbreviation; the list protects, never creates.
    assert r("It is") == "It is"
    assert r("Hr") == "Hr"


# --- 6. Numbers ------------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("123", "123"),
        ("第3四半期", "Dai 3 Shihanki"),
        ("A4", "A4"),
    ],
)
def test_numbers(source, expected):
    assert r(source) == expected


def test_kanji_numeral_romanizes_as_reading():
    # Decision D7: kanji numerals romanize; they are not converted to digits.
    assert r("三日") == "Mikka"


# --- 7. Dates --------------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("2026年5月13日", "2026 Nen 5 Gatsu 13 Nichi"),
        ("1月21日", "1 Gatsu 21 Nichi"),
        ("21日", "21 Nichi"),
        ("31日", "31 Nichi"),
        ("11日", "11 Nichi"),
    ],
)
def test_dates_regular(source, expected):
    assert r(source) == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        ("1日", "Tsuitachi"),
        ("2日", "Futsuka"),
        ("3日", "Mikka"),
        ("4日", "Yokka"),
        ("5日", "Itsuka"),
        ("6日", "Muika"),
        ("7日", "Nanoka"),
        ("8日", "Yōka"),
        ("9日", "Kokonoka"),
        ("10日", "Tōka"),
        ("14日", "Jūyokka"),
        ("20日", "Hatsuka"),
        ("24日", "Nijūyokka"),
    ],
)
def test_dates_irregular_absorb_the_numeral(source, expected):
    assert r(source) == expected


# --- 8. Abbreviations ------------------------------------------------------

@pytest.mark.parametrize("token", ["HMI", "NTT", "JR", "REIT", "JPY"])
def test_abbreviations_survive_uppercase(token):
    assert r(token) == token
    assert r("{} ホテル".format(token)) == "{} Hoteru".format(token)


# --- 9. Macrons ------------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        ("王", "Ō"),            # おう -> ō
        ("大きい", "Ōkii"),      # おお -> ō, いい -> ii
        ("経営", "Keiei"),       # えい -> ei, not ē
        ("先生", "Sensei"),      # えい -> ei
        ("飛行機", "Hikōki"),
        ("空港", "Kūkō"),
        ("ええ", "Ē"),           # ええ -> ē
    ],
)
def test_macrons(source, expected):
    assert r(source) == expected


@pytest.mark.parametrize("source,expected", [("思う", "Omou"), ("追う", "Ou")])
def test_verbs_ending_in_u_never_take_a_macron(source, expected):
    """The う is a separate mora, not a long vowel. pron has no prolonged mark."""
    assert r(source) == expected


# --- 10. Particles ---------------------------------------------------------

@pytest.mark.parametrize(
    "source,expected",
    [
        # UniDic reads 私 as ワタクシ, not ワタシ. Both are valid readings of the
        # character. We take the dictionary's rather than override it: a
        # custom_terms entry for a single kanji is a pre-tokenization
        # substitution and would corrupt every compound containing it, turning
        # 私立 into "Watashi Ri". See test_single_kanji_compounds_are_intact.
        ("私は学生です", "Watakushi wa Gakusei desu"),
        ("海へ行く", "Umi e Iku"),
        ("本を読む", "Hon o Yomu"),
    ],
)
def test_particles(source, expected):
    assert r(source) == expected


@pytest.mark.parametrize(
    "source,expected",
    [("私立", "Shiritsu"), ("私鉄", "Shitetsu"), ("私服", "Shifuku")],
)
def test_single_kanji_compounds_are_intact(source, expected):
    """Guards against 私 ever being added to custom_terms.json."""
    assert r(source) == expected


def test_ha_inside_a_word_is_not_a_particle():
    assert r("話") == "Hanashi"


def test_konnichiwa_is_a_single_token_with_particle_pronunciation():
    """POS alone would say 感動詞 and emit Konnichiha. pron says コンニチワ."""
    assert r("こんにちは") == "Konnichiwa"


# --- 11. Punctuation -------------------------------------------------------

def test_japanese_punctuation_is_preserved_verbatim():
    assert r("・、。「」【】×") == "・、。「」【】×"


def test_punctuation_between_words_is_untouched():
    assert r("東京、大阪") == "Tōkyō、Ōsaka"
    assert r("「東京」") == "「Tōkyō」"


def test_ascii_punctuation_untouched():
    assert r("Hello, world.") == "Hello, world."


# --- 12. Empty and whitespace ---------------------------------------------

@pytest.mark.parametrize("source", ["", "   ", "\n", "\t", "\n\t "])
def test_empty_and_whitespace_round_trip(source):
    assert r(source) == source


def test_leading_and_trailing_whitespace_preserved():
    assert r("  東京  ") == "  Tōkyō  "


def test_none_raises_type_error():
    with pytest.raises(TypeError):
        romanize(None)


def test_non_string_raises_type_error():
    with pytest.raises(TypeError):
        romanize(123)


def test_large_input_completes():
    source = "東京" * 5000
    result = r(source)
    assert result.startswith("Tōkyō")
    assert len(result) > 10000
