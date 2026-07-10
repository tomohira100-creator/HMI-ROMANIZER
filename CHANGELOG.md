# Changelog

All notable changes to ROMANIZER are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Sections are organised by build phase as defined in `PRD.md` rather than by
semantic version, since the project ships as a single internal tool rather than
a versioned library. Each entry records the commit that introduced the change.

## [Unreleased]

## [Phase 1.5] — 2026-07-10

Context-sensitive overrides. Custom terms now match the tokenizer's output
rather than raw text.

### Added

- Token-boundary-aligned span matching in `dictionary.py`. A key matches a run
  of consecutive tokens whose surfaces concatenate exactly to the key. Longest
  span wins, leftmost; consumed tokens are never reconsidered, so partial
  overlap between two overrides cannot arise.
- Optional `pos` constraint on an override, matched against `pos1` of the
  span's first token. Unset on every shipped entry.
- `Dictionary.empty()`, exposing MeCab's unmodified readings. Phase 10 corpus
  tooling will diff against this to propose candidate dictionary entries.
- `load(strict=...)`: raises on dead entries in development, collects them into
  `Dictionary.warnings` at runtime.
- `python -m romanizer lint-dictionary`, reporting each entry as `ok`, `dead`,
  `redundant`, or `shadowed`. Exits non-zero if any entry is dead.
- `python/tests/test_overrides.py`: 51 tests, including negative tests locking
  `私立` `私鉄` `私服` `私道` and a surname-versus-compound case. Suite total is
  165 tests, 95% statement coverage.

### Changed

- `custom_terms.json` is no longer substituted into raw text before
  tokenization. The old mechanism had no notion of token boundaries and would
  rewrite `私立` as `Watashi Ri` given an entry for `私`.
- `ARCHITECTURE.md`: rewrote the `dictionary.py` responsibilities, added an
  override-precedence section, documented `lint-dictionary`, and noted that the
  sidecar loads dictionaries non-strictly.

### Unchanged

- All 114 Phase 1 tests pass without modification. The four Phase 1 test files
  are byte-identical, which is the evidence that the refactor preserves
  behaviour.
- `custom_terms.json` required no migration. All five keys already aligned to
  token boundaries.
- `私` is deliberately **not** seeded. `Watakushi` ships. The mechanism exists
  for proper nouns; `私` is the test fixture that proves it.

### Design notes

- Overrides are keyed on the surface span, never on lemma. UniDic's lemma is
  neither the surface nor hand-writable: `私` has lemma `私-代名詞` and `比良`
  has lemma `ヒラ`.
- Span matching, rather than single-token matching, is required because MeCab
  does not know every proper noun. `白良浜` is shattered into `白` + `良` +
  `浜`, so no single-token override could ever repair it. `比良`, by contrast,
  is a known place name that already reads `Hira` and needs no entry at all.
- Known limit: `私生活` tokenizes as `私` + `生活`, so an override on `私` does
  fire there, yielding `Watashi Seikatsu`. MeCab alone is already wrong here
  (`Watakushi Seikatsu`; the correct reading is `Shiseikatsu`). A longer
  override wins by longest match. Documented and tested rather than hidden.

## [Phase 1] — 2026-07-10

Romanization core library. Modified Hepburn, offline, no file I/O.

### Added

- `python/romanizer/core.py`: script segmentation, MeCab tokenization, counter
  correction, morpheme-to-word grouping, Title Case.
- `python/romanizer/hepburn.py`: katakana to Modified Hepburn tables and
  syllable walker, including sokuon gemination, `tch` before `ch`, and the
  `n'` apostrophe before vowels and `y`.
- `python/romanizer/dictionary.py`: loading and validation of the two
  dictionaries, with longest-match custom-term substitution.
- `python/romanizer/cli.py` and `__main__.py`: `python -m romanizer romanize`.
- `dictionaries/abbreviations.json` seeded with the 13 PRD abbreviations.
- `dictionaries/custom_terms.json` seeded with company forms and two corrected
  date readings.
- `python/tests/`: 114 tests across 13 categories, 95% statement coverage.
- `python/tests/test_unidic_schema.py`: asserts the UniDic feature layout.

### Changed

- `ARCHITECTURE.md`: removed `pykakasi` from the dependency list with a note on
  why; added `hepburn.py` to the directory structure and module
  responsibilities.

### Decisions

- Modified (revised) Hepburn. Long `o`, `u`, `a` take macrons; long `i` and `e`
  are written `ii` and `ei` (`Atarashii`, `Sensei`). Syllabic n is always `n`.
- Vowel length is read from UniDic's `pron` field and vowel identity from its
  `kana` field. Using `kana` alone would romanize the verb 追う as `Ō`; using
  `pron` alone cannot tell `ei` from `ee`.
- Particles は/へ/を are resolved from `pron`, not from part of speech. This is
  what makes こんにちは correct: it is a single interjection token whose `pron`
  is コンニチワ.
- Title Case leaves particles and the copula lowercase (`Watakushi wa Gakusei
  desu`).

### Known MeCab readings not silently corrected

Per the standing rule, readings we believe are wrong are recorded rather than
patched in code.

- `日` after an arabic numeral always reads `カ` in UniDic, including `21日`.
  MeCab provides no usable signal, so the day-counter table in `core.py` is
  ours. Irregular days absorb the numeral (`20日` becomes `Hatsuka`); all
  others keep it (`21日` becomes `21 Nichi`).
- `月` after a numeral reads `ツキ` rather than `ガツ`. Corrected by the same
  counter table.
- `十四日` and `二十四日` read as `Jū Yo Nichi` and `Nijū Yo Nichi`. Corrected
  in `custom_terms.json`.
- `株式会社` reads `カブシキ カイシャ`, losing the rendaku. Corrected in
  `custom_terms.json` to `Kabushiki Gaisha`, alongside `有限会社` and
  `合同会社`. Rendaku is lexical, not rule-governed: `株式市場` is correctly
  `Kabushiki Shijō` with no rendaku.
- `日本` reads `ニッポン`, so it romanizes as `Nippon`, not `Nihon`. Both are
  valid readings of the compound. Left as the dictionary has it. The distinct
  lexeme `日本橋` reads `ニホンバシ` and is unaffected.
- `私` reads `ワタクシ`, so `私は学生です` romanizes as `Watakushi wa Gakusei
  desu`. **Not** corrected via `custom_terms.json`: that dictionary substitutes
  before tokenization and has no context, so an entry for the single kanji `私`
  would rewrite `私立` as `Watashi Ri`, `私鉄` as `Watashi Tetsu`, and `私服` as
  `Watashi Fuku`. Regression tests lock these three compounds.

## [Phase 0] — 2026-07-10

Planning and repository scaffolding. No application code.

### Added

- `README.md`, `PRD.md`, `ARCHITECTURE.md`, `CLAUDE.md`, and `.gitignore`
  establishing the product plan, technical design, and working conventions
  for the project (`8ffaa14`).
