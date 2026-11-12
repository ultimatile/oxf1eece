"""Letter-to-hex conversion rules and the word converter built on them."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

HEX_LETTERS = "abcdef"
HEX_DIGITS = frozenset("0123456789abcdef")
DEFAULT_PRESET = "classic"


class RuleError(ValueError):
    """A check in this module failed: TOML syntax, a rule's `from` / `to` text, a preset
    naming an unknown rule, a missing default preset, or an unknown preset or rule name.

    Only these are checked. A structurally malformed rules file (a missing key, a value of
    the wrong type) is not, and surfaces as Python's own exception.
    """


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    source: str
    target: str

    def __post_init__(self) -> None:
        if not self.source or not (self.source.isascii() and self.source.isalpha()):
            raise RuleError(
                f"rule {self.name!r}: 'from' must be ASCII letters, got {self.source!r}"
            )
        if self.source != self.source.lower():
            raise RuleError(f"rule {self.name!r}: 'from' must be lowercase, got {self.source!r}")
        if not self.target or not set(self.target) <= HEX_DIGITS:
            raise RuleError(f"rule {self.name!r}: 'to' must be hex digits, got {self.target!r}")


@dataclass(frozen=True, slots=True, order=True)
class Derivation:
    """One way to spell a word in hex: the result and the names of the rules it used."""

    hex: str
    rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleSet:
    rules: tuple[Rule, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(r.name for r in self.rules)

    def convert(self, word: str) -> frozenset[Derivation]:
        """Return every distinct hex spelling of `word`; empty if the word cannot be spelled.

        The word is consumed left to right; at each position the letters a-f may stay as
        themselves and every enabled rule whose `source` matches there may fire. When
        several rule combinations yield the same hex string, one using the fewest distinct
        rules is kept (ties broken by rule names).
        """
        word = word.lower()
        if not set(word) <= self._letters():
            return frozenset()

        # For each suffix and each hex spelling of it, keep every inclusion-minimal set of
        # rule names that produces it. Dropping a superset T of an achievable S is safe:
        # whatever rule a prefix adds, S | {n} is a subset of T | {n}, so T never wins.
        @cache
        def from_pos(i: int) -> dict[str, frozenset[frozenset[str]]]:
            if i == len(word):
                return {"": frozenset({frozenset()})}
            out: dict[str, set[frozenset[str]]] = {}
            options: list[tuple[str, int, str | None]] = []
            if word[i] in HEX_LETTERS:
                options.append((word[i], 1, None))
            options.extend(
                (r.target, len(r.source), r.name)
                for r in self.rules
                if word.startswith(r.source, i)
            )
            for target, step, name in options:
                for tail, name_sets in from_pos(i + step).items():
                    bucket = out.setdefault(target + tail, set())
                    bucket.update(s | {name} if name is not None else s for s in name_sets)
            return {hex_: _minimal(sets) for hex_, sets in out.items()}

        return frozenset(
            Derivation(hex_, tuple(sorted(min(sets, key=_rank))))
            for hex_, sets in from_pos(0).items()
        )

    def _letters(self) -> frozenset[str]:
        return _letters_of(self.rules)


@cache
def _letters_of(rules: tuple[Rule, ...]) -> frozenset[str]:
    return frozenset(HEX_LETTERS).union(*(r.source for r in rules))


def _minimal(sets: set[frozenset[str]]) -> frozenset[frozenset[str]]:
    return frozenset(s for s in sets if not any(t < s for t in sets))


def _rank(names: frozenset[str]) -> tuple[int, tuple[str, ...]]:
    return (len(names), tuple(sorted(names)))


@dataclass(frozen=True, slots=True)
class RuleCatalog:
    """All defined rules and the named presets that select among them."""

    rules: Mapping[str, Rule]
    presets: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        for name, members in self.presets.items():
            unknown = [m for m in members if m not in self.rules]
            if unknown:
                raise RuleError(f"preset {name!r} names unknown rules: {', '.join(unknown)}")
        if DEFAULT_PRESET not in self.presets:
            raise RuleError(f"the default preset {DEFAULT_PRESET!r} is not defined")

    def resolve(
        self,
        preset: str = DEFAULT_PRESET,
        enable: Iterable[str] = (),
        disable: Iterable[str] = (),
    ) -> RuleSet:
        if preset not in self.presets:
            raise RuleError(f"unknown preset {preset!r} (known: {', '.join(self.presets)})")
        enable, disable = list(enable), list(disable)
        for name in (*enable, *disable):
            if name not in self.rules:
                raise RuleError(f"unknown rule {name!r} (known: {', '.join(self.rules)})")
        selected = [n for n in self.presets[preset] if n not in disable]
        selected += [n for n in enable if n not in selected and n not in disable]
        return RuleSet(tuple(self.rules[n] for n in selected))


def parse_catalog(text: str) -> RuleCatalog:
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise RuleError(f"invalid rules TOML: {e}") from e
    raw_rules: dict[str, dict[str, str]] = doc.get("rules", {})
    rules = {name: Rule(name, spec["from"], spec["to"]) for name, spec in raw_rules.items()}
    raw_presets: dict[str, list[str]] = doc.get("presets", {})
    return RuleCatalog(rules, {name: tuple(members) for name, members in raw_presets.items()})


@cache
def load_catalog() -> RuleCatalog:
    text = files("oxf1eece").joinpath("data", "rules.toml").read_text(encoding="utf-8")
    return parse_catalog(text)
