"""End-to-end checks against the bundled lexicon."""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from hexsieve import cli
from hexsieve.cli import main
from hexsieve.lexicon import Entry, LexiconError

needs_fzf = pytest.mark.skipif(shutil.which("fzf") is None, reason="fzf not installed")


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[list[str]]]:
    code = main(list(argv))
    out = capsys.readouterr().out
    return code, [line.split("\t") for line in out.splitlines()]


def test_strict_tag_finds_deadbeef(capsys: pytest.CaptureFixture[str]) -> None:
    code, rows = run(capsys, "tag", "8", "--preset", "strict")
    assert code == 0
    assert ["deadbeef", "dead+beef", "35", "-"] in rows
    assert all(len(r[0]) == 8 for r in rows)


def test_list_classic_spells_coffee_with_o0(capsys: pytest.CaptureFixture[str]) -> None:
    code, rows = run(capsys, "list", "--pos", "noun", "--length", "6")
    assert code == 0
    assert rows and all(len(r[0]) == 6 and r[2] == "n" for r in rows)
    coffee = next(r for r in rows if r[1] == "coffee")
    assert coffee[:3] == ["c0ffee", "coffee", "n"]
    assert coffee[4] == "o0"


def test_list_marks_inflected_forms_with_their_lemma(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "list", "--pos", "verb", "--preset", "strict")
    faded = next(r for r in rows if r[1] == "faded")
    assert faded[5].startswith("[fade] ")


def test_tag_rules_are_the_union_of_both_words(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "tag", "8", "--max-size", "35")
    assert ["ab1eace5", "able+aces", "35", "l1,s5"] in rows  # able: l1, aces: s5


def test_max_size_and_limit(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "tag", "8", "--max-size", "35", "--limit", "5")
    assert len(rows) == 5
    assert all(r[2] and int(r[2]) <= 35 for r in rows)


def test_hex_desc_sort(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "list", "--preset", "strict", "--sort=-hex")
    values = [int(r[0], 16) for r in rows]
    assert values == sorted(values, reverse=True)


def test_alpha_sort_and_upper(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "list", "--preset", "strict", "--sort", "alpha", "--upper")
    words = [r[1] for r in rows]
    assert words == sorted(words)
    assert all(r[0] == r[0].upper() for r in rows)
    assert next(r[:2] for r in rows if r[1] == "face") == ["FACE", "face"]


def test_rules_lists_rules_and_presets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "  o0     o -> 0" in out
    assert "  classic (default): o0 i1 l1 s5" in out


def test_unknown_rule_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--enable", "q9"]) == 2
    assert "unknown rule" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["list", "--pos", "noun,pronoun"],
        ["list", "--limit", "0"],
        ["list", "--limit", "abc"],
        ["list", "--length", "0"],
        ["list", "--max-size", "-1"],
        ["tag", "1"],
    ],
)
def test_bad_arguments_are_rejected_by_the_parser(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_closed_pipe_exits_quietly() -> None:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; from hexsieve.cli import main; sys.exit(main(['list']))",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    proc.stdout.readline()
    proc.stdout.close()
    stderr = proc.stderr.read()
    assert proc.wait() == 1
    assert stderr == b""


def test_search_without_fzf_is_an_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_fzf(_name: str) -> None:
        return None

    monkeypatch.setattr(shutil, "which", no_fzf)
    assert main(["search", "--preset", "strict"]) == 2
    assert "fzf not found" in capsys.readouterr().err


@needs_fzf
def test_search_prints_rows_fzf_selects(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # --filter makes fzf print its matches without opening the interactive screen.
    monkeypatch.setenv("FZF_DEFAULT_OPTS", "--filter=c0ffee")
    code, rows = run(capsys, "search", "--pos", "noun")
    assert code == 0
    assert ["c0ffee", "coffee"] in [r[:2] for r in rows]


@needs_fzf
def test_search_with_no_match_prints_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FZF_DEFAULT_OPTS", "--filter=zzzzzz")  # fzf exits 1: no match
    assert run(capsys, "search", "--preset", "strict") == (0, [])


@needs_fzf
def test_search_fzf_failure_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FZF_DEFAULT_OPTS", "--no-such-fzf-option")  # fzf exits 2
    with pytest.raises(subprocess.CalledProcessError):
        main(["search", "--preset", "strict"])


def test_non_integer_option_names_the_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["list", "--limit", "abc"])
    assert "--limit must be an integer, got 'abc'" in capsys.readouterr().err


def test_repeated_list_options_accumulate(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "list", "--preset", "strict", "--enable", "o0", "--enable", "s5")
    assert {"o0", "s5"} <= {rule for r in rows for rule in r[4].split(",")}


def test_search_aborted_in_fzf_prints_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def aborted(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 130, stdout="")

    def fake_fzf(_name: str) -> str:
        return "fzf"

    monkeypatch.setattr(shutil, "which", fake_fzf)
    monkeypatch.setattr(subprocess, "run", aborted)
    assert run(capsys, "search", "--preset", "strict") == (0, [])


def test_broken_lexicon_is_reported_as_an_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> tuple[Entry, ...]:
        raise LexiconError("line 2: want 5 fields, got 4")

    monkeypatch.setattr(cli, "load_lexicon", broken)
    assert main(["list"]) == 2
    assert "hexsieve: error: line 2" in capsys.readouterr().err
