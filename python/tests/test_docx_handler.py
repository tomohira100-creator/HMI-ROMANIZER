"""DOCX handler integration tests.

Three complementary assertions, per the strategy agreed in the Phase 2 plan:

  (a) untouched parts are byte-identical
  (b) edited parts are structurally isomorphic, text aside
  (c) the text is correct

Byte comparison of a whole output against a golden file is deliberately not
used: it breaks on any lxml version bump and reports that something moved
without saying what.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from romanizer import dictionary
from romanizer.handlers import docx_handler as H

W = H.W
XML_SPACE = H.XML_SPACE

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = REPO_ROOT / "samples"
BUILDER = REPO_ROOT / "python" / "tests" / "fixtures" / "build_fixtures.py"

LISTS = SAMPLES / "05_lists.docx"
COMPOSITE = SAMPLES / "10_composite.docx"
FRAGMENTED = SAMPLES / "11_fragmented.docx"

#: Real HMI documents. Gitignored, so absent on a clean checkout.
REAL_DOCX = [
    "比良社長 春の叙勲 受章のご報告 2.docx",
    "India Recruitment Memo.docx",
    "BOD May 2025 Analysis.docx",
    "Meeting Report_ Welcome Dinner Amit Kumar.docx",
    "JPX株式および先物取引に関する高度な議論と分析の詳細報告書.docx",
    "1_20_2025 議事録 リブランド人事計画会議Meeting Minutes Rebrand Resource Planning Meeting.docx",
]


@pytest.fixture(scope="module", autouse=True)
def ensure_fixtures():
    if not all(p.exists() for p in (LISTS, COMPOSITE, FRAGMENTED)):
        subprocess.run([sys.executable, str(BUILDER)], check=True)


def parts(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def texts(blob):
    return [node.text for node in etree.fromstring(blob).iter(W + "t")]


def skeleton(blob):
    """(tag, attributes) for every element, in document order.

    Text content is excluded, and xml:space is excluded because the handler
    legitimately adds it when new text has significant whitespace. Everything
    else -- every w:rPr, w:br, w:tbl, w:bookmarkStart, every attribute value
    and its ordering -- must survive untouched.
    """
    out = []
    for element in etree.fromstring(blob).iter():
        attrib = {k: v for k, v in element.attrib.items() if k != XML_SPACE}
        out.append((element.tag, tuple(sorted(attrib.items()))))
    return out


def assert_preserved(source, output, edited):
    """(a) untouched parts byte-identical, (b) edited parts isomorphic."""
    before, after = parts(source), parts(output)
    assert set(before) == set(after), "part set changed"

    for name in sorted(before):
        if name in edited:
            assert skeleton(before[name]) == skeleton(after[name]), (
                "{} changed structurally".format(name)
            )
        else:
            assert before[name] == after[name], "{} was re-serialized".format(name)


# --- 11_fragmented: the reassembly path ------------------------------------
#
# Artificial fragmentation. See build_fixtures.build_11. This tests the
# handler's reassembly logic, not Word's splitting behaviour.

@pytest.fixture(scope="module")
def fragmented_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("frag") / "out.docx"
    H.convert(FRAGMENTED, out)
    return out


def paragraph_runs(path, index):
    root = etree.fromstring(parts(path)["word/document.xml"])
    p = list(root.iter(W + "p"))[index]
    result = []
    for r in p.iter(W + "r"):
        text = "".join(t.text or "" for t in r.findall(W + "t"))
        rpr = r.find(W + "rPr")
        sig = tuple(etree.QName(c).localname for c in rpr) if rpr is not None else ()
        result.append((sig, text))
    return result


def test_identical_format_split_reassembles(fragmented_out):
    """際 + しての. Per-run romanization would give 'Sai' + 'Shite no'.

    The word 際して straddles both runs, so its whole romanization lands in the
    first; の begins in the second and stays there.
    """
    assert paragraph_runs(fragmented_out, 0) == [((), "Saishite"), ((), " no")]


def test_differing_format_split_first_run_wins(fragmented_out):
    """株(bold) + 式会社. D2: the whole word takes the first run's bold."""
    assert paragraph_runs(fragmented_out, 1) == [(("b",), "Kabushiki Gaisha"), ((), "")]


def test_three_way_split_with_mixed_formatting(fragmented_out):
    assert paragraph_runs(fragmented_out, 2) == [
        (("b",), "Tōkyō"), (("color",), ""), ((), " Tawā"),
    ]


def test_romanization_never_crosses_a_line_break(fragmented_out):
    root = etree.fromstring(parts(fragmented_out)["word/document.xml"])
    p = list(root.iter(W + "p"))[3]
    children = [etree.QName(c).localname for r in p.iter(W + "r") for c in r]
    assert children == ["t", "br", "t"]
    assert [c.text for r in p.iter(W + "r") for c in r if c.tag == W + "t"] == [
        "Tōkyō", "Ōsaka",
    ]


def test_bookmark_between_runs_survives_a_split_word(fragmented_out):
    root = etree.fromstring(parts(fragmented_out)["word/document.xml"])
    assert len(root.findall(".//" + W + "bookmarkStart")) == 1
    assert paragraph_runs(fragmented_out, 4) == [((), "Kabushiki Gaisha"), ((), "")]


def test_split_inside_a_table_cell(fragmented_out):
    root = etree.fromstring(parts(fragmented_out)["word/document.xml"])
    assert len(root.findall(".//" + W + "tbl")) == 1
    cell = root.find(".//" + W + "tbl//" + W + "tc")
    # An emptied w:t serializes as <w:t/> and reads back as None, not "".
    assert [t.text or "" for t in cell.iter(W + "t")] == ["Kabushiki Gaisha", ""]


def test_field_code_is_never_romanized(fragmented_out):
    root = etree.fromstring(parts(fragmented_out)["word/document.xml"])
    assert [e.text for e in root.iter(W + "instrText")] == [" PAGE "]


def test_every_character_in_its_own_run(fragmented_out):
    assert paragraph_runs(fragmented_out, 7) == [
        ((), "Kabushiki Gaisha"), ((), ""), ((), ""), ((), ""),
    ]


def test_no_run_is_ever_deleted(fragmented_out):
    before = etree.fromstring(parts(FRAGMENTED)["word/document.xml"])
    after = etree.fromstring(parts(fragmented_out)["word/document.xml"])
    for tag in ("r", "rPr", "t", "br", "bookmarkStart", "bookmarkEnd", "tbl", "tc"):
        assert len(list(before.iter(W + tag))) == len(list(after.iter(W + tag))), tag


def test_fragmented_structure_preserved(fragmented_out):
    assert_preserved(FRAGMENTED, fragmented_out, edited={"word/document.xml"})


# --- 10_composite: every construct -----------------------------------------

@pytest.fixture(scope="module")
def composite_out(tmp_path_factory):
    out = tmp_path_factory.mktemp("comp") / "out.docx"
    H.convert(COMPOSITE, out)
    return out


def test_composite_untouched_parts_are_byte_identical(composite_out):
    assert_preserved(
        COMPOSITE,
        composite_out,
        edited={
            "word/document.xml", "word/header1.xml", "word/footer1.xml",
            "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml",
        },
    )


def test_embedded_image_is_byte_identical(composite_out):
    assert parts(COMPOSITE)["word/media/image1.png"] == parts(composite_out)["word/media/image1.png"]


def test_numbering_is_untouched_pending_d7(composite_out):
    assert parts(COMPOSITE)["word/numbering.xml"] == parts(composite_out)["word/numbering.xml"]


def test_headers_footnotes_endnotes_comments_are_romanized(composite_out):
    after = parts(composite_out)
    assert texts(after["word/header1.xml"]) == ["Kabushiki Gaisha"]
    assert texts(after["word/footnotes.xml"]) == ["Ōsaka"]
    assert texts(after["word/endnotes.xml"]) == ["Tōkyō"]
    assert texts(after["word/comments.xml"]) == ["Kabushiki Gaisha"]


def test_text_box_is_romanized(composite_out):
    root = etree.fromstring(parts(composite_out)["word/document.xml"])
    box = root.find(".//" + W + "txbxContent")
    assert [t.text for t in box.iter(W + "t")] == ["Kabushiki Gaisha"]


def test_table_cells_are_romanized(composite_out):
    root = etree.fromstring(parts(composite_out)["word/document.xml"])
    cells = [
        [t.text for t in tc.iter(W + "t")] for tc in root.iter(W + "tc")
    ]
    assert ["Tōkyō"] in cells
    assert ["Ōsaka"] in cells


def test_empty_text_node_survives(composite_out):
    """The vMerge continuation cell. Must not crash on NoneType."""
    root = etree.fromstring(parts(composite_out)["word/document.xml"])
    assert any((t.text or "") == "" for t in root.iter(W + "t"))


def test_hyperlink_display_text_is_romanized(composite_out):
    root = etree.fromstring(parts(composite_out)["word/document.xml"])
    link = root.find(".//" + W + "hyperlink")
    assert [t.text for t in link.iter(W + "t")] == ["Ōsaka"]


def test_composite_field_result_survives(composite_out):
    root = etree.fromstring(parts(composite_out)["word/document.xml"])
    assert root.find(".//" + W + "fldSimple").get(W + "instr") == " PAGE "


# --- 05_lists ---------------------------------------------------------------

def test_lists_converts(tmp_path):
    out = tmp_path / "out.docx"
    H.convert(LISTS, out)
    assert texts(parts(out)["word/document.xml"]) == [
        "Tōkyō", "Kabushiki Gaisha", "Ōsaka", "Dai 3 Shihanki",
        "2026 Nen 5 Gatsu 13 Nichi", "Watakushi wa Gakusei desu", "Tōkyō",
    ]


def test_lists_numbering_state_preserved(tmp_path):
    out = tmp_path / "out.docx"
    H.convert(LISTS, out)
    assert_preserved(LISTS, out, edited={"word/document.xml"})


# --- Decision D3: refusal ---------------------------------------------------

def _inject(source, destination, part, snippet):
    before = parts(source)
    blob = before[part].decode("utf-8").replace("</w:body>", snippet + "</w:body>")
    before[part] = blob.encode("utf-8")
    with zipfile.ZipFile(destination, "w") as archive:
        for name, data in before.items():
            archive.writestr(name, data)


REVISION_SNIPPETS = {
    "ins": '<w:p><w:ins w:id="1" w:author="A"><w:r><w:t>x</w:t></w:r></w:ins></w:p>',
    "del": '<w:p><w:del w:id="1" w:author="A"><w:r><w:delText>x</w:delText></w:r></w:del></w:p>',
    "rPrChange": '<w:p><w:r><w:rPr><w:rPrChange w:id="1" w:author="A"><w:rPr/></w:rPrChange></w:rPr><w:t>x</w:t></w:r></w:p>',
    "pPrChange": '<w:p><w:pPr><w:pPrChange w:id="1" w:author="A"><w:pPr/></w:pPrChange></w:pPr></w:p>',
    "moveFrom": '<w:p><w:moveFrom w:id="1" w:author="A"><w:r><w:t>x</w:t></w:r></w:moveFrom></w:p>',
    "moveTo": '<w:p><w:moveTo w:id="1" w:author="A"><w:r><w:t>x</w:t></w:r></w:moveTo></w:p>',
    "tblPrChange": '<w:tbl><w:tblPr><w:tblPrChange w:id="1" w:author="A"><w:tblPr/></w:tblPrChange></w:tblPr></w:tbl>',
    "sectPrChange": '<w:p><w:pPr><w:sectPr><w:sectPrChange w:id="1" w:author="A"><w:sectPr/></w:sectPrChange></w:sectPr></w:pPr></w:p>',
}


@pytest.mark.parametrize("tag", sorted(REVISION_SNIPPETS))
def test_revision_markup_is_refused(tmp_path, tag):
    source = tmp_path / "rev.docx"
    _inject(FRAGMENTED, source, "word/document.xml", REVISION_SNIPPETS[tag])
    out = tmp_path / "out.docx"
    with pytest.raises(H.RevisionMarkupError) as exc:
        H.convert(source, out)
    assert tag in exc.value.tags
    assert not out.exists(), "refusal must not leave an output file"


def test_revision_in_a_header_is_also_refused(tmp_path):
    """Refusal scans every part, not only document.xml."""
    source = tmp_path / "rev.docx"
    before = parts(COMPOSITE)
    before["word/header1.xml"] = (
        before["word/header1.xml"].decode()
        .replace("</w:hdr>", REVISION_SNIPPETS["ins"] + "</w:hdr>")
        .encode()
    )
    with zipfile.ZipFile(source, "w") as archive:
        for name, data in before.items():
            archive.writestr(name, data)
    out = tmp_path / "out.docx"
    with pytest.raises(H.RevisionMarkupError):
        H.convert(source, out)
    assert not out.exists()


def test_refusal_message_is_actionable(tmp_path):
    source = tmp_path / "rev.docx"
    _inject(FRAGMENTED, source, "word/document.xml", REVISION_SNIPPETS["ins"])
    with pytest.raises(H.RevisionMarkupError) as exc:
        H.convert(source, tmp_path / "out.docx")
    message = str(exc.value)
    assert "rev.docx" in message
    assert "Review" in message and "Accept All Changes" in message
    assert "Traceback" not in message


def test_no_partial_file_is_left_behind(tmp_path):
    source = tmp_path / "rev.docx"
    _inject(FRAGMENTED, source, "word/document.xml", REVISION_SNIPPETS["del"])
    out = tmp_path / "out.docx"
    with pytest.raises(H.RevisionMarkupError):
        H.convert(source, out)
    assert list(tmp_path.glob("*.partial")) == []


def test_clean_document_is_not_refused(tmp_path):
    assert H.find_revision_markup(H.Package.read(COMPOSITE)) == []


# --- Custom dictionary passes through --------------------------------------

def test_handler_honours_a_custom_dictionary(tmp_path):
    import json

    (tmp_path / "custom_terms.json").write_text(
        json.dumps({"東京": "TOKYO"}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "abbreviations.json").write_text('{"abbreviations": []}', encoding="utf-8")
    dic = dictionary.load(tmp_path)
    out = tmp_path / "out.docx"
    H.convert(LISTS, out, dic)
    assert "TOKYO" in texts(parts(out)["word/document.xml"])


# --- Idempotence ------------------------------------------------------------

def test_converting_twice_is_stable(tmp_path):
    once, twice = tmp_path / "a.docx", tmp_path / "b.docx"
    H.convert(COMPOSITE, once)
    H.convert(once, twice)
    assert texts(parts(once)["word/document.xml"]) == texts(parts(twice)["word/document.xml"])


# --- CLI --------------------------------------------------------------------

def test_cli_convert_writes_output(tmp_path, capsys):
    from romanizer import cli

    out = tmp_path / "out.docx"
    assert cli.main(["convert", str(LISTS), str(out)]) == cli.EXIT_OK
    assert out.exists()
    assert "wrote" in capsys.readouterr().out


def test_cli_convert_refusal_exit_code_is_two(tmp_path, capsys):
    from romanizer import cli

    source = tmp_path / "rev.docx"
    _inject(FRAGMENTED, source, "word/document.xml", REVISION_SNIPPETS["ins"])
    out = tmp_path / "out.docx"
    assert cli.main(["convert", str(source), str(out)]) == cli.EXIT_REFUSED
    assert not out.exists()
    error = capsys.readouterr().err
    assert "Accept All Changes" in error
    assert "Traceback" not in error


def test_cli_convert_rejects_unsupported_type(tmp_path, capsys):
    from romanizer import cli

    source = tmp_path / "x.pdf"
    source.write_bytes(b"%PDF-1.4")
    assert cli.main(["convert", str(source), str(tmp_path / "o.pdf")]) == cli.EXIT_ERROR
    assert "unsupported file type" in capsys.readouterr().err


def test_cli_convert_missing_file(tmp_path, capsys):
    from romanizer import cli

    code = cli.main(["convert", str(tmp_path / "nope.docx"), str(tmp_path / "o.docx")])
    assert code == cli.EXIT_ERROR
    assert "no such file" in capsys.readouterr().err


# --- Real HMI documents (gitignored; skipped on a clean checkout) -----------

@pytest.mark.parametrize("name", REAL_DOCX)
def test_real_document_converts_without_structural_damage(tmp_path, name):
    source = SAMPLES / name
    if not source.exists():
        pytest.skip("real sample not present: {}".format(name))
    out = tmp_path / "out.docx"
    H.convert(source, out)

    edited = {n for n in parts(source) if H.TEXT_PARTS.match(n)}
    assert_preserved(source, out, edited=edited)

    # No Japanese should remain in the parts we edited.
    for name_ in edited:
        for value in texts(parts(out)[name_]):
            if value:
                assert not H._JAPANESE.search(value), (name_, value)


def test_real_document_preserves_the_one_real_split(tmp_path):
    source = SAMPLES / "比良社長 春の叙勲 受章のご報告 2.docx"
    if not source.exists():
        pytest.skip("real sample not present")
    out = tmp_path / "out.docx"
    H.convert(source, out)
    root = etree.fromstring(parts(out)["word/document.xml"])
    title = list(root.iter(W + "p"))[7]
    joined = "".join(t.text or "" for t in title.iter(W + "t"))
    # Word split 際しての as 際 + しての across two identically formatted runs.
    assert "Saishite no" in joined, joined
    # Per-run romanization would have produced this instead.
    assert "SaiShite" not in joined


def test_real_document_image_is_byte_identical(tmp_path):
    source = SAMPLES / "比良社長 春の叙勲 受章のご報告 2.docx"
    if not source.exists():
        pytest.skip("real sample not present")
    out = tmp_path / "out.docx"
    H.convert(source, out)
    assert parts(source)["word/media/image1.jpeg"] == parts(out)["word/media/image1.jpeg"]
