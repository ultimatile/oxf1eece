"""Select the lexicon entries that a rule set can spell in hex, and order them."""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from oxf1eece.lexicon import Entry, Pos
from oxf1eece.rules import Derivation, RuleSet


@dataclass(frozen=True, slots=True)
class Hit:
    entry: Entry
    derivation: Derivation

    @property
    def hex(self) -> str:
        return self.derivation.hex

    @property
    def size(self) -> int | None:
        return self.entry.size

    @property
    def label(self) -> str:
        return self.entry.word


def sieve(
    entries: Iterable[Entry],
    ruleset: RuleSet,
    *,
    pos: frozenset[Pos] | None = None,
    max_size: int | None = None,
) -> list[Hit]:
    """Return one Hit per (entry, distinct hex spelling).

    With `max_size`, entries with no size or a size above it are dropped.
    """
    hits: list[Hit] = []
    for e in entries:
        if pos is not None and e.pos not in pos:
            continue
        if max_size is not None and (e.size is None or e.size > max_size):
            continue
        hits.extend(Hit(e, d) for d in sorted(ruleset.convert(e.word)))
    return hits


class SortKey(StrEnum):
    TIER = "tier"
    HEX = "hex"
    HEX_DESC = "-hex"
    ALPHA = "alpha"
    RANDOM = "random"


class Sortable(Protocol):
    @property
    def hex(self) -> str: ...
    @property
    def size(self) -> int | None: ...
    @property
    def label(self) -> str: ...


def sort_items[T: Sortable](items: Sequence[T], key: SortKey, seed: int | None = None) -> list[T]:
    """Order items. `hex` / `-hex` compare numeric values, not text: `fa` (0xfa) sorts before
    `ace` (0xace), although text order puts `ace` first. Equal values (`dd`, `0dd`) fall back
    to length, then label. `-hex` is exactly the `hex` order reversed."""
    match key:
        case SortKey.TIER:
            return sorted(
                items, key=lambda x: (math.inf if x.size is None else x.size, x.label, x.hex)
            )
        case SortKey.HEX:
            return sorted(items, key=lambda x: (int(x.hex, 16), len(x.hex), x.label))
        case SortKey.HEX_DESC:
            return sort_items(items, SortKey.HEX)[::-1]
        case SortKey.ALPHA:
            return sorted(items, key=lambda x: (x.label, x.hex))
        case SortKey.RANDOM:
            out = list(items)
            random.Random(seed).shuffle(out)
            return out
