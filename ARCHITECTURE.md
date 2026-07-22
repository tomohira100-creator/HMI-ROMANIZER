# ROMANIZER — Technical Architecture

## Stack Overview

- **App shell:** Tauri 2.x (Rust)
- **Frontend:** React 18 + TypeScript + TailwindCSS
- **Backend:** Bundled Python 3.11 sidecar process
- **Build:** Vite for frontend, Cargo for Rust, PyInstaller for Python sidecar
- **Installer:** Tauri bundler → Windows `.msi` via GitHub Actions

## Design Constraint: No Network Calls at Runtime

ROMANIZER makes no network calls while running. No telemetry, no analytics, no
crash reporting, no reading-lookup API, no update check — nothing leaves the
machine. This is not a performance choice and it is not negotiable.

The tool processes Marriott and IHG franchise material, vendor agreements, and
board papers. Those documents must never leave the machine on which they are
converted. A single outbound request carrying document text — even to look up a
kanji reading, even to a service that promises not to retain it — is a
confidentiality breach in a franchise or vendor context. A future maintainer
who adds a lookup API to "improve accuracy" would be trading the one property
that makes this tool usable on these documents for a marginal gain. Do not.

The offline substitute for an internet reading-lookup is the `samples/expected/`
validation corpus (see below). When MeCab gets a reading wrong, the answer is
not to ask the open web; it is to diff against HMI's own hand-romanized
documents and add the correction to `custom_terms.json`. That grounds accuracy
in HMI's real vocabulary rather than in whatever the web returns, and it does it
without a single byte leaving the machine.

## Python Dependencies

- `mecab-python3` + `unidic` — kanji to reading via morphological analysis, and the sole source of romanization readings
- `paddleocr` — Japanese OCR
- `PyMuPDF` (fitz) — PDF text and layout manipulation
- `openpyxl` — XLSX manipulation (sanity layer above lxml)
- `python-pptx` — PPTX (sanity layer above lxml)
- `lxml` — direct XML manipulation for full fidelity
- `Pillow` — image processing
- `ReportLab` — PDF and image text rendering

`pykakasi` was removed in Phase 1. It performs no part-of-speech tagging, so it
cannot tell a particle は from a は inside a word, and its `hepburn` output is
wapuro-style: no macrons (`toukyou`, not `Tōkyō`) and it rewrites the Japanese
punctuation the PRD requires be preserved. Readings come from UniDic instead.

The `unidic` version is pinned exactly in `python/pyproject.toml`. UniDic
feature fields are read by numeric index and those indices move between
releases, so `python/tests/test_unidic_schema.py` asserts the layout.

## Directory Structure

```
HMI-romanizer/
├── README.md
├── PRD.md
├── ARCHITECTURE.md
├── CLAUDE.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── build-windows.yml          (added Phase 9)
├── src-tauri/                          (Rust shell, added Phase 7)
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── src/
│       └── main.rs
├── src/                                (React frontend, added Phase 7)
│   ├── App.tsx
│   ├── components/
│   └── styles/
├── python/                             (Python backend, Phase 1+)
│   ├── romanizer/
│   │   ├── __init__.py
│   │   ├── core.py                     (Phase 1)
│   │   ├── hepburn.py                  (Phase 1)
│   │   ├── dictionary.py               (Phase 1)
│   │   ├── handlers/
│   │   │   ├── docx_handler.py         (Phase 2)
│   │   │   ├── xlsx_handler.py         (Phase 3)
│   │   │   ├── pptx_handler.py         (Phase 4)
│   │   │   ├── pdf_handler.py          (Phase 5)
│   │   │   └── ocr_handler.py          (Phase 6)
│   │   ├── ipc.py                      (Phase 8)
│   │   └── cli.py                      (Phase 1, for dev testing)
│   ├── pyproject.toml
│   └── tests/
│       └── ...
├── samples/                            (test documents, gitignored if large)
│   └── README.md
├── dictionaries/
│   ├── abbreviations.json              (Phase 1)
│   └── custom_terms.json               (Phase 1, populated later)
└── package.json                        (Phase 7)
```

## Module Responsibilities

### `python/romanizer/core.py`
The romanization engine. Pure function: Japanese string in, romaji string out. Handles Hepburn rules, Title Case, macrons, abbreviation lookups, numbers, punctuation pass-through. No file I/O. No format-specific logic.

### `python/romanizer/hepburn.py`
The katakana to Modified Hepburn conversion tables and the syllable walker that
consumes them. Kept separate from `core.py` because the tables are large, are
pure data, and are expected to be edited during Phase 10 real-world testing.
Takes UniDic's `pron` reading for vowel length and its `kana` reading for vowel
identity; neither alone is sufficient.

### `python/romanizer/dictionary.py`
Loads `abbreviations.json` and `custom_terms.json` at startup. Provides lookup
interface to `core.py`.

Custom terms are matched against the tokenizer's output, not against raw text.
A key matches a run of one or more consecutive tokens whose surfaces
concatenate exactly to the key, beginning and ending on token boundaries.
Token-boundary alignment is the safety property: a key of `私` cannot reach
inside `私立`, because UniDic emits that as a single token. Spans rather than
single tokens are required because MeCab does not know every proper noun, and
shatters `白良浜` into `白` + `良` + `浜`.

Entries may carry an optional `pos` constraint, matched against `pos1` of the
span's first token. Lemma is deliberately not used as a key: UniDic's lemma is
neither the surface nor hand-writable (`私` has lemma `私-代名詞`, `比良` has
lemma `ヒラ`), and it varies between UniDic releases.

`load(strict=True)`, the default for the CLI and tests, raises on an entry that
can never match, so dead entries are caught at edit time. The runtime sidecar
calls `load(strict=False)`, which collects the same problems into
`Dictionary.warnings` and loads the remaining entries, so one malformed entry
in a user's dictionary degrades a single term rather than aborting a conversion
mid-document on an office machine.

`Dictionary.empty()` romanizes with MeCab's own readings and no overrides. It
exists so that Phase 10 corpus tooling can diff default output against expected
output and propose candidate dictionary entries.

Known limitation, to be tested against a real corpus in Phase 10: MeCab
sometimes splits a compound that should not be split, and reads the parts
wrongly. `私生活` becomes `私` + `生活`, which no override on either part can
repair; only an override on the whole span can. This bites on property names:
`舘山寺` splits into `舘山` + `寺` and yields `Tateyamaji` rather than
`Kanzanji`. `浜松`, `神戸`, `御前崎`, `相良`, `熱海`, `那覇` and `読谷` are
single known lexemes and read correctly; vendor entity names are unverified.

### Override precedence

Evaluated on the token stream, highest first:

1. `custom_terms.json` override. Longest span, leftmost. Consumed tokens are
   literal and immune to everything below.
2. The counter-reading table for `日`, `月`, `年`. Sees only tokens no override
   claimed, so `十四日` comes from the dictionary, never from the table.
3. MeCab's own reading, from the `pron` and `kana` fields.
4. Title Case and `abbreviations.json`.

`abbreviations.json` does not compete with `custom_terms.json`. It governs the
casing of Latin runs, which never reach MeCab. An override value is emitted
verbatim and consults neither Title Case nor the abbreviation list.

Because overrides are applied after script segmentation, an override key may
contain only characters that reach the tokenizer: kana, kanji, and digits. A
key containing Latin, punctuation, or whitespace is structurally dead and is
reported as such.

### `python/romanizer/docx_parts.py`
Zip-level read and write for OOXML packages. Reads a package into its original
`ZipInfo` entries and writes it back, substituting only the parts a caller
replaced. Untouched parts are copied byte for byte with their original
compression and timestamps, which is what makes the "untouched parts are
byte-identical" assertion in the test suite meaningful. Re-serializing an
unchanged XML part through lxml would rewrite attribute order and namespace
declarations even when nothing changed.

Deliberately not built on `python-docx`, which was evaluated and rejected: its
object model misses text (runs inside `w:ins` and `w:fldSimple` report as
absent), destroys structure (assigning to `run.text` drops `w:br` and `w:tab`
from the run), and does not parse `footnotes.xml` at all. Its packaging layer
round-trips losslessly; its convenience API does not.

### `python/romanizer/handlers/xlsx_handler.py`
Romanizes a workbook on raw `zipfile` + `lxml`, reusing `ooxml_parts.Package`.
Almost all display text is in `xl/sharedStrings.xml`; cells reference it by
index, so strings are romanized **in place** -- same `<si>` count and order --
and no worksheet moves on account of them. The table is never deduped or
reordered: two Japanese strings can romanize to the same romaji, and merging
them would reindex every referencing cell.

Targeted edits beyond shared strings: sheet names in `workbook.xml` and every
reference to them (cross-sheet formula refs and print-area defined names, which
carry sheet names); formula string literals (`B52&"合計"`); cached `t="str"`
values; and header/footer text. Sheet references use single quotes and string
literals use double quotes, so the two never collide; a romanized name may gain
a space (`Mitsumori Jōken`), so rewritten refs are always emitted quoted.

`<rPh>` phonetic ruby and `<phoneticPr>` are stripped, not romanized: the ruby
is a katakana reading of the kanji, meaningless once the text is Latin, and
Excel would render it over the romaji. `openpyxl` is not used -- it drops
drawings, printer settings and headers on a round-trip and rewrites every
shared string inline; the human reference keeps all of those.

### `python/romanizer/run_reassembly.py`
The shared run-reassembly used by the DOCX and PPTX handlers. Word and
PowerPoint both split a word across runs (`w:r`/`w:t`, `a:r`/`a:t`) for reasons
unrelated to formatting; the segmentation and first-run-wins attribution are
identical and only the element names differ, so a `RunModel` (paragraph tag,
text tag, boundary tags, `xml:space` attr) parameterizes the one implementation.
A boundary element (`w:instrText`, `a:br`, `a:fld`) both splits a segment and is
never descended into, which shields a PPTX field's cached `a:t` value from
romanization. The a:t/w:t sibling guard -- never prune an emptied run, or a
bookmark, line break, or field goes with it -- lives here, at the single shared
point of temptation.

### `python/romanizer/handlers/pptx_handler.py`
Romanizes `<a:t>` display text in `ppt/slides/slideN.xml` (titles, bodies,
tables, grouped shapes -- one recursive walk reaches all) and
`ppt/notesSlides/notesSlideN.xml` (the speaker's script), reusing
`run_reassembly` and `ooxml_parts.Package`. Text is inline per slide -- no
shared-string indirection -- so every non-slide part stays byte-identical.

Never touched: `@typeface` (font names are Japanese but romanizing them breaks
rendering), `@descr` (image alt-text, decision D1), `a:fld` cached values
(regenerated), and -- structurally -- slide masters and layouts. Master/layout
`a:t` is prompt boilerplate (`クリックして...`); it is excluded by part, not by
matching the visible string, so the exclusion survives any re-worded template
(decision D2).

Charts (`c:` parts), SmartArt (`dgm:` parts), embedded OLE objects, and comments
are deferred (decision D4), but **loudly**: `convert` returns a `Conversion`
carrying every unconverted part that still holds Japanese, so a deck with
Japanese chart labels cannot pass for fully converted. The conversion is
reported, not failed. `python-pptx` was rejected the same way as `openpyxl` and
`python-docx`: a round-trip re-serializes 27 of 33 parts.

### `python/romanizer/corpus_diff.py`
Compares our romanization against a human reference in `samples/expected/`. For
`.xlsx` it aligns by shared-string index (`diff-xlsx`); for `.pptx` it aligns by
slide and reassembly-segment order (`compare_pptx`). Each divergence is
classified -- `macron-only`, `spacing-case`, `substantive` -- so the reference
is treated as a reference, not an oracle (see the Validation Corpus section).

### `python/romanizer/handlers/*.py`
Format-specific file handlers. Each one:
- Takes an input file path and output file path
- Reads the file
- Identifies Japanese text regions
- Calls `core.romanize()` for each
- Writes the output preserving all original formatting
- Reports progress via callback

### `python/romanizer/ipc.py`
JSON-over-stdin/stdout protocol for Tauri ↔ Python communication. Receives job requests from Rust shell. Returns progress and results.

### `python/romanizer/cli.py`
Command-line interface for development testing. Lets us run `python -m romanizer convert input.docx output.docx` without the UI.

Commands:
- `romanize` — romanize a string, from an argument or `--stdin`
- `lint-dictionary` — audit `custom_terms.json`, reporting each entry as `ok`,
  `dead` (can never match), `redundant` (MeCab already produces this), or
  `shadowed` (a different entry wins on this key). Exits non-zero if any entry
  is dead.

### `src-tauri/src/main.rs`
Rust shell. Spawns Python sidecar. Manages window lifecycle. Handles file dialog, drag-drop file paths.

### `src/App.tsx` and components
React UI. Drag-drop zone, file cards, progress bars, settings panel, output folder picker.

## Data Flow

1. User drops files → React captures paths via Tauri drag-drop event
2. User clicks "Convert All" → React sends job message to Rust
3. Rust forwards JSON message to Python sidecar via stdin
4. Python receives job, dispatches to appropriate handler; the sidecar loads
   dictionaries with `strict=False` and returns any dead-entry warnings in the
   job result rather than failing the conversion
5. Handler processes file, emits progress messages on stdout
6. Rust reads stdout, forwards to React
7. React updates UI in real-time
8. Handler writes output file, emits completion message
9. React shows "Open File" button

## Image-vs-Text Decision (v1)

- Embedded images in DOCX/XLSX/PPTX/PDF: never touched
- PDF pages with text layer: text-layer redraw
- PDF pages without text layer: OCR entire page
- Standalone PNG/JPG: OCR entire image
- No smart classification of catalogue-style mixed pages in v1

## Romaji Overflow Handling

When romaji exceeds the bounds of the original Japanese:
- Wrap to multiple lines at word boundaries (spaces)
- Maintain original font size
- Cells/rows grow vertically
- Page count may increase

## Parallelism

- Up to 4 files processed concurrently
- Each handler is single-threaded internally
- OCR is the bottleneck — CPU-bound, no GPU assumed

## Bundled Assets

The installer includes:
- Python 3.11 embeddable runtime
- All Python libraries
- MeCab UniDic dictionary (~500 MB)
- PaddleOCR Japanese detection model (~50 MB)
- PaddleOCR Japanese recognition model (~50 MB)
- Noto Sans + Noto Serif fonts (~30 MB)
- Default abbreviations dictionary

Total installer size: ~3 GB.

## Known Limitations and Open Questions

**Honorific and title suffixes are separated from the name. (Closed.)**
`比良さん` romanizes as `Hira San` — space-separated, each word capitalized.
Part of speech alone cannot decide this: UniDic tags `さん` and the grammatical
`人` in `日本人` alike as `接尾辞`. The rule keys on two things together: an
explicit honorific list (`さん 様 氏 殿 君 ちゃん`), and the preceding word being
a proper noun (`pos2 == 固有名詞`). The proper-noun gate is what keeps `お客様`
(which HMI documents use constantly) as `Okyakusama` and `神様` as `Kamisama`,
while `比良さん` detaches — those attach a suffix to a common noun. Job titles
`部長`/`課長` tokenize as `部`/`課` (`助数詞可能`) + `長`; the same proper-noun
gate stops `部`/`課` gluing onto the surname, giving `比良部長` → `Hira Buchō`.
Single-token titles (`社長`, `専務`, `常務`, `係長`) were always separate.
Residual: MeCab mis-tags the standalone `王` as a surname, so `王様` → `Ō Sama`;
rare and accepted.

**Fullwidth Latin and digits pass through unconverted.** `ＨＭＩホテル` becomes
`ＨＭＩ Hoteru`, and `令和８年` becomes `Reiwa ８ Nen`. Latin runs are emitted
byte for byte by design, and fullwidth digits are digits. Whether to apply NFKC
normalization so `ＨＭＩ` becomes `HMI` and `８` becomes `8` is a question the
PRD does not settle, and it is not only cosmetic: NFKC would also fold other
characters in ways that need review. Open, undecided, deliberately untouched.

**Auxiliary verbs are separate capitalized words.** `行っている` becomes
`Itte Iru`. Standard Hepburn practice writes the auxiliary lowercase. This is a
Title Case question rather than a correctness one.

**Compound words spaced with U+3000. (Closed -- Phase 4.5.)** HMI documents
space kanji inside one word with the ideographic space for column alignment:
`数　量`, `名　称`, `金　　額`. `core.romanize` now collapses such a space before
tokenization, so `数量` reads `Sūryō`, not `Kazu Ryō`. The fix lives in `core`,
not a handler, so DOCX, XLSX and PPTX inherit it identically.

The gate is **dictionary-verified, not surface-feature**: a U+3000 run collapses
only when the joined neighbours are a single word UniDic recognizes (an
in-dictionary token), or a custom-term key, or the ordinal construction `第` +
digit. Inferring from surface features was measured to fail -- a "both sides
kanji" rule merges `お客様　各位` into a run and `代表取締役　社長` into one title,
because those joins are multi-token. The dictionary gate preserves them: only a
recognized single word licenses the collapse. A foreign katakana blob
(`セカンダリールームダウンライト`) is one *unknown* token and does not qualify, so
`セカンダリールーム　ダウンライト` stays two words. A proper noun UniDic does not
know (`神戸マリオット`) routes to `custom_terms`, which is why a custom-term key
also licenses the collapse -- so the override fires on the spaced form too.

`romanize_spans` remaps offsets so the collapsed space is absorbed into the word
that swallowed it and the spans still tile the original, keeping the DOCX/PPTX
run-attribution contract intact.

Regression, measured before merge: across the three corpora, 8 unique U+3000
strings changed, every one an improvement, zero regressions; against the human
reference the workbook's `substantive` divergences fell from 177 to 165 with no
new ones. The rejected `<rPh>`-as-reading idea (9% vs the collapse's result)
stays rejected; the collapse does not need it.

## DOCX Findings from the Real Corpus

Measured across six real HMI documents, 51,858 Japanese tokens, before the
handler was written.

**Split-run formatting (decision D2, closed).** Exactly one Japanese word was
split across `w:r` runs, and both runs carried byte-identical formatting. Zero
words were split across runs of differing formatting. The rule "the run
containing the word's first character wins" was therefore validated against
real content: in this corpus it never discards any formatting, because there is
never any to discard. The single split is `際して` broken as `際` + `しての` in
the title of `比良社長 春の叙勲 受章のご報告`. Mid-word formatting changes are
an English typographic habit, not a Japanese one. Untested: splits inside table
cells, and splits adjacent to `w:br` — no sample contains a table.

**`w:pict` is not evidence of an image.** Every file carries `w:pict` elements
whose only child is `v:rect`, VML rectangles used as horizontal rules. There is
no media part behind them. Do not infer image content from `pict`.

**Producer.** Five of the six files have no `docProps/app.xml` and were not
produced by Microsoft Word, though they carry `w:rsid` attributes. Only
`比良社長 春の叙勲` names `Microsoft Office Word`. That is almost certainly why
fragmentation is nearly absent, and it means the corpus is representative of
what HMI actually writes rather than of what Word does. This is the population
the tool serves.

**Constructs absent from the entire corpus**, and therefore untested by it:
tables, `gridSpan`, `vMerge`, content controls, fields, hyperlinks, comments,
headers, footers, embedded OLE objects.

## PPTX Findings from the Real Corpus

Measured on two decks (both romanized outputs, not Japanese originals -- see the
note below).

**Text location and the `@typeface` trap.** Display text is in `<a:t>` only,
inline per slide. A naive "romanize all Japanese in the XML" would be
catastrophic: on the busiest slide, of 383 Japanese characters, 6 were display
text and 344 were **font names in `@typeface` attributes** (游ゴシック, メイリオ).
Romanizing a font name breaks rendering. The a:t walk never reads attributes, so
font names, `@descr` alt-text, and metadata are untouched by construction.

**Fragmentation is common, mid-word splitting rare.** 31.8% of paragraphs are
multi-run (versus DOCX's near-zero), so the reassembly path is the main event --
but genuine mid-word splits were 2 in 312 paragraphs, one of them a
partial-romanization artifact. Multi-run is mostly formatting spans at word
boundaries. Caveat: measured on romanized text; the original's fragmentation
could differ.

**Most residual Japanese is not slide text.** In the partially-romanized deck,
charts (`c:v` cached values) and embedded Excel objects held far more Japanese
than slide `a:t`. These are deferred and reported by the loud notice, not
silently left.

**U+3000 in titles is unmeasured, pending an original.** PPTX makes decision D2
(the U+3000 compound-spacing misread) land in slide titles, the most visible
text on a slide -- `神戸　マリオット` with a mid-title gap would go straight into a
board deck. The count of intra-word `JP　JP` cases in titles cannot be measured
on a romanized output (romanization already split them); the measurement is
written and runs in one command against a Japanese original. This is why D3 in
the session plan pulled U+3000 forward to its own engine phase (4.5) before PPTX
is considered shippable.

**No Japanese-original decks exist in the corpus.** The two `.pptx` files are
both in `samples/expected/` and are romanized outputs; their originals are
absent. Structural design was validated against them (round-trip, part
preservation, the loud notice), but the vocabulary-level accuracy measurement
and the `compare_pptx` diff need original+reference pairs that do not yet exist.

## Validation Corpus

`samples/expected/` holds documents a human romanized by hand, paired with their
Japanese originals in `samples/`, so Phase 10 can measure accuracy by diffing
ROMANIZER's output against a person's answer rather than by eyeballing whether
the output looks plausible. The pairs are `見積書`, `工事工程表`,
`ホテルクラウンパレス小倉改修工事見積書`, `R)【御見積書】260610`,
`【御見積書20260316】PC神戸本工事`, and the Maison d'Aura workbook; they are
expected outputs, never inputs, and neither they nor the originals are ever
committed.

**The corpus is a reference, not an oracle.** When our output diverges from the
human's, sometimes we are wrong -- a misread vendor or construction term -- and
sometimes the human took a shortcut: a dropped macron, a katakana English
loanword translated to English (`メインルーム` written `Main Room`, which is
translation, a PRD non-goal, not romanization), an inconsistent hyphenation.
These are not the same finding and must not be reported alike, or a macron typo
drowns out a real misreading. `corpus_diff` classifies each divergence
mechanically (`macron-only` / `spacing-case` / `substantive`); the semantic
call within `substantive` -- our defect versus the human's choice -- needs
domain judgement, which is why the report shows source, ours, and theirs side by
side, ranked by frequency.

## Build Pipeline

- **Mac dev:** `npm run tauri dev` runs the full app locally for testing
- **Windows installer:** GitHub Actions workflow on push to `main`
  - Sets up Windows runner
  - Builds Rust shell
  - Builds Python sidecar via PyInstaller
  - Builds React frontend via Vite
  - Tauri bundles everything into `.msi`
  - Uploads `.msi` to GitHub Releases
