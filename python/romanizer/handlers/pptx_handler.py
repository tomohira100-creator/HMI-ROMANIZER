"""PPTX handler: romanize slide and speaker-note text, preserve everything else.

Where the text lives
--------------------
Display text is in `<a:t>` runs, stored inline per slide -- there is no
shared-string table as in XLSX, so editing one slide touches only that part.
The handler romanizes `<a:t>` in:

  ppt/slides/slideN.xml        slide content (titles, bodies, tables, grouped
                               shapes -- all reached by one recursive a:t walk)
  ppt/notesSlides/notesSlideN  the speaker's script

and nothing else. In particular:

  @typeface  Font names are Japanese (游ゴシック, メイリオ) but are font
             specifications; romanizing them breaks rendering. Never touched --
             they live in attributes, which the a:t walk never reads.
  @descr     Image alt-text. Metadata, left as-is (decision D1).
  a:fld      Slide-number / date fields. The cached value regenerates, so it is
             a segment boundary and its inner a:t is shielded, not romanized.
  masters,   Template parts. Their placeholder a:t is prompt boilerplate
  layouts    ("クリックして..."), never shown to a viewer. Excluded
             STRUCTURALLY, by part -- the strongest form of the type-based
             exclusion (decision D2): it reads the part's role in the package,
             never the visible string, so it survives any re-worded template.

Split runs
----------
PowerPoint splits a word across `a:r` runs constantly -- 31.8% of paragraphs in
the real decks are multi-run. Reassembly (concatenate, romanize, first-run-wins)
is shared with the DOCX handler via run_reassembly.

Deferred, but LOUDLY (decision D4)
----------------------------------
Chart labels (`c:` parts), SmartArt (`dgm:` parts), embedded OLE objects, and
comments are not converted in this phase. A converted deck that silently left
Japanese chart labels in place is the failure that reaches a Marriott meeting
unnoticed. `convert` returns the destination together with a list of every
unconverted part that still holds Japanese, for the caller to surface. The
conversion is not failed; it is reported.
"""

import io
import re
import zipfile
from pathlib import Path

from lxml import etree

from .. import dictionary as _dictionary
from ..core import romanize_spans
from ..ooxml_parts import Package
from ..run_reassembly import RunModel, romanize_paragraph

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_SLIDE = re.compile(r"^ppt/slides/slide\d+\.xml$")
_NOTES = re.compile(r"^ppt/notesSlides/notesSlide\d+\.xml$")

_JAPANESE = re.compile("[぀-ゟ゠-ヿ㐀-䶿一-鿿々]")

#: DrawingML paragraphs. a:br (line break) and a:fld (field) are boundaries;
#: a:fld additionally shields its cached a:t value from romanization.
_RUN_MODEL = RunModel(
    para_tag=A + "p",
    text_tag=A + "t",
    boundary_tags=(A + "br", A + "fld"),
    space_attr=XML_SPACE,
)


class PptxError(Exception):
    """Base class for PPTX handler failures."""


#: CLI integration.
handler_error = PptxError
refusal_error = None


class Conversion:
    """The result of a conversion: the output path and any unconverted parts.

    Behaves as a path (os.fspath) so callers that only want the destination are
    unaffected.
    """

    def __init__(self, destination, unconverted):
        self.destination = Path(destination)
        #: list of (part_name, kind, japanese_char_count)
        self.unconverted = unconverted

    def __fspath__(self):
        return str(self.destination)

    def __str__(self):
        return str(self.destination)


def _romanize_part(blob, dic):
    root = etree.fromstring(blob)
    for paragraph in root.iter(A + "p"):
        romanize_paragraph(paragraph, dic, _RUN_MODEL, romanize_spans, _JAPANESE)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _japanese_in_element_text(root):
    """Count Japanese characters in element text, ignoring attributes.

    Attributes hold font names (@typeface) and alt-text (@descr), which are not
    content; only element text (a:t, c:v, ...) counts as unconverted content.
    """
    total = 0
    for element in root.iter():
        if element.text:
            total += len(_JAPANESE.findall(element.text))
    return total


def _classify_unconverted(name):
    """The kind of an unconverted part, or None if it is not content we track."""
    if re.search(r"ppt/charts/", name):
        return "chart"
    if re.search(r"ppt/diagrams/", name):
        return "SmartArt"
    if re.search(r"ppt/comments/|/comment", name.lower()):
        return "comment"
    if re.search(r"ppt/embeddings/", name):
        return "embedded object"
    return None


def _scan_unconverted(package):
    """Every part holding Japanese content that this phase does not convert."""
    notices = []
    for name in package.names:
        kind = _classify_unconverted(name)
        if kind is None:
            continue
        blob = package.read_part(name)
        count = 0
        if name.endswith(".xml"):
            try:
                count = _japanese_in_element_text(etree.fromstring(blob))
            except etree.XMLSyntaxError:
                count = 0
        elif kind == "embedded object":
            # An embedded OOXML object is itself a zip; peek for Japanese.
            try:
                inner = zipfile.ZipFile(io.BytesIO(blob))
                count = sum(
                    len(_JAPANESE.findall(inner.read(n).decode("utf-8", "replace")))
                    for n in inner.namelist()
                    if n.endswith(".xml")
                )
            except Exception:
                count = 0
        if count:
            notices.append((name, kind, count))
    notices.sort(key=lambda row: -row[2])
    return notices


def has_comments(package):
    """Whether the deck carries PowerPoint comments (p:cm), which are skipped.

    Kept distinct so a future comments feature can find its entry point, and so
    the notice can name comments as a documented gap rather than a silent miss.
    """
    return any(_classify_unconverted(n) == "comment" for n in package.names)


def convert(source, destination, dic=None):
    """Romanize a PPTX. Returns a Conversion with any unconverted parts noted."""
    source = Path(source)
    destination = Path(destination)
    dic = dic or _dictionary.default()

    package = Package.read(source)

    for name in package.names:
        if _SLIDE.match(name) or _NOTES.match(name):
            package.replace(name, _romanize_part(package.read_part(name), dic))

    unconverted = _scan_unconverted(package)

    temporary = destination.with_name(destination.name + ".partial")
    try:
        package.write(temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return Conversion(destination, unconverted)
