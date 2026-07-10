"""Tests over the synthesized DOCX fixtures.

These assert the fixtures are well formed and contain what the handler will
need to exercise. They do not test the handler, which does not exist yet.

A pass here says nothing about real Word documents: every Japanese phrase in
these fixtures sits in a single w:t, whereas Word splits words across runs.
See samples/README.md and the docstring in fixtures/build_fixtures.py.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "samples"
BUILDER = REPO_ROOT / "python" / "tests" / "fixtures" / "build_fixtures.py"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

LISTS = SAMPLES / "05_lists.docx"
COMPOSITE = SAMPLES / "10_composite.docx"

# Every revision construct decision D3 refuses. Not only w:ins and w:del, and
# not only in document.xml.
REVISION_TAGS = (
    "ins", "del", "moveFrom", "moveTo",
    "rPrChange", "pPrChange", "tblPrChange", "tcPrChange", "sectPrChange",
)


def parts(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def texts(blob):
    root = etree.fromstring(blob)
    return [node.text for node in root.iter(W + "t")]


@pytest.fixture(scope="module", autouse=True)
def ensure_fixtures():
    if not (LISTS.exists() and COMPOSITE.exists()):
        subprocess.run([sys.executable, str(BUILDER)], check=True)


# --- Both fixtures ---------------------------------------------------------

@pytest.mark.parametrize("path", [LISTS, COMPOSITE])
def test_fixture_is_a_valid_zip(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None


@pytest.mark.parametrize("path", [LISTS, COMPOSITE])
def test_every_xml_part_is_well_formed(path):
    for name, blob in parts(path).items():
        if name.endswith(".xml") or name.endswith(".rels"):
            etree.fromstring(blob)


@pytest.mark.parametrize("path", [LISTS, COMPOSITE])
def test_fixture_has_no_revision_marks(path):
    """Both must convert, not be refused. D3 refusal is tested with 06."""
    for name, blob in parts(path).items():
        if not name.endswith(".xml"):
            continue
        root = etree.fromstring(blob)
        for tag in REVISION_TAGS:
            assert not list(root.iter(W + tag)), "{} contains w:{}".format(name, tag)


def test_build_is_deterministic(tmp_path):
    before = {p: (SAMPLES / p).read_bytes() for p in (LISTS.name, COMPOSITE.name)}
    subprocess.run([sys.executable, str(BUILDER)], check=True)
    after = {p: (SAMPLES / p).read_bytes() for p in (LISTS.name, COMPOSITE.name)}
    assert before == after


# --- 05_lists.docx ---------------------------------------------------------

def test_lists_has_three_nesting_depths():
    root = etree.fromstring(parts(LISTS)["word/document.xml"])
    levels = {node.get(W + "val") for node in root.iter(W + "ilvl")}
    assert levels == {"0", "1", "2"}


def test_lists_uses_two_numbering_definitions():
    root = etree.fromstring(parts(LISTS)["word/document.xml"])
    assert {node.get(W + "val") for node in root.iter(W + "numId")} == {"1", "2"}


def test_numbering_format_carries_japanese_literals():
    """The precondition for the D7 work. Passes today."""
    root = etree.fromstring(parts(LISTS)["word/numbering.xml"])
    formats = [node.get(W + "val") for node in root.iter(W + "lvlText")]
    assert "第%1章" in formats
    assert "%2項" in formats


def test_lists_body_text_comes_from_the_phase_1_corpus():
    assert texts(parts(LISTS)["word/document.xml"]) == [
        "東京", "株式会社", "大阪", "第3四半期", "2026年5月13日", "私は学生です", "東京",
    ]


@pytest.mark.xfail(
    reason="D7: romanizing numbering.xml w:lvlText is deferred. "
    "When implemented, this xpasses and the deferral can be closed.",
    strict=False,
)
def test_numbering_literals_are_romanized():
    from romanizer.handlers import docx_handler  # noqa: F401  (absent until Phase 2)

    out = SAMPLES / "_05_out.docx"
    docx_handler.convert(LISTS, out)
    try:
        root = etree.fromstring(parts(out)["word/numbering.xml"])
        formats = [node.get(W + "val") for node in root.iter(W + "lvlText")]
        assert "Dai %1 Shō" in formats
    finally:
        out.unlink(missing_ok=True)


# --- 10_composite.docx -----------------------------------------------------

def test_composite_contains_every_construct():
    blobs = parts(COMPOSITE)
    document = etree.fromstring(blobs["word/document.xml"])

    present = {tag: bool(list(document.iter(W + tag))) for tag in (
        "tbl", "gridSpan", "vMerge", "numPr", "hyperlink", "bookmarkStart",
        "commentRangeStart", "commentReference", "footnoteReference",
        "endnoteReference", "fldSimple", "br", "drawing", "pict",
    )}
    missing = [tag for tag, found in present.items() if not found]
    assert not missing, "missing constructs: {}".format(missing)

    for name in (
        "word/header1.xml", "word/footer1.xml", "word/footnotes.xml",
        "word/endnotes.xml", "word/comments.xml", "word/media/image1.png",
    ):
        assert name in blobs, "missing part {}".format(name)


def test_composite_embeds_a_real_png():
    blob = parts(COMPOSITE)["word/media/image1.png"]
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"


def test_composite_field_code_is_present_and_must_never_be_romanized():
    document = etree.fromstring(parts(COMPOSITE)["word/document.xml"])
    instrs = [node.get(W + "instr") for node in document.iter(W + "fldSimple")]
    assert " PAGE " in instrs


def test_composite_text_lives_in_every_part_the_handler_must_reach():
    blobs = parts(COMPOSITE)
    assert texts(blobs["word/header1.xml"]) == ["株式会社"]
    assert texts(blobs["word/footnotes.xml"]) == ["大阪"]
    assert texts(blobs["word/endnotes.xml"]) == ["東京"]
    assert texts(blobs["word/comments.xml"]) == ["株式会社"]


def test_composite_has_an_empty_text_node():
    """The vMerge continuation cell yields w:t with text None. The handler
    must tolerate it rather than crash on NoneType."""
    document = etree.fromstring(parts(COMPOSITE)["word/document.xml"])
    assert any(node.text is None for node in document.iter(W + "t"))


def test_composite_text_box_holds_japanese():
    document = etree.fromstring(parts(COMPOSITE)["word/document.xml"])
    boxes = list(document.iter(W + "txbxContent"))
    assert len(boxes) == 1
    assert texts(etree.tostring(boxes[0])) == ["株式会社"]
