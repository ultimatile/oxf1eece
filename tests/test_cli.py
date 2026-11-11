"""End-to-end checks against the bundled lexicon."""

from __future__ import annotations

import pytest

from hexsieve.cli import main


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
    coffee = next(r for r in rows if r[1] == "coffee")
    assert coffee[:3] == ["c0ffee", "coffee", "n"]
    assert coffee[4] == "o0"


def test_list_marks_inflected_forms_with_their_lemma(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "list", "--pos", "verb", "--preset", "strict")
    aided = next(r for r in rows if r[1] == "faded")
    assert aided[5].startswith("[fade] ")


def test_max_size_and_limit(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "tag", "8", "--max-size", "35", "--limit", "5")
    assert len(rows) == 5
    assert all(r[2] and int(r[2]) <= 35 for r in rows)


def test_hex_desc_sort(capsys: pytest.CaptureFixture[str]) -> None:
    _, rows = run(capsys, "list", "--preset", "strict", "--sort=-hex")
    values = [int(r[0], 16) for r in rows]
    assert values == sorted(values, reverse=True)


def test_unknown_rule_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--enable", "q9"]) == 2
    assert "unknown rule" in capsys.readouterr().err
