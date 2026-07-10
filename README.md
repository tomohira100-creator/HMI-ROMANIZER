# ROMANIZER

A Windows desktop application that converts Japanese text in office documents into Hepburn romaji while preserving original formatting, layout, and structure.

## What It Does

Drop in DOCX, XLSX, PPTX, PDF, PNG, or JPG files containing Japanese text. Get back the same files with all Japanese converted to romaji — same fonts, same colours, same tables, same charts, same images, same everything.

## Status

In active development. See `PRD.md` for the locked product plan and `ARCHITECTURE.md` for the technical design.

## Supported Formats

- DOCX (Microsoft Word)
- XLSX (Microsoft Excel)
- PPTX (Microsoft PowerPoint)
- PDF (born-digital with text layer)
- PDF (scanned, via OCR)
- PNG and JPG images

## Key Properties

- 100% offline after install
- No login, no accounts, no cloud
- No history or memory between sessions
- Up to 500 MB per file
- Batch conversion of multiple files in parallel

## Development

Developed on macOS. Final Windows installer built via GitHub Actions.

### Local development setup

Coming soon — populated as build phases progress.

### Build the Windows installer

Coming soon — populated when Phase 9 begins.

## Distribution

Single Windows `.msi` installer (~3 GB). Manually distributed to office staff. Installs to `C:\Program Files\ROMANIZER\`.

## License

Proprietary — HMI Hotel Group Japan internal tool.
