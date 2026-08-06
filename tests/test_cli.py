"""The command line interface."""

from pathlib import Path

import pytest

from pyperg.cli.main import main

FIXTURE = str(Path(__file__).parent / "fixtures" / "calc.mgff")


def test_lex_prints_the_tree(capsys):
    assert main(["lex", FIXTURE]) == 0
    out = capsys.readouterr().out
    assert "file " in out
    assert "item t" in out
    assert "group" in out


def test_lex_with_spans(capsys):
    assert main(["lex", "--spans", FIXTURE]) == 0
    assert "[1:1-" in capsys.readouterr().out


def test_lex_reports_errors(tmp_path, capsys):
    bad = tmp_path / "bad.mgff"
    bad.write_text("d x = (a)(b)\n", encoding="utf-8")
    assert main(["lex", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "^" in err  # the excerpt points at the offending column


def test_generate_lists_backends(capsys):
    assert main(["generate", "--list"]) == 0
    assert "dump" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().out


def test_version():
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0


def test_a_file_that_is_not_utf_8_is_reported(tmp_path, capsys):
    """An MGFF file is UTF-8 text; anything else is said so, not decoded."""
    binary = tmp_path / "binary.mgff"
    binary.write_bytes(b"d A = \xff\xfe\n")
    assert main(["check", str(binary)]) == 1
    assert "not valid UTF-8" in capsys.readouterr().err


def test_a_deeply_nested_file_is_reported(tmp_path, capsys):
    deep = tmp_path / "deep.mgff"
    deep.write_text("d X = " + "(" * 400 + "a" + ")" * 400 + "\n", encoding="utf-8")
    assert main(["check", str(deep)]) == 1
    assert "error:" in capsys.readouterr().err
