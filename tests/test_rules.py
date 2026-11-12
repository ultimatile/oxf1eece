from __future__ import annotations

import pytest

from oxf1eece.rules import (
    Derivation,
    Rule,
    RuleCatalog,
    RuleError,
    RuleSet,
    load_catalog,
    parse_catalog,
)


def rs(*specs: tuple[str, str, str]) -> RuleSet:
    return RuleSet(tuple(Rule(n, s, t) for n, s, t in specs))


def hexes(ruleset: RuleSet, word: str) -> set[str]:
    return {d.hex for d in ruleset.convert(word)}


def test_hex_letters_need_no_rule() -> None:
    assert rs().convert("deadbeef") == {Derivation("deadbeef", ())}


def test_unspellable_word_yields_nothing() -> None:
    assert rs(("o0", "o", "0")).convert("coffeex") == frozenset()


def test_single_letter_rule_records_its_name() -> None:
    assert rs(("o0", "o", "0")).convert("coffee") == {Derivation("c0ffee", ("o0",))}


def test_conversion_is_case_insensitive() -> None:
    assert hexes(rs(), "Face") == {"face"}


def test_alternative_targets_for_one_letter_give_every_spelling() -> None:
    assert hexes(rs(("g6", "g", "6"), ("g9", "g", "9")), "egg") == {"e66", "e69", "e96", "e99"}


def test_multi_letter_rule_is_the_only_path_when_letters_lack_rules() -> None:
    # t has no rule, so "late" can only be spelled via ate -> 8.
    assert hexes(rs(("l1", "l", "1"), ("ate8", "ate", "8")), "late") == {"18"}


def test_multi_letter_rule_competes_with_letter_rules() -> None:
    rules = rs(("l1", "l", "1"), ("t7", "t", "7"), ("ate8", "ate", "8"))
    assert hexes(rules, "late") == {"18", "1a7e"}


def test_equally_small_rule_sets_are_broken_by_rule_name() -> None:
    assert rs(("q", "y", "1"), ("p", "y", "1")).convert("y") == {Derivation("1", ("p",))}


def test_same_hex_via_two_paths_keeps_the_one_with_fewer_rules() -> None:
    assert rs(("ab", "ab", "ab")).convert("ab") == {Derivation("ab", ())}


def test_fewest_rules_is_global_not_chosen_per_suffix() -> None:
    # "yyb" -> "11b" either as y,y,b via q alone, or as y + yb via {q, p}. For the suffix
    # "yb" alone, p ({p}) and q ({q}) tie, so a per-suffix choice can keep p and end
    # with {p, q}; the minimum over the whole word is {q}.
    rules = rs(("p", "yb", "1b"), ("q", "y", "1"))
    assert rules.convert("yyb") == {Derivation("11b", ("q",))}


@pytest.mark.parametrize(
    ("source", "target"),
    [("", "0"), ("O", "0"), ("o1", "0"), ("é", "0"), ("o", "g"), ("o", "")],
)
def test_invalid_rule_is_rejected(source: str, target: str) -> None:
    with pytest.raises(RuleError):
        Rule("bad", source, target)


CATALOG = """
[rules]
o0 = { from = "o", to = "0" }
i1 = { from = "i", to = "1" }
s5 = { from = "s", to = "5" }
[presets]
classic = ["o0", "i1"]
"""


def test_resolve_applies_enable_and_disable_to_the_preset() -> None:
    catalog = parse_catalog(CATALOG)
    assert catalog.resolve("classic", enable=["s5"], disable=["i1"]).names == ("o0", "s5")


def test_disable_wins_over_enable() -> None:
    assert parse_catalog(CATALOG).resolve("classic", enable=["s5"], disable=["s5"]).names == (
        "o0",
        "i1",
    )


@pytest.mark.parametrize(
    ("preset", "enable", "disable"),
    [("nope", [], []), ("classic", ["nope"], []), ("classic", [], ["nope"])],
)
def test_resolve_rejects_unknown_names(preset: str, enable: list[str], disable: list[str]) -> None:
    with pytest.raises(RuleError):
        parse_catalog(CATALOG).resolve(preset, enable, disable)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[rules]\n[presets]\nclassic = ["x9"]\n', "unknown rules"),
        ("[rules\n", "invalid rules TOML"),
        ("[rules]\n[presets]\nstrict = []\n", "default preset"),
    ],
)
def test_catalog_checks_raise_rule_error(text: str, message: str) -> None:
    with pytest.raises(RuleError, match=message):
        parse_catalog(text)


def test_catalog_built_directly_is_validated_too() -> None:
    with pytest.raises(RuleError, match="unknown rules"):
        RuleCatalog({}, {"classic": ("x9",)})


def test_bundled_presets_match_the_design() -> None:
    catalog = load_catalog()
    assert catalog.presets["strict"] == ()
    assert catalog.presets["classic"] == ("o0", "i1", "l1", "s5")
    assert catalog.presets["leet"] == ("o0", "i1", "l1", "s5", "t7", "g9", "z2")
