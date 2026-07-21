# Changelog

All notable changes to ROMANIZER are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Sections are organised by build phase as defined in `PRD.md` rather than by
semantic version, since the project ships as a single internal tool rather than
a versioned library. Each entry records the commit that introduced the change.

## [Unreleased]

### Added

- **Phase 3: the XLSX handler.** `python/romanizer/handlers/xlsx_handler.py`
  romanizes a workbook on raw `zipfile` + `lxml`, reusing the `ooxml_parts`
  package class. Shared strings are romanized in place (indices preserved, table
  never deduped or reordered), so no worksheet moves on account of them. Sheet
  names are romanized and every reference rewritten -- cross-sheet formula refs
  and print-area defined names, quoted correctly for names that gain a space
  (`Mitsumori Jōken`). Formula string literals, cached `t="str"` values, and
  header/footer text are romanized. `<rPh>` phonetic ruby and `<phoneticPr>` are
  stripped. Untouched byte-identical: images, drawings, printer settings,
  styles, theme, calcChain -- everything the human reference also kept.
  `openpyxl` was rejected: it drops those parts on a round-trip.
- `python/romanizer/corpus_diff.py` and `python -m romanizer diff-xlsx`: compare
  our output against a `samples/expected/` reference, aligning by shared-string
  index and classifying each divergence (`macron-only`, `spacing-case`,
  `substantive`) so the reference is treated as a reference, not an oracle. The
  semantic call within `substantive` -- our defect versus the human's shortcut
  -- is left to human judgement, with source/ours/theirs shown side by side,
  ranked by frequency.
- `samples/12_spreadsheet.xlsx`: a synthesized fixture covering shared strings,
  a trailing-space Japanese sheet name referenced quoted, quoted and unquoted
  cross-sheet refs, a formula literal, a `t="str"` cached value, an `<rPh>`
  ruby string, a merged cell, a Japanese header, and an untouched image.
- The CLI `convert` dispatch is now handler-agnostic: handlers expose
  `handler_error` and `refusal_error`, so a new format needs no `cli.py` change.

### Fixed

- `<rPh>` phonetic ruby in shared strings was romanized as if it were display
  text, doubling every reading (`式` with ruby `シキ` became `Shiki Shiki`).
  Surfaced by the `diff-xlsx` harness on its first run against the real Maison
  d'Aura pair -- 182 of 291 strings carry ruby -- and fixed by stripping it, as
  the human reference does. Raised identical matches from 7 to 45.

### Deferred

- Compound words spaced with U+3000 for column alignment (`数　量`, `金　　額`)
  tokenize per-kanji and misread (`Kazu Ryō`, not `Sūryō`) -- decision D2, the
  dominant `substantive` divergence in the Maison d'Aura diff. Recorded in
  `ARCHITECTURE.md` with the fix the human's output points to: romanize from the
  `<rPh>` ruby reading, which is offline and author-grounded. A design change,
  not a spot fix; not acted on.

### Refactored

- Renamed `docx_parts.py` to `ooxml_parts.py`; it is format-agnostic OOXML zip
  handling that the XLSX handler reuses.

### Documentation

- `ARCHITECTURE.md`: XLSX handler and `corpus_diff` module responsibilities; the
  U+3000 open item with the ruby-reading fix; and the reference-not-oracle
  principle for the validation corpus.

### Fixed (honorifics, open item #1 closed)

- Honorific and title suffixes now detach from a name (open item #1, closed).
  `比良さん` was `Hirasan`; it is now `Hira San`, space-separated and each word
  capitalized. The rule keys on an explicit honorific list (`さん 様 氏 殿 君
  ちゃん`) **and** the preceding word being a proper noun (`pos2 == 固有名詞`),
  because part of speech alone cannot separate the honorific `さん` from the
  grammatical `人` in `日本人`, both tagged `接尾辞`. The proper-noun gate keeps
  `お客様` → `Okyakusama`, `神様` → `Kamisama`, and `日本人` → `Nipponjin`
  joined, while `比良さん`/`田中様`/`スミスさん` detach. The same gate stops a
  `助数詞可能` noun gluing onto a name, so the titles `比良部長`/`比良課長`
  (tokenized `部`/`課` + `長`) become `Hira Buchō`/`Hira Kachō`; `四半期` and
  `飛行機`, whose bases are common nouns, are unaffected. Single-token titles
  (`社長`, `専務`, `常務`, `係長`) were always separate and are unchanged.

### Documentation

- `ARCHITECTURE.md`: added a "No Network Calls at Runtime" design-constraint
  section. The tool processes Marriott and IHG franchise material, vendor
  agreements, and board papers, which must never leave the machine, so no
  telemetry, analytics, or reading-lookup API is permitted. Recorded so a
  future maintainer does not add a lookup API believing it a harmless accuracy
  improvement. The offline substitute is the `samples/expected/` corpus.

### Fixed

- Conjunctive `て` and `で` now join the stem they inflect. Leaving them
  separate destroyed information: MeCab reads `行っ` as `イッ`, and a word-final
  sokuon has no consonant to double, so `行って` romanized as `I Te`, a string
  from which `言って`, `入って` and `射って` are indistinguishable. Now `Itte`.
  Both halves of the rule are load-bearing and each has a negative test: the
  surface must be `て` or `で` (`が` and `から` are also `接続助詞`), and the
  part of speech must be `接続助詞` (the `で` in `東京で` is a `格助詞`, the `で`
  in `静かで` is a `助動詞`). `た` and `だ` are `助動詞` and were already joined,
  so past forms never carried the defect.
- The katakana middle dot `・` (U+30FB) was classified as a letter because it
  sits inside the katakana Unicode block. It became a word-like atom and took
  spaces: `面接・試験` gave `Mensetsu ・ Shiken`. Now punctuation, preserved
  verbatim. Its neighbour U+30FC, the prolonged sound mark, is a letter and is
  unaffected. The Phase 1 punctuation test passed only by luck, having no
  neighbouring word to space against.
- Words UniDic does not know arrive with a six-field feature vector and no
  reading at all, so they passed through as raw Japanese. When the surface is
  kana, kana is a reading: `アミット` gives `Amitto`, `ビサ` gives `Bisa`, and
  NFKC folds halfwidth `ﾎﾃﾙ` to `Hoteru`. Unknown *kanji* still emit the
  surface, because no reading exists and none can be invented.
- A lone prolonged sound mark romanized to nothing and left a doubled space
  (`くまーる` gave `Kuma  Ru`). It can never begin a word, so it now attaches
  leftward: `Kumā Ru`.

The last three were found by running the DOCX handler over real HMI documents.
None was reachable from the synthesized fixtures.

### Added

- **Phase 2: the DOCX handler.** `python/romanizer/handlers/docx_handler.py`
  romanizes every `w:t` leaf in `document.xml`, headers, footers, footnotes,
  endnotes and comments. That single traversal reaches body text, table cells,
  text boxes, content controls, hyperlink display text and field results with
  no per-construct code. `w:instrText` is never romanized and acts as a segment
  boundary, so ` PAGE ` survives.
- `python/romanizer/docx_parts.py`: zip-level read and write preserving
  untouched parts byte for byte, including images and embedded objects.
- `core.romanize_spans()`: returns `[(src_start, src_end, output)]` instead of a
  string. The spans tile the input and rejoin to exactly `romanize(text)`.
  Without it there is no way to decide which `w:r` run an output word belongs to
  when Word has split a word across runs.
- `python -m romanizer convert in.docx out.docx`. Exit code 2 means the document
  was refused, which is not a crash.
- Decision D3: documents carrying revision markup are **refused**, not
  romanized. Revision history records who changed what and when, and in a
  franchise audit or vendor dispute that record is evidence. All thirteen
  revision constructs are checked across every part, not only `document.xml`,
  and refusal happens before any output is written.
- `samples/11_fragmented.docx`, hand-authoring the run boundaries Word declined
  to give us. Its fragmentation is artificial and it is evidence about the
  handler, never about Word.
- `python/tests/test_docx_handler.py` and `test_docx_spans.py`: 94 tests. The
  integration tests assert on three levels -- untouched parts byte-identical,
  edited parts structurally isomorphic ignoring text, and the text correct.

- `dictionaries/custom_terms.json`: `旭日中綬章` as `Kyokujitsu Chūjushō`. MeCab
  splits it into `旭日` + `中` + `綬章` and reads `旭日` as `アサヒ`, the
  everyday reading, giving `Asahijū Jushō`. No override on the parts can repair
  it, which is precisely what the token-span mechanism exists for.
- `ARCHITECTURE.md`: a known-limitations section. Honorific suffixes are joined
  to the name (`比良さん` gives `Hirasan`), because UniDic tags `さん` and `です`
  alike as `接尾辞` and the distinction is honorific versus grammatical rather
  than part of speech. Fullwidth Latin and digits pass through unconverted
  (`ＨＭＩ`, `８`); whether to apply NFKC is a question the PRD does not settle
  and it remains open. Auxiliary verbs are separate capitalized words
  (`Itte Iru`), a Title Case question rather than a correctness one.
- `ARCHITECTURE.md`: DOCX findings from the real corpus, closing decision D2.
  Across six real HMI documents and 51,858 Japanese tokens, exactly one word is
  split across runs and zero are split across runs of differing formatting, so
  "first-character-wins" discards nothing in practice. Also records that
  `w:pict` is not evidence of an image, and that five of six files were not
  produced by Microsoft Word.
- `python/tests/fixtures/build_fixtures.py`: deterministic synthesis of
  `samples/05_lists.docx` and `samples/10_composite.docx` using `zipfile` and
  `lxml` only, with no `python-docx` dependency. Rebuilds are byte-identical.
- `samples/README.md`: what each of the ten samples must contain, and an
  explicit statement that a green suite over the synthesized fixtures is a
  necessary but not sufficient condition for correctness on real Word
  documents.
- `python/tests/test_samples.py`: 17 tests over the fixtures, plus one xfail.

### Changed

- `.gitignore`: whitelists only `samples/README.md` and the two synthesized
  fixtures. Real HMI documents cannot be committed by accident; the exclusion
  is enforced by the ignore file rather than by discipline.

### Deferred

- Romanizing `numbering.xml` `w:lvlText` (decision D7). `05_lists.docx` carries
  the Japanese numbering literals `第%1章` and `%2項`, and
  `test_numbering_literals_are_romanized` is marked xfail with a reference to
  D7. It xpasses on its own the day the work lands, rather than needing to be
  remembered.

### Documentation

- `ARCHITECTURE.md`: recorded the compound-splitting limitation as a stated
  hypothesis for Phase 10 corpus work. Verified against HMI place names:
  `浜松`, `神戸`, `御前崎`, `相良`, `熱海`, `那覇` and `読谷` are single known
  lexemes and read correctly, but `舘山寺` splits into `舘山` + `寺` and yields
  `Tateyamaji` rather than `Kanzanji`.

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
