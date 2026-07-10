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

## Build Pipeline

- **Mac dev:** `npm run tauri dev` runs the full app locally for testing
- **Windows installer:** GitHub Actions workflow on push to `main`
  - Sets up Windows runner
  - Builds Rust shell
  - Builds Python sidecar via PyInstaller
  - Builds React frontend via Vite
  - Tauri bundles everything into `.msi`
  - Uploads `.msi` to GitHub Releases
