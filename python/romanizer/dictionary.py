"""Loading, validation and lookup for the abbreviation and override dictionaries.

Two mechanisms, deliberately kept separate. They do not compete: one decides
the romaji of Japanese tokens, the other decides the casing of Latin runs.

custom_terms.json
    Maps a Japanese surface form to an exact romaji output string. Matching
    happens against the tokenizer's output, not against raw text: a key
    matches a run of one or more consecutive tokens whose surfaces
    concatenate exactly to the key. The run must begin and end on token
    boundaries.

    Token-boundary alignment is the safety property. A key of 私 cannot
    reach inside 私立, because UniDic emits 私立 as a single token whose
    surface is 私立; no run of tokens there concatenates to 私. The earlier
    raw-text substitution had no such protection and rewrote 私立 as
    "Watashi Ri".

    Spans, rather than single tokens, are required because MeCab does not
    know every proper noun. 白良浜 (Shirarahama) is shattered into
    白 + 良 + 浜, so a single-token override could never repair it.

abbreviations.json
    A set of tokens that must never be downcased. It protects existing
    uppercase; it does not create it. An English word that happens to
    collide with an abbreviation, such as "It" against "IT", is therefore
    left alone. See core._cased_latin.

Why not key on lemma
    UniDic's lemma is not the surface's dictionary form and is not writable
    by hand: 私 has lemma "私-代名詞" (carrying a part-of-speech
    disambiguator) and 比良 has lemma "ヒラ" (katakana, not the surface).
    Both also vary between UniDic releases. The optional pos constraint
    covers the disambiguation that lemma would have offered.
"""

import json
import os
from pathlib import Path

_ENV_VAR = "ROMANIZER_DICT_DIR"


def default_dict_dir():
    """Locate the dictionaries directory, overridable for tests and the sidecar."""
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override)
    # python/romanizer/dictionary.py -> repo root -> dictionaries/
    return Path(__file__).resolve().parents[2] / "dictionaries"


class DictionaryError(ValueError):
    """Raised when a dictionary file is malformed or an entry can never match."""


class Override:
    """One custom-term entry: the romaji, and an optional part-of-speech guard."""

    __slots__ = ("romaji", "pos")

    def __init__(self, romaji, pos=None):
        self.romaji = romaji
        self.pos = pos

    def __repr__(self):
        return "Override({!r}, pos={!r})".format(self.romaji, self.pos)


class Dictionary:
    """Immutable view over the two dictionary files."""

    def __init__(self, overrides=None, abbreviations=None, warnings=None):
        self.overrides = dict(overrides or {})
        self.abbreviations = frozenset(abbreviations or ())
        # Problems found at load time under strict=False. Empty under strict=True,
        # which raises instead. The sidecar surfaces these in the job result.
        self.warnings = list(warnings or [])
        self._max_key_len = max((len(k) for k in self.overrides), default=0)

    @classmethod
    def empty(cls):
        """A dictionary that overrides nothing.

        Exists so that a corpus tool can romanize a string with MeCab's own
        readings and diff that against the expected output, to propose
        candidate entries.
        """
        return cls()

    @property
    def custom_terms(self):
        """Flat key -> romaji view, for callers that do not care about pos."""
        return {key: entry.romaji for key, entry in self.overrides.items()}

    def match_tokens(self, tokens, index):
        """Longest override span starting at tokens[index].

        Returns (span_length, romaji) or None. Matching concatenates token
        surfaces, so it is indifferent to how the key itself would tokenize:
        the key 十四日 cannot fire inside 二十四日, whose tokens are
        二十 + 四 + 日 and none of whose runs concatenate to 十四日.
        """
        if not self.overrides:
            return None
        best = None
        accumulated = ""
        for offset in range(index, len(tokens)):
            accumulated += tokens[offset].surface
            if len(accumulated) > self._max_key_len:
                break
            entry = self.overrides.get(accumulated)
            if entry is None:
                continue
            if entry.pos is not None and tokens[index].pos1 != entry.pos:
                continue
            best = (offset - index + 1, entry.romaji)
        return best

    def is_abbreviation(self, token):
        return token.upper() in self.abbreviations


# --- Parsing and validation ------------------------------------------------


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise DictionaryError("dictionary file not found: {}".format(path))
    except json.JSONDecodeError as exc:
        raise DictionaryError("invalid JSON in {}: {}".format(path, exc))


def _parse_overrides(raw, path):
    """Accept both "key": "romaji" and "key": {"romaji": ..., "pos": ...}."""
    if not isinstance(raw, dict):
        raise DictionaryError("{}: expected a JSON object".format(path))
    parsed = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise DictionaryError("{}: keys must be strings, got {!r}".format(path, key))
        if not key:
            raise DictionaryError("{}: empty key".format(path))
        if isinstance(value, str):
            parsed[key] = Override(value)
            continue
        if isinstance(value, dict):
            romaji = value.get("romaji")
            pos = value.get("pos")
            if not isinstance(romaji, str) or not romaji:
                raise DictionaryError(
                    "{}: entry {!r} needs a non-empty string 'romaji'".format(path, key)
                )
            if pos is not None and not isinstance(pos, str):
                raise DictionaryError("{}: entry {!r} has a non-string 'pos'".format(path, key))
            parsed[key] = Override(romaji, pos)
            continue
        raise DictionaryError(
            "{}: keys and values must be strings, got {!r}".format(path, key)
        )
    return parsed


def _validate_abbreviations(raw, path):
    if isinstance(raw, dict):
        raw = raw.get("abbreviations", [])
    if not isinstance(raw, list):
        raise DictionaryError("{}: expected a list or {{'abbreviations': [...]}}".format(path))
    for item in raw:
        if not isinstance(item, str) or not item:
            raise DictionaryError("{}: abbreviations must be non-empty strings".format(path))
    return raw


def _dead_entry_reason(key):
    """Why this key can never match, or None if it can.

    Overrides are applied after script segmentation, so a key must consist
    entirely of characters that reach MeCab. A key must also survive
    tokenization: MeCab discards whitespace, so its tokens would not
    concatenate back to the key.
    """
    from . import core  # deferred: core imports this module

    # Digits are merged into their neighbouring Japanese run before
    # tokenization, so 21日 is a legitimate key even though a digit is not
    # itself a Japanese script.
    reaches_tokenizer = (core._JP, core._DIGIT)
    for char in key:
        if core._classify(char) not in reaches_tokenizer:
            return (
                "contains {!r}, which never reaches the tokenizer "
                "(only kana, kanji and digits do)".format(char)
            )

    tokens = core._tokenize(key)
    if not tokens:
        return "tokenizes to nothing"
    rebuilt = "".join(token.surface for token in tokens)
    if rebuilt != key:
        return "tokenizes to {!r}, which does not reconstruct the key".format(rebuilt)
    return None


def _check_entries(overrides, path, strict):
    warnings = []
    for key in sorted(overrides):
        reason = _dead_entry_reason(key)
        if reason is None:
            continue
        message = "{}: entry {!r} can never match: {}".format(path, key, reason)
        if strict:
            raise DictionaryError(message)
        warnings.append(message)
    return warnings


def load(dict_dir=None, strict=True):
    """Load both dictionaries.

    strict=True (development, CLI, tests) raises DictionaryError on an entry
    that can never match, so a dead entry is caught at edit time.

    strict=False (the runtime sidecar) collects the same problems into
    Dictionary.warnings and loads the remaining entries. The alternative --
    raising in the field -- would let one malformed entry in a user's custom
    dictionary abort a conversion on an office machine mid-document, which is
    a worse failure than silently skipping the entry and reporting it in the
    UI. Warning unconditionally is worse still: dead entries would accumulate
    and nobody would read the warnings.
    """
    base = Path(dict_dir) if dict_dir else default_dict_dir()
    custom_path = base / "custom_terms.json"
    abbrev_path = base / "abbreviations.json"

    overrides = _parse_overrides(_load_json(custom_path), custom_path)
    abbrev = _validate_abbreviations(_load_json(abbrev_path), abbrev_path)

    warnings = _check_entries(overrides, custom_path, strict)
    if warnings:
        dead = {
            key for key in overrides if _dead_entry_reason(key) is not None
        }
        overrides = {k: v for k, v in overrides.items() if k not in dead}

    return Dictionary(overrides, abbrev, warnings)


# --- Linting ---------------------------------------------------------------


def lint(dict_dir=None):
    """Audit every override entry. Returns a list of (key, status, detail).

    status is one of: ok, dead, redundant, shadowed.

    Every status except "dead" is decided empirically, by romanizing the key
    twice: once with no dictionary, to learn what MeCab would have produced,
    and once with the full dictionary, to learn whether this entry is the one
    that actually fires. Substring containment is deliberately not used to
    infer shadowing: 十四日 is a substring of 二十四日 yet fires correctly on
    its own text, because spans match on token boundaries.
    """
    from . import core

    base = Path(dict_dir) if dict_dir else default_dict_dir()
    custom_path = base / "custom_terms.json"
    overrides = _parse_overrides(_load_json(custom_path), custom_path)

    live = {key: entry for key, entry in overrides.items() if _dead_entry_reason(key) is None}
    full = Dictionary(live)
    empty = Dictionary.empty()

    results = []
    for key in sorted(overrides):
        entry = overrides[key]

        reason = _dead_entry_reason(key)
        if reason is not None:
            results.append((key, "dead", reason))
            continue

        baseline = core.romanize(key, empty)
        effective = core.romanize(key, full)

        if effective != entry.romaji:
            results.append(
                (
                    key,
                    "shadowed",
                    "another entry wins: yields {!r}, not {!r}".format(
                        effective, entry.romaji
                    ),
                )
            )
            continue

        if baseline == entry.romaji:
            results.append(
                (key, "redundant", "MeCab already produces {!r}".format(baseline))
            )
            continue

        results.append((key, "ok", "{!r} overrides {!r}".format(entry.romaji, baseline)))
    return results


# --- Singleton -------------------------------------------------------------

_cached = None


def default():
    """Process-wide singleton, loaded on first use."""
    global _cached
    if _cached is None:
        _cached = load()
    return _cached


def reset_cache():
    """Drop the singleton. Used by tests."""
    global _cached
    _cached = None
