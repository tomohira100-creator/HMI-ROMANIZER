"""XLSX handler: romanize Japanese text, preserve everything else.

Where the text lives
--------------------
Almost all display text is in `xl/sharedStrings.xml`; worksheet cells reference
it by index (`<c t="s"><v>5</v></c>`). Romanizing a shared string **in place** --
same `<si>` count, same order, only the `<t>` text changed -- leaves every cell
index valid, so no worksheet part changes on account of the strings. Never dedup
or reorder the table: two Japanese strings can romanize to the same romaji, and
merging them would reindex every referencing cell and rewrite every sheet.

The rest of the Japanese needs targeted edits to worksheet or workbook XML:

  sheet names        xl/workbook.xml <sheet name="...">. Romanized, and every
                     reference to them rewritten (see below).
  sheet references   Formulas and defined names reference sheets by name:
                     `内訳!G22`, `'鏡 '!A1`, print areas in definedNames.
                     Romanizing a sheet name without rewriting these breaks the
                     formula. Sheet refs use SINGLE quotes; string literals use
                     DOUBLE quotes, so the two never collide. A romanized name
                     may contain a space (Mitsumori Jōken), so rewritten refs
                     are always emitted quoted.
  formula literals   `B52&"合計"` -- Japanese inside a double-quoted literal.
  cached str values  A formula cell (t="str") caches its last computed value.
                     Excel recomputes on open, but the cached <v> is romanized
                     too so there is no flash of Japanese before recompute.
  headers/footers    <headerFooter> text, mixed with &L/&C/&R section codes.

Deliberately untouched, byte-identical: images, drawings, printer settings,
styles, theme, calcChain (it references cells by sheet index, not name, so
renaming sheets does not invalidate it), and drawing shape name attributes
(internal identifiers, not rendered text).

Not built on openpyxl: a load-and-save drops drawings, printer settings and
headers and rewrites every shared string inline. See ooxml_parts.
"""

import re
from pathlib import Path

from lxml import etree

from .. import dictionary as _dictionary
from ..core import romanize
from ..ooxml_parts import Package

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

SHARED_STRINGS = "xl/sharedStrings.xml"
WORKBOOK = "xl/workbook.xml"
_SHEET = re.compile(r"^xl/worksheets/sheet\d+\.xml$")

_JAPANESE = re.compile("[぀-ゟ゠-ヿ㐀-䶿一-鿿々]")


class XlsxError(Exception):
    """Base class for XLSX handler failures."""


#: CLI integration. The XLSX handler refuses nothing; it has no refusal type.
handler_error = XlsxError
refusal_error = None


def _has_japanese(text):
    return bool(text) and _JAPANESE.search(text) is not None


def _serialize(root):
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# --- Shared strings --------------------------------------------------------

def _romanize_shared_strings(blob, dic):
    """Romanize every <t> in place. The <si> count and order are untouched, so
    every worksheet cell index stays valid and no sheet needs rewriting."""
    root = etree.fromstring(blob)
    changed = False
    for node in root.iter(M + "t"):
        if _has_japanese(node.text):
            node.text = romanize(node.text, dic)
            changed = True
    return _serialize(root) if changed else None


# --- Sheet names and references --------------------------------------------

def sheet_name_map(workbook_root, dic):
    """{original sheet name -> romanized, whitespace-trimmed name}.

    Sheet names are identifiers, so leading/trailing spaces (表紙 has one) are
    trimmed; the romaji of a trailing-space name would otherwise carry a
    trailing space into every reference.
    """
    mapping = {}
    for sheet in workbook_root.iter(M + "sheet"):
        name = sheet.get("name")
        if _has_japanese(name):
            mapping[name] = romanize(name, dic).strip()
    return mapping


def rewrite_sheet_refs(text, name_map):
    """Rewrite sheet-name references in a formula or defined-name string.

    Handles the quoted form ('鏡 '!A1, used when the name has a space) and the
    unquoted form (内訳!G22). The replacement is always quoted, because a
    romanized name may contain a space. Only single-quoted names are sheet
    references; double-quoted text is a string literal and is left alone here.
    """
    if not text:
        return text
    for original, romanized in name_map.items():
        quoted = "'{}'!".format(romanized)
        # Quoted original: '表紙 '! (the name may hold a trailing space).
        text = text.replace("'{}'!".format(original), quoted)
        # Unquoted original: 内訳! -- guard the left edge so a longer name is
        # not clipped. Japanese names carry no ASCII word characters, so the
        # boundary is simple.
        text = re.sub(
            r"(?<![A-Za-z0-9_'\"])" + re.escape(original) + "!",
            quoted,
            text,
        )
    return text


def romanize_formula_literals(text, dic):
    """Romanize Japanese inside double-quoted string literals in a formula."""
    if not text or '"' not in text:
        return text

    def replace(match):
        inner = match.group(1)
        return '"{}"'.format(romanize(inner, dic)) if _has_japanese(inner) else match.group(0)

    return re.sub(r'"([^"]*)"', replace, text)


# --- Workbook and worksheets ----------------------------------------------

def _romanize_workbook(blob, name_map, dic):
    """Rename sheets and rewrite sheet references in defined names."""
    root = etree.fromstring(blob)
    for sheet in root.iter(M + "sheet"):
        name = sheet.get("name")
        if name in name_map:
            sheet.set("name", name_map[name])
    for defined in root.iter(M + "definedName"):
        if defined.text:
            defined.text = rewrite_sheet_refs(defined.text, name_map)
    return _serialize(root)


def _romanize_worksheet(blob, name_map, dic):
    """Rewrite formula references and literals, cached string values, and
    header/footer text. Returns None when nothing in the sheet changed, so the
    part stays byte-identical."""
    root = etree.fromstring(blob)
    changed = False

    for cell in root.iter(M + "c"):
        formula = cell.find(M + "f")
        if formula is not None and formula.text:
            new = rewrite_sheet_refs(formula.text, name_map)
            new = romanize_formula_literals(new, dic)
            if new != formula.text:
                formula.text = new
                changed = True
        # A formula cell caches its computed value in <v>. Only t="str" holds a
        # string there; t="s" holds a shared-string index and must not change.
        if cell.get("t") == "str":
            value = cell.find(M + "v")
            if value is not None and _has_japanese(value.text):
                value.text = romanize(value.text, dic)
                changed = True

    header_footer = root.find(M + "headerFooter")
    if header_footer is not None:
        for node in header_footer.iter():
            if node.text and _has_japanese(node.text):
                node.text = romanize(node.text, dic)
                changed = True

    return _serialize(root) if changed else None


# --- Entry point -----------------------------------------------------------

def convert(source, destination, dic=None):
    """Romanize an XLSX, preserving every untouched part byte for byte."""
    source = Path(source)
    destination = Path(destination)
    dic = dic or _dictionary.default()

    package = Package.read(source)
    names = package.names

    if WORKBOOK not in names:
        raise XlsxError("{}: not a workbook (no {})".format(source.name, WORKBOOK))

    workbook_root = etree.fromstring(package.read_part(WORKBOOK))
    name_map = sheet_name_map(workbook_root, dic)

    if SHARED_STRINGS in names:
        romanized = _romanize_shared_strings(package.read_part(SHARED_STRINGS), dic)
        if romanized is not None:
            package.replace(SHARED_STRINGS, romanized)

    if name_map:
        package.replace(WORKBOOK, _romanize_workbook(package.read_part(WORKBOOK), name_map, dic))

    for name in names:
        if _SHEET.match(name):
            romanized = _romanize_worksheet(package.read_part(name), name_map, dic)
            if romanized is not None:
                package.replace(name, romanized)

    temporary = destination.with_name(destination.name + ".partial")
    try:
        package.write(temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination
