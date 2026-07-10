"""Command-line interface for development testing.

    python -m romanizer romanize "東京タワー"
    echo "大阪" | python -m romanizer romanize --stdin

File conversion (python -m romanizer convert in.docx out.docx) arrives with
the handlers in Phase 2 and is deliberately absent here.
"""

import argparse
import sys

from . import dictionary as _dictionary
from .core import romanize


def build_parser():
    parser = argparse.ArgumentParser(
        prog="romanizer",
        description="Convert Japanese text to Hepburn romaji.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    text_cmd = subparsers.add_parser("romanize", help="romanize a string")
    text_cmd.add_argument("text", nargs="?", help="text to romanize")
    text_cmd.add_argument(
        "--stdin", action="store_true", help="read text from standard input"
    )
    text_cmd.add_argument(
        "--dict-dir", default=None, help="override the dictionaries directory"
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "romanize":
        parser.error("unknown command")

    if args.stdin:
        source = sys.stdin.read()
    elif args.text is not None:
        source = args.text
    else:
        parser.error("provide text or --stdin")
        return 2

    try:
        dic = _dictionary.load(args.dict_dir) if args.dict_dir else _dictionary.default()
        result = romanize(source, dic)
    except _dictionary.DictionaryError as exc:
        print("dictionary error: {}".format(exc), file=sys.stderr)
        return 1

    sys.stdout.write(result)
    if not result.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
