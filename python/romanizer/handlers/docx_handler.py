"""DOCX handler: romanize Japanese text, preserve everything else.

Design
------
Every character Word renders lives in a `w:t` leaf. One traversal of those
leaves reaches body paragraphs, table cells, headers, footers, footnotes,
endnotes, comments, text boxes, content controls, hyperlink display text and
field *results*, with no per-construct code. Formatting lives in siblings
(`w:rPr`) and ancestors (`w:pPr`, `w:tbl`) that this module never writes to.

Preservation is therefore structural rather than enumerated: the only thing
mutated is the `.text` of a `w:t`, plus an `xml:space` attribute when the new
text has significant leading or trailing whitespace. Untouched parts are
copied byte for byte by `ooxml_parts.Package`.

Field *codes* (`w:instrText`) are never romanized -- rewriting ` PAGE ` breaks
the field. They act as segment boundaries instead.

Split runs
----------
Word splits a logical word across several `w:r` runs for reasons unrelated to
formatting. Romanizing each run separately would romanize half-words. So a
paragraph's leaves are concatenated, romanized as one string via
`core.romanize_spans`, and each output span is written back to the leaf owning
its first source character (decision D2, "first-character run wins").

Measured against six real HMI documents and 51,858 Japanese tokens: exactly one
word was split across runs, and both runs carried identical formatting. Zero
words were split across runs of differing formatting, so "first-character wins"
discards nothing in practice.

Concatenating first is still what makes that one real case correct. Word broke
`際しての` as `際` + `しての`. Romanizing each run alone gives `Sai` + `Shite no`
= `SaiShite no`. Romanizing the concatenation gives `Saishite no`.

Tracked changes
---------------
Refused, not romanized (decision D3). Revision markup records who changed what
and when, and in a franchise audit or vendor dispute that record is evidence.
Romanizing it would convert evidence into something nobody can diff against the
original. Refusal costs the user thirty seconds and cannot corrupt anything.
"""

import re
from pathlib import Path

from lxml import etree

from .. import dictionary as _dictionary
from ..core import romanize_spans
from ..ooxml_parts import Package, is_xml_part
from ..run_reassembly import RunModel, romanize_paragraph

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

#: Parts whose w:t leaves carry rendered document text.
TEXT_PARTS = re.compile(
    r"^word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$"
)

#: Every revision construct. Formatting-only revisions (w:rPrChange) carry no
#: w:ins or w:del, so a check that looks only for insertions and deletions
#: passes a document that still holds revision history.
REVISION_TAGS = (
    "ins", "del", "moveFrom", "moveTo",
    "moveFromRangeStart", "moveToRangeStart",
    "rPrChange", "pPrChange", "tblPrChange", "tcPrChange",
    "trPrChange", "sectPrChange", "numberingChange",
)

#: Elements that end a run of text. Romanization never crosses one, so a word
#: is never formed across a line break, a tab, or a field code.
BOUNDARY_TAGS = frozenset(
    W + tag
    for tag in ("br", "tab", "cr", "instrText", "fldChar", "noBreakHyphen", "ptab", "sym")
)

#: Kana and kanji. Excludes the katakana middle dot U+30FB and its halfwidth
#: form U+FF65, which are punctuation and are preserved verbatim.
_JAPANESE = re.compile(
    "[ぁ-ゟ゠-ヺー-ヿｦ-ﾝ㐀-䶿一-鿿々]"
)


class DocxError(Exception):
    """Base class for DOCX handler failures."""


class RevisionMarkupError(DocxError):
    """The document carries tracked changes. See decision D3."""

    def __init__(self, path, tags):
        self.path = str(path)
        self.tags = sorted(set(tags))
        super().__init__(
            "{} contains tracked changes and was not converted.\n\n"
            "Open it in Word, then choose Review > Accept > Accept All Changes "
            "(or Reject All Changes), save the document, and convert it again.\n\n"
            "ROMANIZER will not convert a document with revision history. "
            "Romanizing the record of who changed what, and when, would destroy "
            "it. That decision belongs to you, not to this tool.".format(
                Path(path).name
            )
        )


#: CLI integration: the base error, and the refusal type reported as a distinct
#: non-crash outcome.
handler_error = DocxError
refusal_error = RevisionMarkupError


def find_revision_markup(package):
    """Every revision tag present anywhere in the package, not just document.xml."""
    found = []
    for name in package.names:
        if not is_xml_part(name):
            continue
        try:
            root = etree.fromstring(package.read_part(name))
        except etree.XMLSyntaxError:
            continue
        for tag in REVISION_TAGS:
            if root.find(".//" + W + tag) is not None:
                found.append(tag)
    return found


#: How the shared reassembler addresses DOCX paragraphs. The word-splitting
#: algorithm lives in run_reassembly; only these tags are DOCX-specific.
_RUN_MODEL = RunModel(
    para_tag=W + "p",
    text_tag=W + "t",
    boundary_tags=BOUNDARY_TAGS,
    space_attr=XML_SPACE,
)


def _romanize_part(blob, dic):
    root = etree.fromstring(blob)
    for paragraph in root.iter(W + "p"):
        romanize_paragraph(paragraph, dic, _RUN_MODEL, romanize_spans, _JAPANESE)
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )


def convert(source, destination, dic=None):
    """Romanize a DOCX. Raises RevisionMarkupError before writing anything."""
    source = Path(source)
    destination = Path(destination)
    dic = dic or _dictionary.default()

    package = Package.read(source)

    revisions = find_revision_markup(package)
    if revisions:
        # Refuse before writing. A partial output file is worse than none.
        raise RevisionMarkupError(source, revisions)

    for name in package.names:
        if TEXT_PARTS.match(name):
            package.replace(name, _romanize_part(package.read_part(name), dic))

    # Write via a temporary file so a failure mid-write cannot leave a
    # truncated document where the user expects a converted one.
    temporary = destination.with_name(destination.name + ".partial")
    try:
        package.write(temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination
