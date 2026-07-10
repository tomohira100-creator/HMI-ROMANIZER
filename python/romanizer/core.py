"""The romanization engine: Japanese text in, Hepburn romaji out.

Pure text transformation. No file I/O, no format-specific logic.

Pipeline
    1. Custom-term substitution over the raw string (longest match wins).
       Replacements become literal spans, immune to everything downstream.
    2. Script segmentation into runs. Only Japanese runs reach MeCab.
       Latin, punctuation and whitespace are passed through byte for byte,
       which is what preserves 、。「」【】× rather than rewriting them.
    3. Morphological analysis of Japanese runs via MeCab + UniDic.
    4. Counter correction for 日 and 月 following a numeral.
    5. Grouping of morphemes into words, since a morpheme is not a word:
       読ん + だ is one word, Yonda, not two.
    6. Romanization of each word from its kana and pron readings.
    7. Title Case, with particles, the copula and conjunctions left lower.
"""

import csv
import re
import unicodedata

from . import dictionary as _dictionary
from .hepburn import kana_to_romaji

# --- UniDic feature vector -------------------------------------------------
#
# UniDic 3.1.0 emits 29 comma-separated fields, but the accent-condition
# fields are quoted and contain commas themselves ("B4WW7G9G,B4WW"), so the
# vector must be parsed as CSV, not split on commas. Numerals and unknown
# words emit a short vector with no reading at all.
#
# Field indices differ between UniDic releases: kana is field 20 here but
# field 17 in unidic-lite's UniDic 2.x. Reading the wrong index silently
# destroys every macron, so the index is asserted at import by
# tests/test_unidic_schema.py and pinned in pyproject.toml.

_POS1 = 0
_POS2 = 1
_POS3 = 2
_PRON = 9
_KANA = 20
_MIN_FIELDS_WITH_READING = 21

_UNKNOWN = "*"

_tagger = None


def _get_tagger():
    global _tagger
    if _tagger is None:
        import MeCab
        import unidic

        try:
            _tagger = MeCab.Tagger("-d {}".format(unidic.DICDIR))
        except RuntimeError:
            _tagger = MeCab.Tagger("-r /dev/null -d {}".format(unidic.DICDIR))
    return _tagger


def _parse_features(feature):
    return next(csv.reader([feature]))


class _Token:
    __slots__ = ("surface", "pos1", "pos2", "pos3", "pron", "kana", "literal")

    def __init__(self, surface, pos1, pos2, pos3, pron, kana, literal=None):
        self.surface = surface
        self.pos1 = pos1
        self.pos2 = pos2
        self.pos3 = pos3
        self.pron = pron
        self.kana = kana
        # When set, romanization is bypassed and this string is emitted.
        self.literal = literal

    @property
    def is_numeral(self):
        return self.pos1 == "名詞" and self.pos2 == "数詞"

    @property
    def is_digit_numeral(self):
        return self.is_numeral and _DIGITS_ONLY.match(self.surface) is not None


_DIGITS_ONLY = re.compile(r"^[0-9０-９]+$")
_PROLONGED_ONLY = re.compile(r"^[ー－]+$")


def _tokenize(text):
    tagger = _get_tagger()
    tokens = []
    node = tagger.parseToNode(text)
    while node:
        if node.surface:
            f = _parse_features(node.feature)

            def field(index):
                if len(f) > index and f[index] != _UNKNOWN:
                    return f[index]
                return ""

            pron = field(_PRON)
            kana = field(_KANA) if len(f) >= _MIN_FIELDS_WITH_READING else ""
            tokens.append(
                _Token(
                    node.surface,
                    f[_POS1] if f else "",
                    field(_POS2),
                    field(_POS3),
                    pron,
                    kana,
                )
            )
        node = node.next
    return tokens


# --- Counters --------------------------------------------------------------
#
# MeCab reads 日 as カ after every arabic numeral, including 21日, and reads
# 月 as ツキ rather than ガツ. It supplies no usable signal, so the readings
# below are ours (decision D4).
#
# The irregular day readings already contain the number: 二十日 is Hatsuka,
# not "20 Hatsuka". For those the numeral is absorbed into the reading. All
# other days keep the numeral and take Nichi, matching the PRD's
# 1月21日 -> "1 Gatsu 21 Nichi".

_IRREGULAR_DAYS = {
    1: "Tsuitachi",
    2: "Futsuka",
    3: "Mikka",
    4: "Yokka",
    5: "Itsuka",
    6: "Muika",
    7: "Nanoka",
    8: "Yōka",
    9: "Kokonoka",
    10: "Tōka",
    14: "Jūyokka",
    20: "Hatsuka",
    24: "Nijūyokka",
}

_COUNTER_READINGS = {
    "月": ("ガツ", "ガツ"),
    "日": ("ニチ", "ニチ"),
    "年": ("ネン", "ネン"),
}


def _to_int(surface):
    return int(unicodedata.normalize("NFKC", surface))


def _apply_overrides(tokens, dic):
    """Replace token spans matched by custom_terms with literal romaji.

    Runs before the counter table and before word grouping, so an override
    on 十四日 wins over the day-counter rule. Longest span wins at each
    index; consumed tokens are never reconsidered, so partial overlap
    between two overrides cannot arise.
    """
    out = []
    index = 0
    while index < len(tokens):
        hit = dic.match_tokens(tokens, index)
        if hit is None:
            out.append(tokens[index])
            index += 1
            continue
        span, romaji = hit
        surface = "".join(token.surface for token in tokens[index:index + span])
        out.append(_Token(surface, "名詞", "", "", "", "", literal=romaji))
        index += span
    return out


def _apply_counters(tokens):
    out = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        nxt = tokens[index + 1] if index + 1 < len(tokens) else None

        if (
            token.literal is None
            and nxt is not None
            and nxt.literal is None
            and token.is_digit_numeral
            and nxt.surface in _COUNTER_READINGS
        ):
            value = _to_int(token.surface)
            if nxt.surface == "日" and value in _IRREGULAR_DAYS:
                # The numeral is absorbed: 20日 -> Hatsuka.
                out.append(
                    _Token("{}日".format(token.surface), "名詞", "", "",
                           "", "", literal=_IRREGULAR_DAYS[value])
                )
                index += 2
                continue
            pron, kana = _COUNTER_READINGS[nxt.surface]
            out.append(token)
            out.append(_Token(nxt.surface, "名詞", "", "", pron, kana))
            index += 2
            continue

        out.append(token)
        index += 1
    return out


# --- Word grouping ---------------------------------------------------------
#
# A UniDic morpheme is not a word. Rules, in order of application:
#
#   suffix (接尾辞)      joins the preceding word     日本 + 人 -> Nipponjin
#   auxiliary (助動詞)   joins only after a verb or   読ん + だ -> Yonda
#                        adjective, so that です      学生 + です -> Gakusei desu
#                        after a noun stays separate
#   bound counter noun   joins the preceding word     四半 + 期 -> Shihanki
#   (助数詞可能)         unless the preceding word    飛行 + 機 -> Hikōki
#                        is a numeral                 5 + 月    -> 5 Gatsu
#   prefix (接頭辞)      joins the following word     新 + 一   -> Shin'ichi
#                        unless it is a digit         第 + 3    -> Dai 3
#   conjunctive て/で    joins a verb or adjective     行っ + て -> Itte
#   (助詞/接続助詞)                                   読ん + で -> Yonde
#   particle (助詞)      otherwise stands alone       私 は     -> Watashi wa

_INFLECTABLE = ("動詞", "形容詞", "助動詞")

#: The conjunctive particles て and で attach to the stem they inflect. Leaving
#: them separate does not merely look wrong, it destroys information: MeCab
#: reads 行っ as イッ, and a word-final sokuon has no consonant to double, so
#: 行って romanized as "I Te". 言って, 入って and 射って all collapse to the same
#: string. Joining supplies the following mora and gemination works: "Itte".
#:
#: Both conditions below are load-bearing.
#:
#: The surface must be て or で, because が and から are also 接続助詞 and
#: joining them would give "Ikuga" for 行くが.
#:
#: The part of speech must be 接続助詞, because the で in 東京で is a 格助詞
#: and the で in 静かで is a 助動詞. Neither attaches to anything.
_CONJUNCTIVE_PARTICLES = frozenset({"て", "で"})


class _Word:
    __slots__ = ("pron", "kana", "pos1", "literal", "surface")

    def __init__(self, token):
        self.pron = token.pron
        self.kana = token.kana or token.pron
        self.pos1 = token.pos1
        self.literal = token.literal
        self.surface = token.surface

    def absorb(self, token):
        # An absorbed token may have no reading of its own -- a lone prolonged
        # sound mark, or kana UniDic does not know. Fall back to its kana
        # surface so the reading is not silently dropped.
        fallback = _kana_surface_reading(token.surface) or ""
        self.pron += token.pron or fallback
        self.kana += token.kana or token.pron or fallback
        self.surface += token.surface


def _joins_left(token, previous):
    if previous is None or previous.literal is not None:
        return False
    if _PROLONGED_ONLY.match(token.surface):
        # A prolonged sound mark can never begin a word. MeCab emits it as its
        # own token when the word around it is unknown (くまーる), which would
        # otherwise romanize to an empty atom and leave a doubled space.
        return True
    if token.pos1 == "接尾辞":
        return True
    if (
        token.pos1 == "助詞"
        and token.pos2 == "接続助詞"
        and token.surface in _CONJUNCTIVE_PARTICLES
    ):
        return previous.pos1 in _INFLECTABLE
    if token.pos1 == "助動詞":
        return previous.pos1 in _INFLECTABLE
    if token.pos1 == "名詞" and token.pos3 == "助数詞可能":
        return previous.pos1 != "" and not _is_numeral_word(previous)
    return False


def _is_numeral_word(word):
    return _DIGITS_ONLY.match(word.surface) is not None


def _group_words(tokens):
    words = []
    pending_prefix = None

    for token in tokens:
        if token.pos1 == "接頭辞":
            # 第 before a digit is a word of its own; 新 before 一 is not.
            pending_prefix = token
            continue

        if pending_prefix is not None:
            if token.is_digit_numeral:
                words.append(_Word(pending_prefix))
                words.append(_Word(token))
            else:
                word = _Word(pending_prefix)
                word.absorb(token)
                word.pos1 = token.pos1
                words.append(word)
            pending_prefix = None
            continue

        previous = words[-1] if words else None
        if token.literal is None and _joins_left(token, previous):
            previous.absorb(token)
            continue

        words.append(_Word(token))

    if pending_prefix is not None:
        words.append(_Word(pending_prefix))
    return words


# --- Particle pronunciation ------------------------------------------------
#
# は as wa, へ as e, を as o. We do not decide this ourselves. MeCab has
# already written the pronounced form into pron, so the only difference we
# adopt from pron is exactly these three substitutions. Everything else in
# pron (its collapsed long vowels) is deliberately ignored in favour of kana.
#
# This is also what makes こんにちは correct. It is a single interjection
# token whose kana is コンニチハ but whose pron is コンニチワ, so a rule
# keyed on part of speech alone would emit Konnichiha.

_PRONUNCIATION_SHIFTS = {("ハ", "ワ"), ("ヘ", "エ"), ("ヲ", "オ")}

#: Words UniDic does not know arrive with a 6-field feature vector and no
#: reading at all. When the surface is written in kana that is not a problem:
#: kana is a reading. NFKC folds halfwidth katakana (ﾎﾃﾙ) to fullwidth, and
#: hiragana is shifted into katakana so one romanization table serves both.
_KANA_ONLY = re.compile(r"^[ぁ-ゖァ-ヺーヽヾ]+$")

_HIRAGANA_TO_KATAKANA = 0x30A1 - 0x3041


def _kana_surface_reading(surface):
    """The katakana reading of an all-kana surface, or None if not all kana."""
    folded = unicodedata.normalize("NFKC", surface)
    if not folded or not _KANA_ONLY.match(folded):
        return None
    return "".join(
        chr(ord(char) + _HIRAGANA_TO_KATAKANA) if "ぁ" <= char <= "ゖ" else char
        for char in folded
    )


def _reading(word):
    kana, pron = word.kana, word.pron
    if not kana:
        return pron, pron
    if len(kana) != len(pron):
        return pron, kana
    adjusted = [
        pron[i] if (kana[i], pron[i]) in _PRONUNCIATION_SHIFTS else kana[i]
        for i in range(len(kana))
    ]
    return pron, "".join(adjusted)


# --- Casing ----------------------------------------------------------------
#
# Title Case, English style (decision D3): particles, the copula and
# conjunctions stay lowercase; everything else capitalizes. The first word
# of a string always capitalizes.

LOWERCASE_WORDS = frozenset(
    {
        # Particles: は が を に へ で と も の から まで より
        "wa", "ga", "o", "ni", "e", "de", "to", "mo", "no",
        "kara", "made", "yori",
        # Copula: です だ である
        "desu", "da", "dearu",
    }
)

_LOWERCASE_POS = ("助詞", "助動詞", "接続詞")


def _capitalize(romaji):
    if not romaji:
        return romaji
    return romaji[0].upper() + romaji[1:]


# --- Script segmentation ---------------------------------------------------

_JP = "JP"
_LATIN = "LATIN"
_DIGIT = "DIGIT"
_PUNCT = "PUNCT"
_SPACE = "SPACE"

_HIRAGANA = (0x3041, 0x309F)
_KATAKANA = (0x30A0, 0x30FF)
_KATAKANA_HALF = (0xFF66, 0xFF9D)
_KANJI = (0x4E00, 0x9FFF)
_KANJI_EXT_A = (0x3400, 0x4DBF)


def _in(code, span):
    return span[0] <= code <= span[1]


#: The katakana middle dot lives inside the katakana block (U+30FB) but is
#: punctuation, not a letter. Classifying it as Japanese sends it to MeCab,
#: which returns it as a word-like atom, and 面接・試験 comes out as
#: "Mensetsu ・ Shiken" with spaces the PRD does not want. The prolonged sound
#: mark U+30FC, its neighbour, is a genuine letter and must stay Japanese.
_KATAKANA_PUNCTUATION = "・･"


def _classify(char):
    code = ord(char)
    if char.isspace() or code == 0x3000:
        return _SPACE
    if char in _KATAKANA_PUNCTUATION:
        return _PUNCT
    if char.isdigit() and (char.isascii() or _in(code, (0xFF10, 0xFF19))):
        return _DIGIT
    if char.isascii() and char.isalpha():
        return _LATIN
    if _in(code, (0xFF21, 0xFF3A)) or _in(code, (0xFF41, 0xFF5A)):
        return _LATIN
    if (
        _in(code, _HIRAGANA)
        or _in(code, _KATAKANA)
        or _in(code, _KATAKANA_HALF)
        or _in(code, _KANJI)
        or _in(code, _KANJI_EXT_A)
        or char == "々"
    ):
        return _JP
    return _PUNCT


def _runs(text):
    runs = []
    for char in text:
        kind = _classify(char)
        if runs and runs[-1][0] == kind:
            runs[-1][1] += char
        else:
            runs.append([kind, char])
    return _merge_digits(runs)


def _merge_digits(runs):
    """Attach digit runs to whichever neighbour makes them meaningful.

    A digit beside Latin is part of a token (A4). A digit beside Japanese is
    part of a phrase MeCab must see whole, so that 5月 can find its counter.
    A digit standing alone is passed to MeCab, which returns it unchanged.
    """
    out = []
    for index, (kind, text) in enumerate(runs):
        if kind != _DIGIT:
            out.append([kind, text])
            continue
        prev_kind = runs[index - 1][0] if index else None
        next_kind = runs[index + 1][0] if index + 1 < len(runs) else None
        if prev_kind == _LATIN or next_kind == _LATIN:
            target = _LATIN
        else:
            target = _JP
        if out and out[-1][0] == target:
            out[-1][1] += text
        else:
            out.append([target, text])

    merged = []
    for kind, text in out:
        if merged and merged[-1][0] == kind and kind in (_JP, _LATIN):
            merged[-1][1] += text
        else:
            merged.append([kind, text])
    return merged


# --- Atoms and assembly ----------------------------------------------------

_WORDLIKE = ("ROMAJI", "LATIN")


def _cased_latin(text, dic):
    """Latin passes through untouched, except that abbreviations stay upper.

    The abbreviation list protects uppercase rather than creating it, so the
    English word "It" is not rewritten to "IT".
    """
    if text.isupper() and dic.is_abbreviation(text):
        return text.upper()
    return text


def _romanize_japanese(run, dic, offset):
    # Precedence: override > counter table > MeCab's own reading.
    tokens = _tokenize(run)
    tokens = _apply_overrides(tokens, dic)
    tokens = _apply_counters(tokens)
    words = _group_words(tokens)

    # Every transformation above preserves surfaces, so the words' surfaces
    # concatenate back to the run. That invariant is what lets us hand each
    # atom a source range, which is what the DOCX handler needs to decide
    # which w:r run an output word belongs to.
    atoms = []
    position = offset
    for word in words:
        start = position
        position += len(word.surface)
        end = position

        if word.literal is not None:
            atoms.append(("ROMAJI", word.literal, word, start, end))
            continue
        if _DIGITS_ONLY.match(word.surface):
            atoms.append(("ROMAJI", word.surface, word, start, end))
            continue
        pron, kana = _reading(word)
        if not pron:
            fallback = _kana_surface_reading(word.surface)
            if fallback is not None:
                # UniDic has no entry, but the surface is kana, and kana IS a
                # reading. Foreign names and loanwords absent from the lexicon
                # (アミット, ビサ) would otherwise pass through as Japanese.
                atoms.append(("ROMAJI", kana_to_romaji(fallback), word, start, end))
                continue
            # Unknown kanji: we have no reading and cannot invent one. Emit the
            # surface rather than drop the text.
            atoms.append(("ROMAJI", word.surface, word, start, end))
            continue
        romaji = kana_to_romaji(pron, kana)
        atoms.append(("ROMAJI", romaji, word, start, end))
    return atoms


def _apply_case(atoms, dic):
    out = []
    seen_word = False
    for kind, text, word, start, end in atoms:
        if kind != "ROMAJI" or word is None:
            out.append((kind, text, start, end))
            if kind in _WORDLIKE:
                seen_word = True
            continue
        if _DIGITS_ONLY.match(text) or (word.literal is not None):
            out.append((kind, text, start, end))
            seen_word = True
            continue
        lower = text.lower()
        keep_lower = (
            seen_word
            and word.pos1 in _LOWERCASE_POS
            and lower in LOWERCASE_WORDS
        )
        out.append((kind, text if keep_lower else _capitalize(text), start, end))
        seen_word = True
    return out


def _check_text(text):
    if text is None:
        raise TypeError("romanize() requires a string, got None")
    if not isinstance(text, str):
        raise TypeError("romanize() requires a string, got {}".format(type(text).__name__))


def romanize_spans(text, dic=None):
    """Romanize, returning [(src_start, src_end, output)] instead of a string.

    The spans tile the input: they are contiguous, non-overlapping, ordered,
    and cover [0, len(text)). Joining their outputs reproduces romanize(text)
    exactly, including the spaces inserted between adjacent words -- each such
    space is carried as a prefix of the following span's output rather than
    floating between spans.

    The DOCX handler needs this. Word splits a word across several w:r runs,
    so romanizing a paragraph as one string leaves no way to decide which run
    each output word belongs to. A source range answers that: the output is
    attributed to the run owning its first source character.
    """
    _check_text(text)
    if not text.strip():
        return [(0, len(text), text)] if text else []

    dic = dic or _dictionary.default()

    # Overrides are applied inside _romanize_japanese, against the token
    # stream. They are deliberately not applied here against raw text: a
    # raw-text substitution has no notion of token boundaries and would
    # rewrite 私立 as "Watashi Ri" given an entry for 私.
    atoms = []
    offset = 0
    for kind, run in _runs(text):
        start, offset = offset, offset + len(run)
        if kind == _JP:
            atoms.extend(_romanize_japanese(run, dic, start))
        elif kind == _LATIN:
            atoms.append(("LATIN", _cased_latin(run, dic), None, start, offset))
        elif kind == _SPACE:
            atoms.append(("SPACE", run, None, start, offset))
        else:
            atoms.append(("PUNCT", run, None, start, offset))

    cased = _apply_case(atoms, dic)

    # A single space separates adjacent word-like atoms. Punctuation and
    # whitespace are emitted verbatim, so 東京、大阪 keeps its ideographic
    # comma with no space inserted around it.
    spans = []
    previous_kind = None
    for kind, value, start, end in cased:
        # An atom that romanized to nothing takes no separator, or a word with
        # no reading would leave a doubled space behind it.
        wants_space = kind in _WORDLIKE and previous_kind in _WORDLIKE and value
        spans.append((start, end, (" " if wants_space else "") + value))
        previous_kind = kind
    return spans


def romanize(text, dic=None):
    """Romanize Japanese text into Modified Hepburn, preserving everything else."""
    _check_text(text)
    if not text.strip():
        return text
    return "".join(output for _, _, output in romanize_spans(text, dic))
