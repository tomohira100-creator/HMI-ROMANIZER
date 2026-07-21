"""PPTX handler integration tests.

Same three-tier strategy as DOCX/XLSX: untouched parts byte-identical, edited
parts isomorphic, text correct. PPTX stores text inline per slide, so the
byte-identity tier holds trivially for every non-slide part.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from romanizer import dictionary
from romanizer.handlers import pptx_handler as P

A = P.A

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "samples"
BUILDER = REPO_ROOT / "python" / "tests" / "fixtures" / "build_fixtures.py"
FIXTURE = SAMPLES / "13_slides.pptx"

REAL_DECKS = [
    SAMPLES / "expected" / "modi_hatsugen_romaji.pptx",
    SAMPLES / "expected" / "Romaji ppt.pptx",
]


@pytest.fixture(scope="module", autouse=True)
def ensure_fixture():
    if not FIXTURE.exists():
        subprocess.run([sys.executable, str(BUILDER)], check=True)


def parts(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def slide_texts(blob):
    return [t.text for t in etree.fromstring(blob).iter(A + "t")]


def skeleton(blob):
    out = []
    for element in etree.fromstring(blob).iter():
        attrib = {k: v for k, v in element.attrib.items() if k != P.XML_SPACE}
        out.append((element.tag, tuple(sorted(attrib.items()))))
    return out


@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    out = tmp_path_factory.mktemp("pptx") / "out.pptx"
    result = P.convert(FIXTURE, out)
    return out, result


# --- Three tiers ------------------------------------------------------------

def test_no_parts_added_or_lost(converted):
    out, _ = converted
    assert set(parts(FIXTURE)) == set(parts(out))


def test_untouched_parts_byte_identical(converted):
    out, _ = converted
    before, after = parts(FIXTURE), parts(out)
    for name in before:
        if name.startswith("ppt/slides/") or name.startswith("ppt/notesSlides/"):
            continue
        assert before[name] == after[name], "re-serialized: {}".format(name)


def test_theme_master_layout_chart_image_untouched(converted):
    out, _ = converted
    before, after = parts(FIXTURE), parts(out)
    for name in before:
        if any(k in name for k in ("theme", "Master", "Layout", "charts", "media")):
            assert before[name] == after[name], name


def test_slide_structure_isomorphic(converted):
    out, _ = converted
    assert skeleton(parts(FIXTURE)["ppt/slides/slide1.xml"]) == skeleton(
        parts(out)["ppt/slides/slide1.xml"]
    )


def test_slide_text_romanized(converted):
    out, _ = converted
    texts = [t for t in slide_texts(parts(out)["ppt/slides/slide1.xml"]) if t]
    assert "Kabushiki Gaisha" in texts   # title, split across two runs
    assert "Tōkyō" in texts
    assert "Gōkei" in texts              # table cell
    assert "Ōsaka" in texts             # grouped shape + body


# --- Reassembly (decision D1) ----------------------------------------------

def _romanize_slide_fragment(inner):
    blob = (
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="{ns}"><p:cSld><p:spTree>{inner}</p:spTree></p:cSld></p:sld>'
    ).format(ns=A[1:-1], inner=inner)
    return etree.fromstring(P._romanize_part(blob.encode(), dictionary.default()))


def test_word_split_midword_across_langs_reassembles_to_first_run():
    """マリオット split マリ(en-US)|オット(ja-JP) -> whole word in the first run.

    The runs differ only in lang and share identical visual formatting; the
    lang tag is itself wrong (Japanese text tagged en-US). Picking the first
    run's lang for the reassembled word changes nothing visible.
    """
    inner = (
        "<p:sp><p:txBody><a:bodyPr/><a:p>"
        '<a:r><a:rPr lang="en-US" b="1"><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></a:rPr><a:t>マリ</a:t></a:r>'
        '<a:r><a:rPr lang="ja-JP" b="1"><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></a:rPr><a:t>オット</a:t></a:r>'
        "</a:p></p:txBody></p:sp>"
    )
    root = _romanize_slide_fragment(inner)
    runs = root.findall(".//" + A + "r")
    assert [r.find(A + "t").text for r in runs] == ["Mariotto", None]
    # Both runs survive (sibling guard); the first run's visual formatting is intact.
    assert len(runs) == 2
    rpr = runs[0].find(A + "rPr")
    assert rpr.get("b") == "1"
    assert rpr.find(".//" + A + "srgbClr").get("val") == "FF0000"


def test_two_words_at_run_boundary_each_stay_in_their_run():
    inner = (
        "<p:sp><p:txBody><a:bodyPr/><a:p>"
        '<a:r><a:rPr lang="en-US"/><a:t>神戸</a:t></a:r>'
        '<a:r><a:rPr lang="ja-JP"/><a:t>マリオット</a:t></a:r>'
        "</a:p></p:txBody></p:sp>"
    )
    root = _romanize_slide_fragment(inner)
    texts = [r.find(A + "t").text for r in root.findall(".//" + A + "r")]
    assert texts == ["Kōbe", " Mariotto"]


# --- Sibling guard ----------------------------------------------------------

def test_line_break_and_field_survive(converted):
    out, _ = converted
    slide = etree.fromstring(parts(out)["ppt/slides/slide1.xml"])
    assert slide.find(".//" + A + "br") is not None, "a:br dropped"
    assert slide.find(".//" + A + "fld") is not None, "a:fld dropped"


def test_field_cached_value_not_romanized(converted):
    """The slide-number field's a:t ('1') is a boundary and must stay."""
    out, _ = converted
    slide = etree.fromstring(parts(out)["ppt/slides/slide1.xml"])
    fld = slide.find(".//" + A + "fld")
    assert fld.find(A + "t").text == "1"


def test_break_splits_reassembly_segment():
    """東京 <a:br/> 大阪 must not be romanized as one word across the break."""
    inner = (
        "<p:sp><p:txBody><a:bodyPr/><a:p>"
        '<a:r><a:rPr lang="ja-JP"/><a:t>東京</a:t></a:r><a:br/>'
        '<a:r><a:rPr lang="ja-JP"/><a:t>大阪</a:t></a:r>'
        "</a:p></p:txBody></p:sp>"
    )
    root = _romanize_slide_fragment(inner)
    texts = [t.text for t in root.iter(A + "t")]
    assert texts == ["Tōkyō", "Ōsaka"]


# --- Never touched ----------------------------------------------------------

def test_typeface_font_names_untouched(converted):
    out, _ = converted
    faces = {e.get("typeface") for e in etree.fromstring(parts(out)["ppt/slides/slide1.xml"]).iter(A + "latin")}
    assert "游ゴシック" in faces, "a Japanese font name was romanized"


def test_notes_are_romanized(converted):
    out, _ = converted
    assert slide_texts(parts(out)["ppt/notesSlides/notesSlide1.xml"]) == [
        "Watakushi wa Gakusei desu"
    ]


# --- Loud deferral notice (decision D4) ------------------------------------

def test_chart_is_deferred_and_reported(converted):
    out, result = converted
    # The chart's Japanese is left untouched...
    assert "売上" in parts(out)["ppt/charts/chart1.xml"].decode("utf-8")
    # ...but reported, not silently dropped.
    names = [n for n, _, _ in result.unconverted]
    assert "ppt/charts/chart1.xml" in names
    kind = next(k for n, k, _ in result.unconverted if n == "ppt/charts/chart1.xml")
    assert kind == "chart"


def test_conversion_is_pathlike(converted):
    out, result = converted
    import os

    assert os.fspath(result) == str(out)


def test_reopens_in_pptx(converted):
    out, _ = converted
    pytest.importorskip("pptx")
    from pptx import Presentation

    Presentation(str(out))


# --- CLI --------------------------------------------------------------------

def test_cli_converts_and_reports_notice(tmp_path, capsys):
    from romanizer import cli

    out = tmp_path / "out.pptx"
    assert cli.main(["convert", str(FIXTURE), str(out)]) == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "wrote" in captured.out
    # The chart notice goes to stderr.
    assert "NOT converted" in captured.err
    assert "chart1.xml" in captured.err


# --- Real decks (gitignored; skipped on a clean checkout) -------------------

@pytest.mark.parametrize("deck", REAL_DECKS)
def test_real_deck_preserves_untouched_parts(tmp_path, deck):
    if not deck.exists():
        pytest.skip("real deck not present: {}".format(deck.name))
    out = tmp_path / "out.pptx"
    P.convert(deck, out)
    before, after = parts(deck), parts(out)
    assert set(before) == set(after)
    import re

    for name in before:
        if re.match(r"ppt/(slides/slide|notesSlides/notesSlide)\d+\.xml$", name):
            continue
        assert before[name] == after[name], "re-serialized: {}".format(name)


def test_real_deck_reports_unconverted_charts(tmp_path):
    deck = SAMPLES / "expected" / "Romaji ppt.pptx"
    if not deck.exists():
        pytest.skip("real deck not present")
    out = tmp_path / "out.pptx"
    result = P.convert(deck, out)
    kinds = {k for _, k, _ in result.unconverted}
    assert "chart" in kinds
