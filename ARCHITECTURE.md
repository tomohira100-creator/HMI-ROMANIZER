# ROMANIZER — Technical Architecture

## Stack Overview

- **App shell:** Tauri 2.x (Rust)
- **Frontend:** React 18 + TypeScript + TailwindCSS
- **Backend:** Bundled Python 3.11 sidecar process
- **Build:** Vite for frontend, Cargo for Rust, PyInstaller for Python sidecar
- **Installer:** Tauri bundler → Windows `.msi` via GitHub Actions

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

**Honorific suffixes are joined to the name.** `比良さん` romanizes as `Hirasan`
rather than `Hira-san` or `Hira San`. The word-grouping rule joins every
`接尾辞` to the preceding word, which is right for `です` and for `日本人`
(`Nipponjin`) and wrong for `さん`, `様`, `氏` and `殿`. The distinction UniDic
does not draw is honorific versus grammatical: both are tagged `接尾辞`, so part
of speech alone cannot separate them. A fix needs an explicit list of honorifics
and a decision on whether to hyphenate or space them. Unresolved.

**Fullwidth Latin and digits pass through unconverted.** `ＨＭＩホテル` becomes
`ＨＭＩ Hoteru`, and `令和８年` becomes `Reiwa ８ Nen`. Latin runs are emitted
byte for byte by design, and fullwidth digits are digits. Whether to apply NFKC
normalization so `ＨＭＩ` becomes `HMI` and `８` becomes `8` is a question the
PRD does not settle, and it is not only cosmetic: NFKC would also fold other
characters in ways that need review. Open, undecided, deliberately untouched.

**Auxiliary verbs are separate capitalized words.** `行っている` becomes
`Itte Iru`. Standard Hepburn practice writes the auxiliary lowercase. This is a
Title Case question rather than a correctness one.

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

## Validation Corpus

`samples/expected/` holds documents a human romanized by hand, paired with their
Japanese originals in `samples/`, so Phase 10 can measure accuracy by diffing
ROMANIZER's output against a person's answer rather than by eyeballing whether
the output looks plausible. The pairs are `見積書`, `工事工程表`,
`ホテルクラウンパレス小倉改修工事見積書`, `R)【御見積書】260610`,
`【御見積書20260316】PC神戸本工事`, and the Maison d'Aura workbook; they are
expected outputs, never inputs, and neither they nor the originals are ever
committed.

## Build Pipeline

- **Mac dev:** `npm run tauri dev` runs the full app locally for testing
- **Windows installer:** GitHub Actions workflow on push to `main`
  - Sets up Windows runner
  - Builds Rust shell
  - Builds Python sidecar via PyInstaller
  - Builds React frontend via Vite
  - Tauri bundles everything into `.msi`
  - Uploads `.msi` to GitHub Releases
