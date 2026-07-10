# ROMANIZER — Technical Architecture

## Stack Overview

- **App shell:** Tauri 2.x (Rust)
- **Frontend:** React 18 + TypeScript + TailwindCSS
- **Backend:** Bundled Python 3.11 sidecar process
- **Build:** Vite for frontend, Cargo for Rust, PyInstaller for Python sidecar
- **Installer:** Tauri bundler → Windows `.msi` via GitHub Actions

## Python Dependencies

- `pykakasi` — kana to romaji conversion
- `mecab-python3` + `unidic` — kanji to reading via morphological analysis
- `paddleocr` — Japanese OCR
- `PyMuPDF` (fitz) — PDF text and layout manipulation
- `openpyxl` — XLSX manipulation (sanity layer above lxml)
- `python-pptx` — PPTX (sanity layer above lxml)
- `lxml` — direct XML manipulation for full fidelity
- `Pillow` — image processing
- `ReportLab` — PDF and image text rendering

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

### `python/romanizer/dictionary.py`
Loads `abbreviations.json` and `custom_terms.json` at startup. Provides lookup interface to `core.py`.

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

### `src-tauri/src/main.rs`
Rust shell. Spawns Python sidecar. Manages window lifecycle. Handles file dialog, drag-drop file paths.

### `src/App.tsx` and components
React UI. Drag-drop zone, file cards, progress bars, settings panel, output folder picker.

## Data Flow

1. User drops files → React captures paths via Tauri drag-drop event
2. User clicks "Convert All" → React sends job message to Rust
3. Rust forwards JSON message to Python sidecar via stdin
4. Python receives job, dispatches to appropriate handler
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
