# Test Samples

Sample documents for handler development and integration testing.

## What is committed, and what is not

`.gitignore` excludes `samples/*` and whitelists only this README and the two
synthesized fixtures. **Real HMI documents never enter this repository.**
Vendor statements, board papers, and franchise compliance material stay on
local machines, redacted or otherwise. Redaction is not a security boundary
this project relies on. The exclusion is enforced by `.gitignore` rather than
by discipline, so a real document cannot be committed by accident.

| File | Origin | Committed |
|---|---|---|
| `01_basic.docx` | Microsoft Word | no |
| `02_formatting.docx` | Microsoft Word | no |
| `03_table.docx` | Microsoft Word | no |
| `04_headers.docx` | Microsoft Word | no |
| `05_lists.docx` | **synthesized** | **yes** |
| `06_revisions.docx` | Microsoft Word | no |
| `07_comments.docx` | Microsoft Word | no |
| `08_images.docx` | Microsoft Word | no |
| `09_textbox.docx` | Microsoft Word | no |
| `10_composite.docx` | **synthesized** | **yes** |
| the real board paper | HMI | never |

Regenerate the synthesized fixtures with:

    python python/tests/fixtures/build_fixtures.py

The output is byte-for-byte deterministic.

## What the synthesized fixtures do not prove

**A green test suite over `05` and `10` is not a guarantee about real
documents.**

Both files write each Japanese phrase as a single `<w:t>`. Microsoft Word does
not. Word splits a logical word across several `<w:r>` runs for reasons
unrelated to formatting — spell-check state, revision bookkeeping, proofing
language, rsid tracking — so `株式会社` routinely arrives as three runs that
share identical formatting.

The consequence: `10_composite.docx` proves the constructs *compose* under
artificial conditions, with clean run boundaries the handler never has to
reassemble. The split-run redistribution path, which is the hardest and most
failure-prone part of the DOCX handler, is barely exercised by it.

Only two artefacts test that path honestly:

- `02_formatting.docx`, produced by Word, where **Word** chose the splits
- the real board paper, run locally by Tomo and never committed

Treat a pass over the synthesized fixtures as a necessary condition, never a
sufficient one.

## Japanese content

Where the synthesized fixtures contain Japanese, the text is drawn from the
Phase 1 test corpus — `株式会社`, `東京`, `大阪`, `2026年5月13日`, `第3四半期`,
`私は学生です` — rather than invented. If a romanization is wrong, it should be
wrong in a way the Phase 1 suite has already characterised, not a new mystery.

## Contents of each sample

1. `01_basic.docx` — plain Japanese paragraphs, one font, no formatting
   variation; the date `2026年5月13日`; `第3四半期`; one full English sentence;
   the punctuation `、。「」・` used naturally.
2. `02_formatting.docx` — a Japanese word split mid-word across runs of
   **differing** formatting, plus a word split across runs of **identical**
   formatting (Word's own doing, and the commoner case).
3. `03_table.docx` — a table with a `gridSpan` merge and a `vMerge` merge,
   Japanese in cells, one cell with a manual line break, one numeric cell.
4. `04_headers.docx` — distinct first-page, odd and even headers and footers,
   Japanese text, `PAGE` and `NUMPAGES` fields, at least three pages.
5. `05_lists.docx` — three nesting depths of numbered list plus a bulleted
   list. **The numbering format itself carries Japanese literals** (`第%1章`,
   `%2項`). Romanizing `numbering.xml` is deferred under decision D7; the
   fixture exists now so that the day it is implemented, the `xfail` test in
   `python/tests/test_samples.py` flips on its own.
6. `06_revisions.docx` — tracked insertions and deletions by two authors, a
   formatting-only revision (`w:rPrChange`), and a moved paragraph
   (`w:moveFrom` / `w:moveTo`). Nothing accepted or rejected.
   **Decision D3: the handler refuses this file.** It exists to test refusal.
7. `07_comments.docx` — two or three Japanese comments anchored to Japanese
   text, one spanning several words, one reply. **No tracked changes.**
   Comments are content and are romanized (decision D4).
8. `08_images.docx` — an embedded raster image containing Japanese text in its
   pixels, a Japanese caption beneath, one inline shape or logo. The image must
   be a real JPEG or PNG so the byte-preservation path is exercised.
9. `09_textbox.docx` — a text box with Japanese, and if available a SmartArt
   diagram and a chart with Japanese labels. SmartArt and charts are Phase 4
   backlog, not Phase 2 behaviour.
10. `10_composite.docx` — headers, footers, a merged-cell table, nested lists,
    an embedded PNG, a VML text box, comments, footnotes, endnotes, an internal
    hyperlink, a bookmark, and a `PAGE` field, with **no tracked changes**.
    Proves the parts compose. See the caveat above.

Note that comments (07) and revisions (06) are deliberately in separate files.
D3 refuses documents with revision marks and D4 romanizes comments, so a single
file containing both could only ever exercise refusal, leaving the comment path
untested.
