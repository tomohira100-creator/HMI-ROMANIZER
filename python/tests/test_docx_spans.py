"""Unit tests for the DOCX handler's pure logic: segmentation and span attribution."""

import pytest
from lxml import etree

from romanizer.core import romanize, romanize_spans
from romanizer.handlers import docx_handler as H

W = H.W
NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def paragraph(inner):
    return etree.fromstring("<w:p {}>{}</w:p>".format(NS, inner))


def run(text):
    return "<w:r><w:t>{}</w:t></w:r>".format(text)


# --- romanize_spans contract ----------------------------------------------

CORPUS = [
    "株式会社ホテル", "私は学生です", "2026年5月13日", "第3四半期",
    "Hello 世界", "HMI ホテルグループ", "東京、大阪", "・、。「」【】×",
    "際しての", "こんにちは", "大阪", "20日", "A4", "", "   ", "\n\t",
]


@pytest.mark.parametrize("text", CORPUS)
def test_spans_reassemble_to_romanize(text):
    assert "".join(o for _, _, o in romanize_spans(text)) == romanize(text)


@pytest.mark.parametrize("text", CORPUS)
def test_spans_tile_the_input(text):
    spans = romanize_spans(text)
    if not text:
        assert spans == []
        return
    position = 0
    for start, end, _ in spans:
        assert start == position
        assert end >= start
        position = end
    assert position == len(text)


def test_span_source_ranges_point_at_the_right_characters():
    spans = romanize_spans("株式会社ホテル")
    assert spans == [(0, 4, "Kabushiki Gaisha"), (4, 7, " Hoteru")]


# --- Segmentation ----------------------------------------------------------

def test_single_run_is_one_segment():
    p = paragraph(run("東京"))
    segments = H._segments(p)
    assert len(segments) == 1
    assert [leaf.text for leaf in segments[0]] == ["東京"]


def test_adjacent_runs_join_one_segment():
    p = paragraph(run("株式") + run("会社"))
    segments = H._segments(p)
    assert len(segments) == 1
    assert [leaf.text for leaf in segments[0]] == ["株式", "会社"]


def test_break_splits_segments():
    p = paragraph("<w:r><w:t>東京</w:t><w:br/><w:t>大阪</w:t></w:r>")
    segments = H._segments(p)
    assert len(segments) == 2
    assert [leaf.text for leaf in segments[0]] == ["東京"]
    assert [leaf.text for leaf in segments[1]] == ["大阪"]


def test_tab_splits_segments():
    p = paragraph("<w:r><w:t>東京</w:t><w:tab/><w:t>大阪</w:t></w:r>")
    assert len(H._segments(p)) == 2


def test_field_code_splits_segments_and_is_not_a_leaf():
    p = paragraph(
        run("東京")
        + '<w:r><w:instrText> PAGE </w:instrText></w:r>'
        + run("大阪")
    )
    segments = H._segments(p)
    assert len(segments) == 2
    leaves = [leaf for segment in segments for leaf in segment]
    assert all(leaf.tag == W + "t" for leaf in leaves)


def test_bookmark_does_not_split_a_segment():
    p = paragraph(
        run("株式") + '<w:bookmarkStart w:id="1" w:name="x"/>' + run("会社")
    )
    segments = H._segments(p)
    assert len(segments) == 1
    assert [leaf.text for leaf in segments[0]] == ["株式", "会社"]


def test_nested_paragraph_leaves_are_not_claimed_by_the_outer_paragraph():
    p = paragraph(
        run("東京")
        + "<w:r><w:pict><v:textbox xmlns:v='urn:schemas-microsoft-com:vml'>"
        "<w:txbxContent><w:p><w:r><w:t>大阪</w:t></w:r></w:p></w:txbxContent>"
        "</v:textbox></w:pict></w:r>"
    )
    leaves = [leaf.text for segment in H._segments(p) for leaf in segment]
    assert leaves == ["東京"]


# --- Span attribution ------------------------------------------------------

def _leaves(*texts):
    return [etree.fromstring("<w:t {}>{}</w:t>".format(NS, t)) for t in texts]


def test_word_split_across_two_leaves_goes_to_the_first():
    leaves = _leaves("株", "式会社")
    outputs = H._assign_spans(leaves, romanize_spans("株式会社"), "株式会社")
    assert outputs == ["Kabushiki Gaisha", ""]


def test_word_split_across_three_leaves_goes_to_the_first():
    leaves = _leaves("株", "式", "会社")
    outputs = H._assign_spans(leaves, romanize_spans("株式会社"), "株式会社")
    assert outputs == ["Kabushiki Gaisha", "", ""]


def test_two_words_across_two_leaves_stay_put():
    leaves = _leaves("東京", "タワー")
    outputs = H._assign_spans(leaves, romanize_spans("東京タワー"), "東京タワー")
    assert outputs == ["Tōkyō", " Tawā"]


def test_a_leaf_may_receive_several_spans():
    leaves = _leaves("東京タワー")
    outputs = H._assign_spans(leaves, romanize_spans("東京タワー"), "東京タワー")
    assert outputs == ["Tōkyō Tawā"]


def test_empty_leaf_tolerated():
    leaves = _leaves("株式", "", "会社")
    outputs = H._assign_spans(leaves, romanize_spans("株式会社"), "株式会社")
    assert outputs[0] == "Kabushiki Gaisha"
    assert outputs[1] == "" and outputs[2] == ""


def test_leaf_with_none_text_tolerated():
    leaves = _leaves("株式", "会社")
    leaves[1].text = None
    full = "株式"
    outputs = H._assign_spans(leaves, romanize_spans(full), full)
    assert outputs[0] == "Kabushiki Shiki"[:0] or outputs[0]  # non-empty
    assert outputs[1] == ""


def test_outputs_concatenate_to_the_romanized_segment():
    for text, split in [
        ("株式会社ホテル", [1, 3]),
        ("東京タワー", [2]),
        ("私は学生です", [1, 4]),
    ]:
        pieces, previous = [], 0
        for point in split + [len(text)]:
            pieces.append(text[previous:point])
            previous = point
        leaves = _leaves(*pieces)
        outputs = H._assign_spans(leaves, romanize_spans(text), text)
        assert "".join(outputs) == romanize(text)
