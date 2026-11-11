"""Adjective + noun tags whose hex spellings add up to a requested number of digits."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from hexsieve.lexicon import Pos
from hexsieve.sieve import Hit


@dataclass(frozen=True, slots=True)
class Tag:
    adj: Hit
    noun: Hit

    @property
    def hex(self) -> str:
        return self.adj.hex + self.noun.hex

    @property
    def size(self) -> int | None:
        """The rarer word's size; None if either word has no size."""
        a, n = self.adj.size, self.noun.size
        return None if a is None or n is None else max(a, n)

    @property
    def label(self) -> str:
        return f"{self.adj.label}+{self.noun.label}"


def generate_tags(hits: Iterable[Hit], digits: int) -> list[Tag]:
    """Pair every adjective hit with every noun hit so the joined hex has `digits` digits.

    Lengths are those of the hex spellings, which differ from the word lengths when a
    multi-letter rule (e.g. ate -> 8) fired.
    """
    if digits < 2:
        raise ValueError(f"digits must be at least 2, got {digits}")
    by_len: dict[Pos, dict[int, list[Hit]]] = {
        Pos.ADJ: defaultdict(list),
        Pos.NOUN: defaultdict(list),
    }
    for h in hits:
        if h.entry.pos in by_len:
            by_len[h.entry.pos][len(h.hex)].append(h)
    adjs, nouns = by_len[Pos.ADJ], by_len[Pos.NOUN]
    return [
        Tag(a, n)
        for k in range(1, digits)
        for a in adjs.get(k, [])
        for n in nouns.get(digits - k, [])
    ]
