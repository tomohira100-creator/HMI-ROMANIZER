# ROMANIZER — Product Requirements Document

## Purpose

Convert Japanese text in office documents into Hepburn romaji while preserving original formatting. Internal tool for HMI Hotel Group Japan office staff.

## Target Users

HMI Hotel Group Japan office staff. No technical expertise required. Each user installs the app on their own Windows machine.

## Core User Flow

1. User double-clicks installed ROMANIZER shortcut
2. Single window opens with drag-and-drop zone
3. User drags one or more Japanese documents into the zone
4. Files appear as cards showing filename, type, size, and status
5. User clicks "Convert All"
6. Progress bars show per-file and overall progress
7. As files complete, "Open File" and "Open Folder" buttons appear
8. Output files saved with `_ROMAJI` suffix to `Desktop/ROMANIZER Output/`
9. User closes app — all temp files cleared, no traces remain

## Supported File Formats (v1)

- DOCX (Microsoft Word)
- XLSX (Microsoft Excel)
- PPTX (Microsoft PowerPoint)
- PDF (born-digital, with embedded text layer)
- PDF (scanned, OCR required)
- PNG images
- JPG images

## Romanization Rules

- **System:** Hepburn romanization
- **Default case:** Title Case
  - Example: 株式会社ホテル → "Kabushiki Gaisha Hoteru"
- **ALL CAPS exception:** Known abbreviations only
  - Known list: HMI, NTT, ANA, JR, JPY, USD, KPI, REIT, FFE, OSE, HR, IT, AI
  - Extensible via custom dictionary
- **Macrons:** Preserved for long vowels (ū, ō, ā, ē, ī)
- **Numbers:** Stay as numerals (1月21日 → "1 Gatsu 21 Nichi")
- **Punctuation:** Preserved (・、。「」【】×)
- **English:** Untouched, passes through unchanged
- **Custom dictionary:** Loaded at runtime, overrides default romanization for HMI-specific terms (hotel names, brand names, person names). Initial dictionary is empty placeholder — populated later.

## Layout Handling

When romaji is longer than original Japanese:
- **Wrap to multiple lines, keep font size**
- Cells and rows may grow taller
- Documents may grow in page count
- Readability is prioritized over page-count fidelity

## Image Handling

- **Embedded images inside DOCX/XLSX/PPTX/PDF:** Untouched. Stay pixel-perfect, even if they contain Japanese text inside them.
- **PDF pages that are entirely an image (scanned PDFs):** Full OCR pipeline.
- **PNG/JPG uploaded directly:** Full OCR pipeline.
- **Catalogue-style mixed pages** (real text + embedded images on same page): Treated as scanned for now. Smart classification deferred to v2.

## Performance Targets

- Up to 500 MB per file
- Up to 400 pages per file
- Up to 10 files per batch
- 4 files processed in parallel
- Progress updates every 100ms
- Cancel button aborts within 1 second

## Privacy and Safety

- 100% local processing
- Zero network calls after install
- No analytics, no telemetry
- Temp files in `%TEMP%\ROMANIZER\` cleared on app close
- No history, no memory, no shared state between users

## Accepted Limitations (Documented)

- ~85–95% OCR accuracy on scanned documents depending on scan quality
- Catalogue pages with mixed text+image content lose some fidelity in v1
- Romaji is 3–5x longer than Japanese — documents will grow
- Installer is ~3 GB (price of full offline operation)
- Windows SmartScreen warning on first install (code signing deferred to v2)
- No collaborative features, no cloud sync — by design

## Non-Goals

- Translation (we only romanize, not translate to English)
- Cloud or web-hosted version
- Mobile or tablet support
- User accounts or shared state
- History, undo, or version tracking
- Real-time collaboration
- Auto-update from within the app (manual reinstall for v1)
