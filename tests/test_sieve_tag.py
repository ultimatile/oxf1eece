from __future__ import annotations

import pytest

from hexsieve.lexicon import Entry, Pos
from hexsieve.rules import Derivation, Rule, RuleSet
from hexsieve.sieve import Hit, SortKey, sieve, sort_items
from hexsieve.tag import generate_tags

O0_I1_L1 = RuleSet((Rule("o0", "o", "0"), Rule("i1", "i", "1"), Rule("l1", "l", "1")))


def entry(word: str, pos: Pos = Pos.NOUN, size: int | None = 35) -> Entry:
    return Entry(word, pos, size, word, "")


def hit(word: str, hex_: str, pos: Pos = Pos.NOUN, size: int | None = 35) -> Hit:
    return Hit(entry(word, pos, size), Derivation(hex_, ()))


def test_sieve_keeps_only_spellable_entries() -> None:
    hits = sieve([entry("coffee"), entry("tea"), entry("bad")], O0_I1_L1)
    assert [(h.label, h.hex) for h in hits] == [("coffee", "c0ffee"), ("bad", "bad")]


def test_sieve_emits_one_hit_per_spelling_of_one_word() -> None:
    rules = RuleSet((Rule("g6", "g", "6"), Rule("g9", "g", "9")))
    assert sorted(h.hex for h in sieve([entry("egg")], rules)) == ["e66", "e69", "e96", "e99"]


def test_sieve_emits_one_hit_per_distinct_spelling_of_different_words() -> None:
    hits = sieve([entry("bail"), entry("ball")], O0_I1_L1)
    assert [(h.label, h.hex) for h in hits] == [("bail", "ba11"), ("ball", "ba11")]


def test_sieve_filters_by_pos() -> None:
    hits = sieve(
        [entry("dead", Pos.ADJ), entry("beef", Pos.NOUN)], O0_I1_L1, pos=frozenset({Pos.ADJ})
    )
    assert [h.label for h in hits] == ["dead"]


def test_max_size_drops_rarer_and_unsized_entries() -> None:
    entries = [entry("ace", size=35), entry("abed", size=70), entry("dace", size=None)]
    assert [h.label for h in sieve(entries, O0_I1_L1, max_size=60)] == ["ace"]


def test_hex_sort_compares_numeric_value_not_text() -> None:
    # Text order would put "ace" before "fa"; numerically 0xfa < 0xace.
    items = [hit("ace", "ace"), hit("fa", "fa"), hit("odd", "0dd"), hit("dd", "dd")]
    assert [h.hex for h in sort_items(items, SortKey.HEX)] == ["dd", "0dd", "fa", "ace"]


def test_hex_desc_is_exactly_hex_reversed_including_full_ties() -> None:
    # Same word in two parts of speech ties on (value, length, label).
    items = [hit("ace", "ace", Pos.NOUN), hit("ace", "ace", Pos.VERB), hit("fa", "fa")]
    asc = sort_items(items, SortKey.HEX)
    assert sort_items(items, SortKey.HEX_DESC) == asc[::-1]


def test_tier_sort_puts_unsized_last() -> None:
    items = [hit("x", "a", size=None), hit("y", "b", size=70), hit("z", "c", size=35)]
    assert [h.label for h in sort_items(items, SortKey.TIER)] == ["z", "y", "x"]


def test_random_sort_is_reproducible_with_seed() -> None:
    items = [hit(str(i), "a") for i in range(20)]
    first = sort_items(items, SortKey.RANDOM, seed=1)
    assert first == sort_items(items, SortKey.RANDOM, seed=1)
    assert sorted(first, key=lambda h: h.label) == sorted(items, key=lambda h: h.label)


def test_tags_have_exactly_the_requested_digits() -> None:
    hits = [
        hit("dead", "dead", Pos.ADJ),
        hit("bad", "bad", Pos.ADJ),
        hit("beef", "beef"),
        hit("decaf", "decaf"),
        hit("decade", "decade"),  # 3 + 6 and 4 + 6: never 8
        hit("fee", "fee"),
    ]
    tags = generate_tags(hits, 8)
    assert sorted(t.label for t in tags) == ["bad+decaf", "dead+beef"]
    assert all(len(t.hex) == 8 for t in tags)


def test_tags_use_hex_length_not_word_length() -> None:
    # "late" spells as 2 hex digits via ate -> 8.
    tags = generate_tags([hit("late", "18", Pos.ADJ), hit("cafe", "cafe")], 6)
    assert [t.hex for t in tags] == ["18cafe"]


def test_tag_size_is_the_rarer_word() -> None:
    (tag,) = generate_tags([hit("dead", "dead", Pos.ADJ, 35), hit("beef", "beef", Pos.NOUN, 60)], 8)
    assert tag.size == 60


def test_tag_size_is_unknown_if_either_word_is_unsized() -> None:
    (tag,) = generate_tags(
        [hit("dead", "dead", Pos.ADJ, 35), hit("beef", "beef", Pos.NOUN, None)], 8
    )
    assert tag.size is None


def test_tags_ignore_other_parts_of_speech() -> None:
    assert generate_tags([hit("fade", "fade", Pos.VERB), hit("beef", "beef")], 8) == []


def test_tags_need_two_digits() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        generate_tags([], 1)


def test_a_word_listed_under_two_lemmas_is_paired_once() -> None:
    adj = hit("bad", "bad", Pos.ADJ)
    bases_of_base = Hit(Entry("bases", Pos.NOUN, 35, "base", "g1"), Derivation("ba5e5", ()))
    bases_of_basis = Hit(Entry("bases", Pos.NOUN, 35, "basis", "g2"), Derivation("ba5e5", ()))
    tags = generate_tags([adj, bases_of_base, bases_of_basis], 8)
    assert [t.label for t in tags] == ["bad+bases"]


def test_tag_pairing_keeps_entries_that_differ_in_pos_word_or_hex() -> None:
    # Same word and hex in two parts of speech: one serves as the adjective, one as the noun.
    pair = [hit("fade", "fade", Pos.ADJ), hit("fade", "fade", Pos.NOUN)]
    assert [t.label for t in generate_tags(pair, 8)] == ["fade+fade"]
    adj = hit("bad", "bad", Pos.ADJ)
    nouns = [hit("egg", "e66"), hit("egg", "e99"), hit("bail", "ba11"), hit("ball", "ba11")]
    # Same word, two hex spellings: both are paired.
    assert sorted(t.hex for t in generate_tags([adj, *nouns], 6)) == ["bade66", "bade99"]
    # Same hex, two words: both are paired.
    assert sorted(t.label for t in generate_tags([adj, *nouns], 7)) == ["bad+bail", "bad+ball"]
