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

    convert_cmd = subparsers.add_parser("convert", help="romanize a document")
    convert_cmd.add_argument("input", help="path to the source document")
    convert_cmd.add_argument("output", help="path to write the converted document")
    convert_cmd.add_argument(
        "--dict-dir", default=None, help="override the dictionaries directory"
    )

    diff_cmd = subparsers.add_parser(
        "diff-xlsx",
        help="compare our romanization of an .xlsx against a human reference",
    )
    diff_cmd.add_argument("original", help="the Japanese .xlsx original")
    diff_cmd.add_argument("expected", help="the hand-romanized reference .xlsx")
    diff_cmd.add_argument("--limit", type=int, default=None, help="cap rows shown")
    diff_cmd.add_argument(
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


#: Exit codes. 2 means the document was refused, which is not a crash and
#: should not be reported to the user as one.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

_HANDLERS = {
    ".docx": "romanizer.handlers.docx_handler",
    ".xlsx": "romanizer.handlers.xlsx_handler",
}


def _run_convert(args):
    import importlib
    from pathlib import Path

    source = Path(args.input)
    suffix = source.suffix.lower()
    if suffix not in _HANDLERS:
        print(
            "unsupported file type {!r}. Supported: {}".format(
                suffix, ", ".join(sorted(_HANDLERS))
            ),
            file=sys.stderr,
        )
        return EXIT_ERROR
    if not source.exists():
        print("no such file: {}".format(source), file=sys.stderr)
        return EXIT_ERROR

    handler = importlib.import_module(_HANDLERS[suffix])
    # A handler may refuse a document (the DOCX handler refuses tracked
    # changes); that is a distinct, non-crash outcome, reported with exit code
    # EXIT_REFUSED. Handlers expose the refusal type as `refusal_error` and
    # their own error base as `handler_error`.
    refusal = getattr(handler, "refusal_error", None)
    handler_error = getattr(handler, "handler_error", Exception)
    try:
        dic = _dictionary.load(args.dict_dir) if args.dict_dir else _dictionary.default()
        handler.convert(source, Path(args.output), dic)
    except _dictionary.DictionaryError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:
        if refusal is not None and isinstance(exc, refusal):
            print(str(exc), file=sys.stderr)
            return EXIT_REFUSED
        if isinstance(exc, handler_error):
            print("error: {}".format(exc), file=sys.stderr)
            return EXIT_ERROR
        raise

    print("wrote {}".format(args.output))
    return EXIT_OK


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "romanize":
        return _run_romanize(args, parser)
    if args.command == "lint-dictionary":
        return _run_lint(args)
    if args.command == "convert":
        return _run_convert(args)
    if args.command == "diff-xlsx":
        return _run_diff_xlsx(args)
    parser.error("unknown command")
    return EXIT_ERROR


def _run_diff_xlsx(args):
    from pathlib import Path

    from . import corpus_diff

    dic = _dictionary.load(args.dict_dir) if args.dict_dir else _dictionary.default()
    try:
        divergences, summary = corpus_diff.compare_xlsx(
            Path(args.original), Path(args.expected), dic
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print("diff error: {}".format(exc), file=sys.stderr)
        return EXIT_ERROR
    print(corpus_diff.format_report(divergences, summary, args.limit))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
