"""Command-line interface for development testing.

    python -m romanizer romanize "東京タワー"
    echo "大阪" | python -m romanizer romanize --stdin
    python -m romanizer lint-dictionary

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

    lint_cmd = subparsers.add_parser(
        "lint-dictionary", help="audit custom_terms.json for dead or useless entries"
    )
    lint_cmd.add_argument(
        "--dict-dir", default=None, help="override the dictionaries directory"
    )
    return parser


_STATUS_ORDER = {"dead": 0, "shadowed": 1, "redundant": 2, "ok": 3}


def _run_lint(args):
    try:
        results = _dictionary.lint(args.dict_dir)
    except _dictionary.DictionaryError as exc:
        print("dictionary error: {}".format(exc), file=sys.stderr)
        return 1

    if not results:
        print("custom_terms.json is empty")
        return 0

    results.sort(key=lambda row: (_STATUS_ORDER[row[1]], row[0]))
    width = max(len(key) for key, _, _ in results)
    for key, status, detail in results:
        print("{:<{w}}  {:<9}  {}".format(key, status, detail, w=width))

    counts = {}
    for _, status, _ in results:
        counts[status] = counts.get(status, 0) + 1
    summary = ", ".join("{} {}".format(counts[s], s) for s in sorted(counts))
    print("\n{} entries: {}".format(len(results), summary))

    return 1 if counts.get("dead") else 0


def _run_romanize(args, parser):
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


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "romanize":
        return _run_romanize(args, parser)
    if args.command == "lint-dictionary":
        return _run_lint(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
