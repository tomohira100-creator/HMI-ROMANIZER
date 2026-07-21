"""Zip-level read and write for OOXML packages, preserving untouched parts.

An OOXML file -- DOCX, XLSX, PPTX -- is a zip of parts. ROMANIZER edits a
handful of XML parts and must leave every other byte alone: images, embedded
objects, styles, themes, printer settings, drawings, content types,
relationships.

This module reads a package into its original ZipInfo entries and writes it
back, substituting only the parts the caller replaced. Untouched parts are
copied byte for byte, with their original compression, timestamps and
attributes. That is a stronger guarantee than re-serializing them through an
XML library, which would rewrite attribute order and namespace declarations
even when nothing changed, and it is what makes the "untouched parts are
byte-identical" test in the suite meaningful.

Deliberately not built on python-docx or openpyxl. python-docx misses text
(runs inside w:ins and w:fldSimple report as absent) and destroys structure
(assigning to run.text drops w:br and w:tab). openpyxl drops whole parts on a
round-trip -- drawings, printer settings, headers -- and rewrites every shared
string inline. Both re-serialize parts they did not change, which forecloses
the byte-identity guarantee. Their convenience APIs are the hazard; the zip
layer here is not.
"""

from zipfile import ZIP_DEFLATED, ZipFile


class Package:
    """An OOXML package held as ordered entries, with selective replacement."""

    def __init__(self, entries):
        # entries: list of (ZipInfo, bytes), in the package's original order.
        self._entries = list(entries)
        self._replaced = {}

    @classmethod
    def read(cls, path):
        with ZipFile(path) as archive:
            entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
        return cls(entries)

    @property
    def names(self):
        return [info.filename for info, _ in self._entries]

    def read_part(self, name):
        if name in self._replaced:
            return self._replaced[name]
        for info, blob in self._entries:
            if info.filename == name:
                return blob
        raise KeyError(name)

    def replace(self, name, blob):
        if name not in self.names:
            raise KeyError(name)
        self._replaced[name] = blob

    @property
    def replaced_names(self):
        return set(self._replaced)

    def write(self, path):
        """Write the package. Order, compression and metadata are preserved."""
        with ZipFile(path, "w") as archive:
            for info, blob in self._entries:
                payload = self._replaced.get(info.filename, blob)
                # Reuse the original ZipInfo so date_time, external_attr and
                # compress_type survive. A replaced part may differ in size,
                # which ZipFile recomputes.
                archive.writestr(info, payload)


def is_xml_part(name):
    return name.endswith(".xml") or name.endswith(".rels")
