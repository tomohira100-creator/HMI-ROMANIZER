"""Compare romanized output against a human reference, classifying divergences.

The samples/expected/ corpus is a REFERENCE, not an oracle. When our output
differs from the human's, sometimes we are wrong -- a misread vendor or
construction term -- and sometimes the human took a shortcut: a dropped macron,
an inconsistent spacing choice. Those are not the same finding and must not
look the same in a report, or a macron typo drowns out a real misreading.

Each divergence is classified:

  macron-only   differ only in macrons (Hyoshi vs Hyōshi). Almost always the
                human dropping a diacritic; our Modified Hepburn is more
                correct here (decision D4). Not a tool defect.
  spacing-case  differ only in whitespace or letter case.
  substantive   differ in letters -- a likely misread, worth investigating.

Divergences are ranked substantive-first, then by how many cells use the
string, so the findings that matter surface at the top.
"""

import re
import unicodedata

from lxml import etree

from . import dictionary as _dictionary
from .core import romanize

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

_MACRONS = str.maketrans("āīūēōĀĪŪĒŌ", "aiueoAIUEO")


def strip_macrons(text):
    return unicodedata.normalize("NFC", text).translate(_MACRONS)


def classify(ours, theirs):
    """How do two romanizations of the same source differ?"""
    if ours == theirs:
        return "identical"
    if strip_macrons(ours) == strip_macrons(theirs):
        return "macron-only"
    a = re.sub(r"\s+", "", ours).lower()
    b = re.sub(r"\s+", "", theirs).lower()
    if a == b:
        return "spacing-case"
    if strip_macrons(a) == strip_macrons(b):
        return "spacing-case"
    return "substantive"


def _si_text(si):
    """The display text of a shared string, excluding <rPh> phonetic ruby.

    Ruby is a katakana reading of the kanji; including it would double the
    reading (件名 with ruby ケンメイ would read as "Kenmei Kenmei").
    """
    parts = []
    for t in si.iter(M + "t"):
        parent = t.getparent()
        if parent is not None and parent.tag == M + "rPh":
            continue
        parts.append(t.text or "")
    return "".join(parts)


def _shared_strings(zip_bytes):
    root = etree.fromstring(zip_bytes)
    return [_si_text(si) for si in root.iter(M + "si")]


def _usage_counts(package, n_strings):
    """How many cells reference each shared-string index."""
    counts = [0] * n_strings
    for name in package.names:
        if not re.match(r"^xl/worksheets/sheet\d+\.xml$", name):
            continue
        root = etree.fromstring(package.read_part(name))
        for cell in root.iter(M + "c"):
            if cell.get("t") == "s":
                value = cell.find(M + "v")
                if value is not None and value.text and value.text.isdigit():
                    index = int(value.text)
                    if 0 <= index < n_strings:
                        counts[index] += 1
    return counts


class Divergence:
    __slots__ = ("source", "ours", "theirs", "category", "usage")

    def __init__(self, source, ours, theirs, category, usage):
        self.source = source
        self.ours = ours
        self.theirs = theirs
        self.category = category
        self.usage = usage


_ORDER = {"substantive": 0, "spacing-case": 1, "macron-only": 2}


def compare_xlsx(original_path, expected_path, dic=None):
    """Romanize the original's shared strings and diff against the human's.

    Returns (divergences, summary). Alignment is by shared-string index, which
    holds because both files romanize in place and preserve the table's order.
    """
    from .ooxml_parts import Package

    dic = dic or _dictionary.default()
    original = Package.read(original_path)
    expected = Package.read(expected_path)

    src = _shared_strings(original.read_part("xl/sharedStrings.xml"))
    human = _shared_strings(expected.read_part("xl/sharedStrings.xml"))
    if len(src) != len(human):
        raise ValueError(
            "shared-string tables differ in length ({} vs {}); cannot align by "
            "index".format(len(src), len(human))
        )

    usage = _usage_counts(original, len(src))
    japanese = re.compile("[぀-ゟ゠-ヿ㐀-䶿一-鿿々]")

    divergences = []
    summary = {"identical": 0, "macron-only": 0, "spacing-case": 0, "substantive": 0}
    for i, source in enumerate(src):
        if not japanese.search(source):
            continue  # nothing for us to romanize; skip non-Japanese cells
        ours = romanize(source, dic)
        theirs = human[i]
        category = classify(ours, theirs)
        summary[category] += 1
        if category != "identical":
            divergences.append(Divergence(source, ours, theirs, category, usage[i]))

    divergences.sort(key=lambda d: (_ORDER[d.category], -d.usage))
    return divergences, summary


def _slide_segments(package):
    """Ordered (slide, segment text) for every slide, using the handler's own
    segmentation.

    A segment is a run of a:t leaves between hard boundaries (a:br, a:fld), the
    same unit the handler romanizes as one word. Aligning at the segment level
    -- not per run -- is what lets a reassembled split word (株式|会社 ->
    "Kabushiki Gaisha" in one run) compare correctly against the source.
    Excludes @typeface/@descr (attributes) and a:fld cached values.
    """
    import re as _re

    from .run_reassembly import RunModel, segments

    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    model = RunModel(a + "p", a + "t", (a + "br", a + "fld"))
    out = []
    for name in sorted(package.names):
        if not _re.match(r"^ppt/slides/slide\d+\.xml$", name):
            continue
        root = etree.fromstring(package.read_part(name))
        for paragraph in root.iter(a + "p"):
            for segment in segments(paragraph, model):
                out.append((name, "".join(leaf.text or "" for leaf in segment)))
    return out


def compare_pptx(original_path, expected_path, dic=None):
    """Diff our romanization of a deck's slide text against a human reference.

    Alignment is by (slide, segment order). Requires that the human kept the
    paragraph and boundary structure -- true when the reference was produced by
    romanizing in place, the same assumption the XLSX path makes.
    """
    from .ooxml_parts import Package

    dic = dic or _dictionary.default()
    src = _slide_segments(Package.read(original_path))
    human = _slide_segments(Package.read(expected_path))
    if len(src) != len(human):
        raise ValueError(
            "slide segment counts differ ({} vs {}); cannot align by "
            "segment order".format(len(src), len(human))
        )

    japanese = re.compile("[぀-ゟ゠-ヿ㐀-䶿一-鿿々]")
    divergences = []
    summary = {"identical": 0, "macron-only": 0, "spacing-case": 0, "substantive": 0}
    for (_name, source), (_hname, theirs) in zip(src, human):
        if not japanese.search(source):
            continue
        ours = romanize(source, dic)
        category = classify(ours, theirs)
        summary[category] += 1
        if category != "identical":
            divergences.append(Divergence(source, ours, theirs, category, 1))

    divergences.sort(key=lambda d: (_ORDER[d.category], -d.usage))
    return divergences, summary


def format_report(divergences, summary, limit=None):
    lines = []
    total = sum(summary.values())
    matched = summary["identical"]
    lines.append(
        "{} Japanese strings compared: {} identical, {} substantive, "
        "{} spacing/case, {} macron-only".format(
            total, matched, summary["substantive"], summary["spacing-case"],
            summary["macron-only"],
        )
    )
    lines.append(
        "  (macron-only divergences are the human dropping a diacritic, not a "
        "tool defect -- see corpus_diff)"
    )
    lines.append("")

    shown = divergences if limit is None else divergences[:limit]
    if not shown:
        lines.append("No divergences.")
        return "\n".join(lines)

    width_o = min(40, max((len(d.ours) for d in shown), default=5))
    width_t = min(40, max((len(d.theirs) for d in shown), default=5))
    header = "  {:<11} {:>4}  {:<{wo}}  {:<{wt}}  {}".format(
        "category", "uses", "ROMANIZER", "human", "source", wo=width_o, wt=width_t
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for d in shown:
        lines.append(
            "  {:<11} {:>4}  {:<{wo}}  {:<{wt}}  {}".format(
                d.category, d.usage, d.ours[:width_o], d.theirs[:width_t],
                d.source, wo=width_o, wt=width_t,
            )
        )
    if limit is not None and len(divergences) > limit:
        lines.append("  ... {} more".format(len(divergences) - limit))
    return "\n".join(lines)
