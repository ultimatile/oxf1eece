"""The bundled word list: OEWN lemmas and ESDB inflected forms with POS, size and gloss."""

from __future__ import annotations

import gzip
import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib.resources import files

COLUMNS = ("word", "pos", "size", "lemma", "gloss")


class Pos(StrEnum):
    NOUN = "n"
    VERB = "v"
    ADJ = "a"
    ADV = "r"


@dataclass(frozen=True, slots=True)
class Entry:
    word: str
    pos: Pos
    size: int | None
    """ESDB size (lower is more common); None when ESDB has no size of 80 or less."""
    lemma: str
    """The OEWN lemma; equal to `word` unless `word` is an inflected form taken from ESDB."""
    gloss: str
    """OEWN definition(s) of the lemma."""

    @property
    def inflected(self) -> bool:
        return self.word != self.lemma


class LexiconError(ValueError):
    """A lexicon row is malformed (header, field count, POS or size), or an entry cannot be
    written as a row. A corrupt gzip stream or non-UTF-8 data is not checked and surfaces as
    Python's own exception."""


def parse_rows(lines: Iterable[str]) -> Iterator[Entry]:
    it = iter(lines)
    header = next(it, "").rstrip("\n").split("\t")
    if tuple(header) != COLUMNS:
        raise LexiconError(f"unexpected lexicon header {header!r}, want {COLUMNS!r}")
    for lineno, line in enumerate(it, start=2):
        fields = line.rstrip("\n").split("\t")
        if len(fields) != len(COLUMNS):
            raise LexiconError(f"line {lineno}: want {len(COLUMNS)} fields, got {len(fields)}")
        word, pos, size, lemma, gloss = fields
        try:
            yield Entry(word, Pos(pos), int(size) if size else None, lemma, gloss)
        except ValueError as e:
            raise LexiconError(f"line {lineno}: {e}") from e


def format_rows(entries: Iterable[Entry]) -> Iterator[str]:
    """Serialize entries as TSV; raises LexiconError for a field holding a tab or newline."""
    yield "\t".join(COLUMNS) + "\n"
    for e in entries:
        size = "" if e.size is None else str(e.size)
        fields = (e.word, e.pos.value, size, e.lemma, e.gloss)
        if any("\t" in f or "\n" in f for f in fields):
            raise LexiconError(f"entry {e.word!r} has a tab or newline in a field")
        yield "\t".join(fields) + "\n"


def read_lexicon(raw: bytes) -> tuple[Entry, ...]:
    """Parse gzip-compressed lexicon rows; only "\\n" ends a row, as `format_rows` writes."""
    with gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", newline="\n") as f:
        return tuple(parse_rows(f))


@cache
def load_lexicon() -> tuple[Entry, ...]:
    return read_lexicon(files("hexsieve").joinpath("data", "lexicon.tsv.gz").read_bytes())
