"""Deterministic synthesis of the DOCX fixtures ROMANIZER can build for itself.

Produces samples/05_lists.docx and samples/10_composite.docx. Every other
sample (01-04, 06-09) must come from Microsoft Word, and the real board paper
never enters this repository at all.

    python python/tests/fixtures/build_fixtures.py

WHAT THESE FIXTURES DO NOT PROVE
--------------------------------
Every Japanese phrase below is written as a single <w:t>. Word does not do
this. Word splits a logical word across several <w:r> runs for reasons that
have nothing to do with formatting -- spell-check state, revision bookkeeping,
proofing language, rsid tracking -- so that 株式会社 routinely arrives as three
runs with identical formatting.

Therefore 10_composite.docx proves that the constructs compose under
ARTIFICIAL conditions: clean run boundaries the handler never has to reassemble.
A green test suite over these fixtures is NOT a guarantee about real documents.
The split-run redistribution path, which is the hardest part of the DOCX
handler, is barely exercised here.

Only two things test that path honestly:
  - samples/02_formatting.docx, produced by Word, where Word chose the splits
  - the real board paper, run locally and never committed

Treat a pass here as a necessary condition, not a sufficient one.

Japanese content is drawn from the Phase 1 test corpus (株式会社, 東京, 大阪,
2026年5月13日, 第3四半期, 私は学生です) rather than invented. If a romanization
is wrong it should be wrong in a way already characterised by the Phase 1
suite, not a new mystery.
"""

import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = REPO_ROOT / "samples"

NS = " ".join(
    [
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"',
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"',
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"',
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"',
        'xmlns:v="urn:schemas-microsoft-com:vml"',
        'xmlns:w10="urn:schemas-microsoft-com:office:word"',
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"',
    ]
)

DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

RELS_NS = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
CT_NS = 'xmlns="http://schemas.openxmlformats.org/package/2006/content-types"'
REL_BASE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def para(text, style=None, num=None):
    ppr = ""
    if style or num is not None:
        parts = []
        if style:
            parts.append('<w:pStyle w:val="{}"/>'.format(style))
        if num is not None:
            num_id, level = num
            parts.append(
                '<w:numPr><w:ilvl w:val="{}"/><w:numId w:val="{}"/></w:numPr>'.format(
                    level, num_id
                )
            )
        ppr = "<w:pPr>{}</w:pPr>".format("".join(parts))
    return "<w:p>{}<w:r><w:t xml:space=\"preserve\">{}</w:t></w:r></w:p>".format(ppr, text)


def minimal_styles():
    return (
        DECL
        + '<w:styles {}><w:docDefaults><w:rPrDefault><w:rPr>'
        '<w:rFonts w:ascii="Yu Mincho" w:eastAsia="Yu Mincho"/>'
        '<w:sz w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        "<w:name w:val=\"Normal\"/></w:style>"
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        "<w:name w:val=\"heading 1\"/><w:rPr><w:b/></w:rPr></w:style>"
        "</w:styles>".format(NS)
    )


def minimal_settings():
    return DECL + "<w:settings {}><w:zoom w:percent=\"100\"/></w:settings>".format(NS)


def content_types(overrides, defaults=None):
    defaults = defaults or []
    base = [
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ] + defaults
    body = "".join(base) + "".join(overrides)
    return DECL + "<Types {}>{}</Types>".format(CT_NS, body)


def package_rels():
    return DECL + (
        "<Relationships {}>"
        '<Relationship Id="rId1" Type="{}/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    ).format(RELS_NS, REL_BASE.rsplit("/", 1)[0] + "/relationships")


def _rel(rid, kind, target, mode=None):
    extra = ' TargetMode="{}"'.format(mode) if mode else ""
    return '<Relationship Id="{}" Type="{}/{}" Target="{}"{}/>'.format(
        rid, REL_BASE, kind, target, extra
    )


def document_rels(rels):
    return DECL + "<Relationships {}>{}</Relationships>".format(RELS_NS, "".join(rels))


def tiny_png():
    """A 4x4 opaque red PNG, built without Pillow so the fixture has no deps."""
    width = height = 4
    raw = b"".join(b"\x00" + b"\xd0\x21\x21" * width for _ in range(height))

    def chunk(tag, data):
        payload = tag + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


# A fixed timestamp. Without it ZipFile stamps wall-clock time and two builds
# of the same fixture differ byte for byte, which would make the committed
# samples churn and defeat any byte-comparison test over them.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def write_docx(path, parts):
    path.parent.mkdir(parents=True, exist_ok=True)

    def entry(name):
        info = ZipInfo(name, date_time=FIXED_TIMESTAMP)
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        return info

    with ZipFile(path, "w") as archive:
        # [Content_Types].xml must be written first.
        archive.writestr(entry("[Content_Types].xml"), parts.pop("[Content_Types].xml"))
        for name, blob in parts.items():
            archive.writestr(entry(name), blob)


# --- 05_lists.docx ---------------------------------------------------------
#
# Three nesting depths of numbered list, plus a bulleted list. The numbering
# format itself carries Japanese literal text (第%1章, %2項). Romanizing
# numbering.xml is deferred work under decision D7; the fixture exists now so
# that the day someone implements it, the xfail test flips on its own.

def numbering_xml():
    levels = [
        ('0', "decimal", "第%1章", "360"),
        ('1', "decimal", "%2項", "720"),
        ('2', "decimal", "%3.", "1080"),
    ]
    lvl_xml = "".join(
        '<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/>'
        '<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
        '<w:pPr><w:ind w:left="{ind}"/></w:pPr></w:lvl>'.format(
            ilvl=ilvl, fmt=fmt, text=text, ind=ind
        )
        for ilvl, fmt, text, ind in levels
    )
    bullet = (
        '<w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/>'
        '<w:lvlText w:val="&#8226;"/><w:lvlJc w:val="left"/></w:lvl>'
    )
    return DECL + (
        "<w:numbering {ns}>"
        '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="multilevel"/>{lvls}</w:abstractNum>'
        '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/>{bul}</w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
        "</w:numbering>"
    ).format(ns=NS, lvls=lvl_xml, bul=bullet)


def build_05():
    body = "".join(
        [
            para("東京", style="Heading1"),
            para("株式会社", num=(1, 0)),
            para("大阪", num=(1, 1)),
            para("第3四半期", num=(1, 2)),
            para("2026年5月13日", num=(1, 1)),
            para("私は学生です", num=(2, 0)),
            para("東京", num=(2, 0)),
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>',
        ]
    )
    document = DECL + "<w:document {}><w:body>{}</w:body></w:document>".format(NS, body)

    parts = {
        "[Content_Types].xml": content_types(
            [
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
                '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
                '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>',
                '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>',
            ]
        ),
        "_rels/.rels": package_rels(),
        "word/document.xml": document,
        "word/_rels/document.xml.rels": document_rels(
            [
                _rel("rId1", "styles", "styles.xml"),
                _rel("rId2", "numbering", "numbering.xml"),
                _rel("rId3", "settings", "settings.xml"),
            ]
        ),
        "word/styles.xml": minimal_styles(),
        "word/numbering.xml": numbering_xml(),
        "word/settings.xml": minimal_settings(),
    }
    write_docx(SAMPLES / "05_lists.docx", parts)


# --- 10_composite.docx -----------------------------------------------------
#
# Headers, footers, a merged-cell table, nested lists, an embedded image, a
# VML text box, comments, footnotes, endnotes, a hyperlink, a bookmark and a
# PAGE field. No tracked changes: decision D3 refuses those, and this file
# must convert.

def table_xml():
    def cell(text, span=None, vmerge=None):
        props = []
        if span:
            props.append('<w:gridSpan w:val="{}"/>'.format(span))
        if vmerge:
            props.append(
                '<w:vMerge w:val="restart"/>' if vmerge == "restart" else "<w:vMerge/>"
            )
        tc_pr = "<w:tcPr>{}</w:tcPr>".format("".join(props)) if props else ""
        return "<w:tc>{}{}</w:tc>".format(tc_pr, para(text))

    return (
        '<w:tbl><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4"/></w:tblBorders></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/></w:tblGrid>'
        "<w:tr>{}</w:tr>"
        "<w:tr>{}{}</w:tr>"
        "<w:tr>{}{}</w:tr>"
        "</w:tbl>"
    ).format(
        cell("東京", span=2),
        cell("大阪", vmerge="restart"),
        cell("第3四半期"),
        cell("", vmerge="continue"),
        # A manual line break inside a cell.
        '<w:tc>{}</w:tc>'.format(
            '<w:p><w:r><w:t>株式会社</w:t><w:br/><w:t>2026年5月13日</w:t></w:r></w:p>'
        ),
    )


def image_paragraph():
    emu = 4 * 9525
    return (
        "<w:p><w:r><w:drawing>"
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        '<wp:extent cx="{emu}" cy="{emu}"/>'
        '<wp:docPr id="1" name="Picture 1"/>'
        "<a:graphic><a:graphicData "
        'uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        "<pic:pic><pic:nvPicPr><pic:cNvPr id=\"0\" name=\"image1.png\"/>"
        "<pic:cNvPicPr/></pic:nvPicPr>"
        '<pic:blipFill><a:blip r:embed="rIdImg"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{emu}" cy="{emu}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline>"
        "</w:drawing></w:r></w:p>"
    ).format(emu=emu)


def textbox_paragraph():
    return (
        "<w:p><w:r><w:pict>"
        '<v:shape id="tb1" type="#_x0000_t202" style="width:200pt;height:40pt">'
        "<v:textbox><w:txbxContent>{}</w:txbxContent></v:textbox>"
        "</v:shape></w:pict></w:r></w:p>"
    ).format(para("株式会社"))


def build_10():
    body = "".join(
        [
            para("東京", style="Heading1"),
            # Bookmark + internal hyperlink + comment anchor.
            '<w:p><w:bookmarkStart w:id="1" w:name="anchor1"/>'
            "<w:commentRangeStart w:id=\"5\"/>"
            "<w:r><w:t>私は学生です</w:t></w:r>"
            '<w:commentRangeEnd w:id="5"/>'
            '<w:r><w:commentReference w:id="5"/></w:r>'
            '<w:bookmarkEnd w:id="1"/></w:p>',
            '<w:p><w:hyperlink w:anchor="anchor1"><w:r><w:t>大阪</w:t></w:r></w:hyperlink></w:p>',
            # Footnote and endnote references.
            '<w:p><w:r><w:t>第3四半期</w:t></w:r>'
            '<w:r><w:footnoteReference w:id="2"/></w:r>'
            '<w:r><w:endnoteReference w:id="2"/></w:r></w:p>',
            table_xml(),
            para("株式会社", num=(1, 0)),
            para("東京", num=(1, 1)),
            image_paragraph(),
            para("2026年5月13日"),
            textbox_paragraph(),
            # A PAGE field: the instrText must never be romanized.
            '<w:p><w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p>',
            '<w:sectPr><w:headerReference w:type="default" r:id="rIdHdr"/>'
            '<w:footerReference w:type="default" r:id="rIdFtr"/>'
            '<w:pgSz w:w="11906" w:h="16838"/></w:sectPr>',
        ]
    )
    document = DECL + "<w:document {}><w:body>{}</w:body></w:document>".format(NS, body)

    header = DECL + "<w:hdr {}>{}</w:hdr>".format(NS, para("株式会社"))
    footer = DECL + "<w:ftr {}>{}</w:ftr>".format(
        NS, '<w:p><w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p>'
    )

    footnotes = DECL + (
        "<w:footnotes {ns}>"
        '<w:footnote w:id="-1" w:type="separator"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:id="0" w:type="continuationSeparator"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
        '<w:footnote w:id="2">{p}</w:footnote>'
        "</w:footnotes>"
    ).format(ns=NS, p=para("大阪"))

    endnotes = DECL + (
        "<w:endnotes {ns}>"
        '<w:endnote w:id="-1" w:type="separator"><w:p><w:r><w:separator/></w:r></w:p></w:endnote>'
        '<w:endnote w:id="0" w:type="continuationSeparator"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:endnote>'
        '<w:endnote w:id="2">{p}</w:endnote>'
        "</w:endnotes>"
    ).format(ns=NS, p=para("東京"))

    comments = DECL + (
        "<w:comments {ns}>"
        '<w:comment w:id="5" w:author="Tomo" w:date="2026-07-10T00:00:00Z" w:initials="T">{p}</w:comment>'
        "</w:comments>"
    ).format(ns=NS, p=para("株式会社"))

    parts = {
        "[Content_Types].xml": content_types(
            [
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
                '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
                '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>',
                '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>',
                '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>',
                '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>',
                '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>',
                '<Override PartName="/word/endnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"/>',
                '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>',
            ],
            defaults=['<Default Extension="png" ContentType="image/png"/>'],
        ),
        "_rels/.rels": package_rels(),
        "word/document.xml": document,
        "word/_rels/document.xml.rels": document_rels(
            [
                _rel("rId1", "styles", "styles.xml"),
                _rel("rId2", "numbering", "numbering.xml"),
                _rel("rId3", "settings", "settings.xml"),
                _rel("rIdHdr", "header", "header1.xml"),
                _rel("rIdFtr", "footer", "footer1.xml"),
                _rel("rIdFn", "footnotes", "footnotes.xml"),
                _rel("rIdEn", "endnotes", "endnotes.xml"),
                _rel("rIdCm", "comments", "comments.xml"),
                _rel("rIdImg", "image", "media/image1.png"),
            ]
        ),
        "word/styles.xml": minimal_styles(),
        "word/numbering.xml": numbering_xml(),
        "word/settings.xml": minimal_settings(),
        "word/header1.xml": header,
        "word/footer1.xml": footer,
        "word/footnotes.xml": footnotes,
        "word/endnotes.xml": endnotes,
        "word/comments.xml": comments,
        "word/media/image1.png": tiny_png(),
    }
    write_docx(SAMPLES / "10_composite.docx", parts)


def main():
    build_05()
    build_10()
    for name in ("05_lists.docx", "10_composite.docx"):
        print("wrote samples/{}".format(name))


if __name__ == "__main__":
    main()
