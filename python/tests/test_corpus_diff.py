"""Tests for the corpus diff harness and its reference-not-oracle classifier."""

import subprocess
import sys
from pathlib import Path

import pytest

from romanizer import corpus_diff as C

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "samples"
BUILDER = REPO_ROOT / "python" / "tests" / "fixtures" / "build_fixtures.py"
FIXTURE = SAMPLES / "12_spreadsheet.xlsx"


# --- classify: the reference-not-oracle distinction -------------------------

def test_identical():
    assert C.classify("Tōkyō", "Tōkyō") == "identical"


def test_macron_only_is_not_a_defect():
    # The human dropped a macron; our Modified Hepburn is more correct (D4).
    assert C.classify("Hyōshi", "Hyoshi") == "macron-only"
    assert C.classify("Kōtsū", "Kotsu") == "macron-only"


def test_spacing_and_case():
    assert C.classify("Gyōsha Keihi", "gyōsha keihi") == "spacing-case"
    assert C.classify("Kabushikigaisha", "Kabushiki Gaisha") == "spacing-case"


def test_substantive_is_a_real_divergence():
    # 数量 space-broken to Kazu Ryō vs the correct Sūryō.
    assert C.classify("Kazu Ryō", "Sūryō") == "substantive"
    assert C.classify("Mein Rūmu", "Main Room") == "substantive"


def test_strip_macrons():
    assert C.strip_macrons("Kōtsū-hi") == "Kotsu-hi"
    assert C.strip_macrons("Āīūēō") == "Aiueo"  # replaces macrons, keeps other chars


# --- compare_xlsx on the synthetic fixture ---------------------------------

@pytest.fixture(scope="module", autouse=True)
def ensure_fixture():
    if not FIXTURE.exists():
        subprocess.run([sys.executable, str(BUILDER)], check=True)


def test_compare_against_self_is_all_identical(tmp_path):
    """Romanizing the fixture and diffing against our own output: no divergence."""
    from romanizer.handlers import xlsx_handler

    out = tmp_path / "out.xlsx"
    xlsx_handler.convert(FIXTURE, out)
    divergences, summary = C.compare_xlsx(FIXTURE, out)
    assert divergences == []
    assert summary["substantive"] == 0
    # Every Japanese source string matched our own output.
    assert summary["identical"] == 4


def test_compare_detects_a_planted_divergence(tmp_path):
    """A reference that differs substantively is reported and ranked."""
    from lxml import etree
    from romanizer.handlers import xlsx_handler
    from romanizer.ooxml_parts import Package

    out = tmp_path / "out.xlsx"
    xlsx_handler.convert(FIXTURE, out)

    # Corrupt one shared string in a copy of the output to simulate a human
    # choosing a different romanization.
    pkg = Package.read(out)
    root = etree.fromstring(pkg.read_part("xl/sharedStrings.xml"))
    for t in root.iter(C.M + "t"):
        if t.text == "Tōkyō":
            t.text = "Tokyo Different"
    pkg.replace("xl/sharedStrings.xml", etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))
    planted = tmp_path / "planted.xlsx"
    pkg.write(planted)

    divergences, summary = C.compare_xlsx(FIXTURE, planted)
    assert summary["substantive"] == 1
    assert divergences[0].source == "東京"
    assert divergences[0].ours == "Tōkyō"
    assert divergences[0].theirs == "Tokyo Different"


def test_length_mismatch_raises(tmp_path):
    from lxml import etree
    from romanizer.ooxml_parts import Package

    pkg = Package.read(FIXTURE)
    root = etree.fromstring(pkg.read_part("xl/sharedStrings.xml"))
    root.append(etree.SubElement(root, C.M + "si"))  # extra <si>
    pkg.replace("xl/sharedStrings.xml", etree.tostring(root))
    longer = tmp_path / "longer.xlsx"
    pkg.write(longer)
    with pytest.raises(ValueError, match="align by index"):
        C.compare_xlsx(FIXTURE, longer)


def test_compare_pptx_against_our_own_output_is_identical(tmp_path):
    """A hand-romanized deck can run through the harness; against our own
    output there is no divergence."""
    from romanizer.handlers import pptx_handler

    out = tmp_path / "out.pptx"
    pptx_handler.convert(SAMPLES / "13_slides.pptx", out)
    divergences, summary = C.compare_pptx(SAMPLES / "13_slides.pptx", out)
    assert divergences == []
    assert summary["substantive"] == 0
    assert summary["identical"] > 0


def test_report_separates_macron_from_substantive():
    divergences = [
        C.Divergence("東京", "Tōkyō", "Tokyo", "macron-only", 5),
        C.Divergence("数量", "Kazu Ryō", "Sūryō", "substantive", 3),
    ]
    summary = {"identical": 10, "macron-only": 1, "spacing-case": 0, "substantive": 1}
    report = C.format_report(divergences, summary)
    # Substantive ranks first; macron-only is labelled as a human shortcut.
    assert report.index("substantive") < report.index("macron-only")
    assert "not a" in report and "defect" in report
