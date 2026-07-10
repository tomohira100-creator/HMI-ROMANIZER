"""Katakana to Modified Hepburn romaji conversion.

Modified (revised) Hepburn, per decision D1:
  - Syllabic n is always "n", never "m" (shinbun, not shimbun).
  - Syllabic n before a vowel or y takes an apostrophe (Shin'ichi).
  - Long o, u and a take macrons. Long i and e do not: they are written
    "ii" and "ei" (Atarashii, Sensei), per decision D9. The sole exception
    is a katakana prolonged mark, which always takes a macron (Bīru, Kōhī).

The conversion consumes two parallel katakana strings supplied by UniDic:

  pron  field 9   phonetic reading; long vowels already collapsed to a
                  prolonged mark, particles already resolved to wa/e/o
  kana  field 20  orthographic reading; preserves the ou/oo and ei/ee and
                  ii distinctions that pron has destroyed

Neither string is sufficient alone. pron cannot tell ei from ee (both
become エー) nor ii from a genuine long i. kana cannot tell a long vowel
from two morae, so it would romanize the verb 追う (オウ) as "Ō" instead
of "Ou". Reading pron for vowel length and kana for vowel identity is what
makes both correct. The two strings are index-aligned because pron only
ever substitutes a single character in place (ウ to ー, ハ to ワ).
"""

CHOONPU = "ー"  # ー prolonged sound mark
SOKUON = "ッ"  # ッ small tsu
SYLLABIC_N = "ン"  # ン

MACRON = {"a": "ā", "i": "ī", "u": "ū", "e": "ē", "o": "ō"}

VOWELS = "aiueo"

# Two-character sequences must be matched before single characters.
DIGRAPHS = {
    "キャ": "kya", "キュ": "kyu", "キョ": "kyo",
    "シャ": "sha", "シュ": "shu", "ショ": "sho",
    "チャ": "cha", "チュ": "chu", "チョ": "cho",
    "ニャ": "nya", "ニュ": "nyu", "ニョ": "nyo",
    "ヒャ": "hya", "ヒュ": "hyu", "ヒョ": "hyo",
    "ミャ": "mya", "ミュ": "myu", "ミョ": "myo",
    "リャ": "rya", "リュ": "ryu", "リョ": "ryo",
    "ギャ": "gya", "ギュ": "gyu", "ギョ": "gyo",
    "ジャ": "ja", "ジュ": "ju", "ジョ": "jo",
    "ヂャ": "ja", "ヂュ": "ju", "ヂョ": "jo",
    "ビャ": "bya", "ビュ": "byu", "ビョ": "byo",
    "ピャ": "pya", "ピュ": "pyu", "ピョ": "pyo",
    # Loanword extensions.
    "ファ": "fa", "フィ": "fi", "フェ": "fe",
    "フォ": "fo", "フュ": "fyu",
    "ティ": "ti", "ディ": "di", "トゥ": "tu",
    "ドゥ": "du", "テュ": "tyu", "デュ": "dyu",
    "ウィ": "wi", "ウェ": "we", "ウォ": "wo",
    "ヴァ": "va", "ヴィ": "vi", "ヴェ": "ve",
    "ヴォ": "vo",
    "シェ": "she", "ジェ": "je", "チェ": "che",
    "ツァ": "tsa", "ツィ": "tsi", "ツェ": "tse",
    "ツォ": "tso",
    "クァ": "kwa", "グァ": "gwa",
}

MONOGRAPHS = {
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヰ": "i", "ヱ": "e", "ヲ": "o",
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    "ヴ": "vu",
    # Small vowels standing alone.
    "ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o",
    "ャ": "ya", "ュ": "yu", "ョ": "yo",
}

_N_MARKER = "\x00n"


def _lengthen(chunks, kana_char):
    """Extend the trailing vowel of the last chunk, given the orthographic kana."""
    if not chunks:
        return
    last = chunks[-1]
    if last == _N_MARKER or not last or last[-1] not in VOWELS:
        return
    vowel = last[-1]
    # An orthographic イ after e or i is a vowel digraph, not a long vowel:
    # ケイエイ -> keiei, アタラシイ -> atarashii. Everything else lengthens.
    if kana_char == "イ" and vowel in ("e", "i"):
        chunks[-1] = last + "i"
        return
    chunks[-1] = last[:-1] + MACRON[vowel]


def kana_to_romaji(pron, kana=None):
    """Convert a katakana reading to Modified Hepburn romaji, lowercase.

    pron supplies vowel length and particle pronunciation; kana supplies
    vowel identity. When kana is absent or misaligned, pron is used for
    both, which is safe but may write ē where ei is wanted.
    """
    if not pron:
        return ""
    if kana is None or len(kana) != len(pron):
        kana = pron

    chunks = []
    i = 0
    n = len(pron)
    sokuon = False

    while i < n:
        ch = pron[i]

        if ch == CHOONPU:
            _lengthen(chunks, kana[i])
            i += 1
            continue

        if ch == SOKUON:
            sokuon = True
            i += 1
            continue

        if ch == SYLLABIC_N:
            chunks.append(_N_MARKER)
            i += 1
            continue

        pair = pron[i:i + 2]
        if len(pair) == 2 and pair in DIGRAPHS:
            romaji = DIGRAPHS[pair]
            i += 2
        elif ch in MONOGRAPHS:
            romaji = MONOGRAPHS[ch]
            i += 1
        else:
            # Not kana. Emit unchanged rather than guessing.
            chunks.append(ch)
            i += 1
            sokuon = False
            continue

        if sokuon:
            # A geminate before ch is written tch: マッチ -> matchi.
            romaji = "t" + romaji if romaji.startswith("ch") else romaji[0] + romaji
            sokuon = False

        chunks.append(romaji)

    # A word-final sokuon has no consonant to double and is dropped.

    out = []
    for index, chunk in enumerate(chunks):
        if chunk != _N_MARKER:
            out.append(chunk)
            continue
        nxt = chunks[index + 1] if index + 1 < len(chunks) else ""
        if nxt and nxt != _N_MARKER and (nxt[0] in VOWELS or nxt[0] == "y"):
            out.append("n'")
        else:
            out.append("n")
    return "".join(out)
