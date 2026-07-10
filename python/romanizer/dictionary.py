"""Loading and lookup for the abbreviation and custom-term dictionaries.

Two mechanisms, deliberately kept separate:

custom_terms.json
    Maps a Japanese surface form to an exact romaji output string. Applied
    before tokenization as a longest-match substitution over the raw text.
    The replacement is emitted verbatim, immune to MeCab and to Title Case.
    This is the escape hatch for lexical facts no rule can derive, such as
    rendaku (株式会社 is Gaisha but 株式市場 is Shijō) and for readings
    where MeCab is wrong.

    Because the substitution runs before tokenization it has no context.
    Never add a single kanji that occurs inside compounds: an entry for 私
    would rewrite 私立 (Shiritsu) as "Watashi Ri". Prefer the longest surface
    form that is unambiguous, and add a regression test for the compounds you
    are about to endanger.

abbreviations.json
    A set of tokens that must never be downcased. It protects existing
    uppercase; it does not create it. An English word that happens to
    collide with an abbreviation, such as "It" against "IT", is therefore
    left alone. See core._cased_latin.
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
    """Raised when a dictionary file is malformed."""


class Dictionary:
    """Immutable view over the two dictionary files."""

    def __init__(self, custom_terms=None, abbreviations=None):
        self.custom_terms = dict(custom_terms or {})
        self.abbreviations = frozenset(abbreviations or ())
        # Longest first so that 二十四日 wins over 四日, and ties broken
        # leftmost by the scan in core, not here.
        self._keys_by_length = sorted(self.custom_terms, key=len, reverse=True)

    @property
    def custom_keys(self):
        return self._keys_by_length

    def match_at(self, text, index):
        """Return (surface, romaji) for the longest custom term at index, or None."""
        for key in self._keys_by_length:
            if key and text.startswith(key, index):
                return key, self.custom_terms[key]
        return None

    def is_abbreviation(self, token):
        return token.upper() in self.abbreviations


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise DictionaryError("dictionary file not found: {}".format(path))
    except json.JSONDecodeError as exc:
        raise DictionaryError("invalid JSON in {}: {}".format(path, exc))


def _validate_custom(raw, path):
    if not isinstance(raw, dict):
        raise DictionaryError("{}: expected a JSON object".format(path))
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise DictionaryError(
                "{}: keys and values must be strings, got {!r}".format(path, key)
            )
        if not key:
            raise DictionaryError("{}: empty key".format(path))
    return raw


def _validate_abbreviations(raw, path):
    if isinstance(raw, dict):
        raw = raw.get("abbreviations", [])
    if not isinstance(raw, list):
        raise DictionaryError("{}: expected a list or {{'abbreviations': [...]}}".format(path))
    for item in raw:
        if not isinstance(item, str) or not item:
            raise DictionaryError("{}: abbreviations must be non-empty strings".format(path))
    return raw


def load(dict_dir=None):
    """Load both dictionaries from disk."""
    base = Path(dict_dir) if dict_dir else default_dict_dir()
    custom_path = base / "custom_terms.json"
    abbrev_path = base / "abbreviations.json"
    custom = _validate_custom(_load_json(custom_path), custom_path)
    abbrev = _validate_abbreviations(_load_json(abbrev_path), abbrev_path)
    return Dictionary(custom, abbrev)


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
