"""CLI behaviour: exit codes, stdin, encoding."""

import io
import sys

import pytest

from romanizer import cli


def run(argv, capsys, stdin=None):
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_romanize_argument(capsys):
    code, out, _ = run(["romanize", "東京タワー"], capsys)
    assert code == 0
    assert out == "Tōkyō Tawā\n"


def test_romanize_stdin(capsys):
    code, out, _ = run(["romanize", "--stdin"], capsys, stdin="大阪")
    assert code == 0
    assert out == "Ōsaka\n"


def test_output_is_utf8_encodable(capsys):
    _, out, _ = run(["romanize", "空港"], capsys)
    assert out.strip().encode("utf-8").decode("utf-8") == "Kūkō"


def test_missing_text_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["romanize"])
    assert exc.value.code != 0


def test_no_command_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code != 0


def test_bad_dict_dir_returns_one(capsys, tmp_path):
    code, _, err = run(["romanize", "東京", "--dict-dir", str(tmp_path)], capsys)
    assert code == 1
    assert "dictionary error" in err


def test_english_passthrough_via_cli(capsys):
    code, out, _ = run(["romanize", "HMI ホテルグループ"], capsys)
    assert code == 0
    assert out == "HMI Hoteru Gurūpu\n"
