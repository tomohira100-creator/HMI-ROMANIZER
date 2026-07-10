# CLAUDE.md — Instructions for Claude Code in This Repo

This file is read on every session start. Follow these instructions in every session unless explicitly overridden by Tomo.

## Project Context

This is ROMANIZER — a Windows desktop application for converting Japanese text in office documents to Hepburn romaji while preserving formatting.

Before doing anything in a new session, read:
1. `PRD.md` — product plan
2. `ARCHITECTURE.md` — technical design
3. The most recent commits to understand current state

## Working Style — Critical

Tomo is a senior manager at HMI Hotel Group Japan and works at a high level of detail and precision. He expects:

- **Extreme detail.** Never oversimplify. Never gloss over edge cases.
- **Explicit reasoning.** Show your thinking before making a decision.
- **Accuracy over speed.** It's better to take longer and get it right.
- **Professional tone.** No emojis. No casual language. No "" or "Awesome!"
- **State uncertainty explicitly.** If something is unknown, say so.
- **Separate facts, assumptions, and opinions** when they appear together.

## What to Always Do

- **Read `PRD.md` and `ARCHITECTURE.md` at the start of every session.**
- **Commit and push after completing every meaningful unit of work.** Tomo has standing instructions: always remind him to commit and push after any code task. In Claude Code, do the commits yourself when the work is done.
- **Update `CHANGELOG.md`** with a one-line entry per commit (create the file if it doesn't exist).
- **Write tests for new functionality.** Every handler module gets tests.
- **Use `.docx` not `.pdf`** if asked to produce a document deliverable.
- **Build in phases, in the order specified in `PRD.md`.** Do not skip ahead.

## What to Never Do

- **Never invent features not in `PRD.md`.** If something seems missing, ask Tomo before adding.
- **Never restructure existing code without explicit approval.**
- **Never change the tech stack** without explicit approval.
- **Never add network calls** to the runtime app. Everything is offline.
- **Never add analytics, telemetry, or logging-to-cloud.**
- **Never store user data** between sessions in the app itself.
- **Never use emojis in code comments, commit messages, or output.**
- **Never call Tomo's father "papa"** — always "dad" or "Shacho" or "President Hira."
- **Never use informal terms like "uncle" or "akka"** in any context.

## Output Preferences

- Structured tables, numbered lists, or step-by-step when explaining
- Code blocks for all code
- File paths in backticks
- When asking questions, present 2–4 specific options, not open-ended prompts
- When showing progress, summarize at the end with what was done and what's next

## Build Phases (in order)

1. **Romanization core library** (`python/romanizer/core.py`, `dictionary.py`, `cli.py`)
2. **DOCX handler** (`handlers/docx_handler.py`)
3. **XLSX handler** (`handlers/xlsx_handler.py`)
4. **PPTX handler** (`handlers/pptx_handler.py`)
5. **PDF born-digital handler** (`handlers/pdf_handler.py`)
6. **OCR pipeline** (`handlers/ocr_handler.py`)
7. **Tauri shell + React UI** (`src-tauri/`, `src/`)
8. **Python sidecar integration** (`ipc.py`, Rust IPC code)
9. **Windows installer via GitHub Actions** (`.github/workflows/`)
10. **Real-world testing iteration**

Do not advance to the next phase without explicit approval from Tomo.

## Testing Approach

- Each Python module: unit tests in `python/tests/`
- Each handler: integration test with a sample file in `samples/`
- Before declaring a phase complete: run the test suite and report results
- The CLI (`python -m romanizer convert ...`) is the primary test interface until the UI is built in Phase 7

## Romanization Rules Reference

See `PRD.md` for the full spec. Quick reference:
- Hepburn, Title Case default
- ALL CAPS for known abbreviations only
- Macrons preserved (ū, ō, ā, ē, ī)
- Numbers stay as numerals
- Punctuation preserved
- English untouched

## Commit Message Style

```
<type>(<phase>): <short summary>

<body if needed>
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `build`

Example: `feat(phase-1): add Hepburn romanization core with macron support`

## When in Doubt

Ask Tomo. Present 2–4 specific options. Don't guess.
