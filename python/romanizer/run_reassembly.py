"""Shared run-reassembly for OOXML text, used by the DOCX and PPTX handlers.

Word and PowerPoint both split a logical word across several runs -- `w:r`
holding `w:t` in DOCX, `a:r` holding `a:t` in PPTX -- for reasons unrelated to
formatting: spell-check state, a retyped title, a paste from another file. A
word straddling two runs must be romanized as one string, or half-words reach
MeCab.

The algorithm is identical for both formats and only the element names differ:

  1. Split a paragraph's text leaves into segments at hard boundaries (a line
     break, a tab, a field), so romanization never forms a word across one.
  2. Concatenate a segment's leaves, romanize with `core.romanize_spans`.
  3. Attribute each output span to the leaf that owns its first source
     character -- "first-run-wins". A straddling word's whole romanization
     lands in the first run; later runs it covered receive nothing and keep
     their formatting with empty text.

Measured against real corpora: in DOCX one word in 51,858 tokens was split,
both runs identically formatted; in PPTX 31.8% of paragraphs are multi-run.
The path is rare in Word and common in PowerPoint, so it lives here once.
"""


class RunModel:
    """The namespace-specific tags one format uses for paragraphs and runs."""

    def __init__(self, para_tag, text_tag, boundary_tags, space_attr=None):
        self.para_tag = para_tag
        self.text_tag = text_tag
        self.boundary_tags = frozenset(boundary_tags)
        # xml:space, set on a leaf whose romanized text has significant leading
        # or trailing whitespace so it survives the round-trip. Optional.
        self.space_attr = space_attr


def _direct_children_in_order(paragraph, para_tag):
    """Walk a paragraph's subtree in document order, not descending into a
    nested paragraph.

    A text box (DOCX) or a nested shape (PPTX) contains its own paragraphs;
    those belong to the inner paragraph and are visited when the caller
    iterates over every paragraph in the part.
    """
    for child in paragraph:
        if child.tag == para_tag:
            continue
        yield child
        for descendant in _direct_children_in_order(child, para_tag):
            yield descendant


def segments(paragraph, model):
    """Split a paragraph's text leaves into runs of text romanizable as one
    string. Boundaries fall at line breaks, tabs and fields."""
    result = []
    current = []
    for element in _direct_children_in_order(paragraph, model.para_tag):
        if element.tag in model.boundary_tags:
            if current:
                result.append(current)
                current = []
            continue
        if element.tag == model.text_tag:
            current.append(element)
    if current:
        result.append(current)
    return result


def assign_spans(leaves, spans):
    """Attribute each output span to the leaf owning its first source character.

    First-run-wins. Namespace-independent: it reads only each leaf's `.text`.
    """
    owner = []
    for index, leaf in enumerate(leaves):
        owner.extend([index] * len(leaf.text or ""))

    outputs = [""] * len(leaves)
    for start, _end, output in spans:
        if not output:
            continue
        index = owner[start] if start < len(owner) else len(leaves) - 1
        outputs[index] += output
    return outputs


def romanize_paragraph(paragraph, dic, model, romanize_spans, japanese_re):
    """Romanize one paragraph's text in place, reassembling split words."""
    for leaves in segments(paragraph, model):
        full = "".join(leaf.text or "" for leaf in leaves)
        if not full or not japanese_re.search(full):
            # Nothing to romanize. Leave the leaves untouched rather than
            # rewriting identical text, so xml:space and entity forms survive.
            continue

        outputs = assign_spans(leaves, romanize_spans(full, dic))

        for leaf, text in zip(leaves, outputs):
            leaf.text = text
            # A leaf may legitimately end up empty: its word was absorbed by an
            # earlier run under first-run-wins. NEVER delete the leaf or its
            # run, and never prune "empty" siblings.
            #
            # This is the point of temptation -- a maintainer sees empty runs
            # and wants to clean them up. Do not. Runs are not the only thing
            # in a paragraph: in DOCX, w:bookmarkStart / w:bookmarkEnd /
            # w:commentRangeStart / w:footnoteReference / w:br sit between runs
            # (real HMI documents carry up to 48 bookmarks each). In PPTX, an
            # a:br (line break) and a:fld (slide-number / date field) are
            # siblings inside the paragraph; pruning an emptied run or its
            # neighbours drops the line break or the field with it. No
            # synthetic fixture would catch that loss. An empty text leaf is
            # valid OOXML and costs nothing.
            if model.space_attr is not None and text != text.strip():
                leaf.set(model.space_attr, "preserve")
