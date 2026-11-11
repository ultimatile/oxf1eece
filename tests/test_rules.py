from __future__ import annotations

import pytest

from hexsieve.rules import Derivation, Rule, RuleError, RuleSet, load_catalog, parse_catalog


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


def test_same_hex_via_two_paths_keeps_the_one_with_fewer_rules() -> None:
    assert rs(("ab", "ab", "ab")).convert("ab") == {Derivation("ab", ())}


@pytest.mark.parametrize(
    ("source", "target"), [("", "0"), ("O", "0"), ("o1", "0"), ("o", "g"), ("o", "")]
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
    "kwargs", [{"preset": "nope"}, {"enable": ["nope"]}, {"disable": ["nope"]}]
)
def test_resolve_rejects_unknown_names(kwargs: dict[str, object]) -> None:
    with pytest.raises(RuleError):
        parse_catalog(CATALOG).resolve(**kwargs)  # type: ignore[arg-type]


def test_preset_naming_unknown_rule_is_rejected() -> None:
    with pytest.raises(RuleError, match="unknown rules"):
        parse_catalog('[rules]\n[presets]\nclassic = ["x9"]\n')


def test_catalog_without_default_preset_is_rejected() -> None:
    with pytest.raises(RuleError, match="default preset"):
        parse_catalog("[rules]\n[presets]\nstrict = []\n")


def test_bundled_presets_match_the_design() -> None:
    catalog = load_catalog()
    assert catalog.presets["strict"] == ()
    assert catalog.presets["classic"] == ("o0", "i1", "l1", "s5")
    assert catalog.presets["leet"] == ("o0", "i1", "l1", "s5", "t7", "g9", "z2")
