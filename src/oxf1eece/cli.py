"""Command-line interface: list / tag / search / rules."""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections.abc import Callable, Iterator, Sequence

from oxf1eece.lexicon import LexiconError, Pos, load_lexicon
from oxf1eece.rules import DEFAULT_PRESET, RuleError, RuleSet, load_catalog
from oxf1eece.search import FzfNotFoundError, fzf_select
from oxf1eece.sieve import Hit, SortKey, sieve, sort_items
from oxf1eece.tag import Tag, generate_tags

POS_CHOICES = {"noun": Pos.NOUN, "verb": Pos.VERB, "adj": Pos.ADJ, "adv": Pos.ADV}


def _csv(value: str) -> list[str]:
    return [v for v in (s.strip() for s in value.split(",")) if v]


def _pos_list(value: str) -> list[Pos]:
    names = _csv(value)
    unknown = [n for n in names if n not in POS_CHOICES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown part of speech: {', '.join(unknown)} (known: {', '.join(POS_CHOICES)})"
        )
    return [POS_CHOICES[n] for n in names]


def _at_least(minimum: int, what: str) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            n = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{what} must be an integer, got {value!r}") from None
        if n < minimum:
            raise argparse.ArgumentTypeError(f"{what} must be at least {minimum}, got {n}")
        return n

    return parse


def _add_list_option(
    add_argument: Callable[..., object],
    flag: str,
    metavar: str,
    help_: str,
    parse: Callable[[str], Sequence[object]] = _csv,
) -> None:
    """Add a repeatable comma-separated option; values accumulate across uses."""
    add_argument(flag, type=parse, action="extend", default=[], metavar=metavar, help=help_)


def _common_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("conversion rules")
    g.add_argument("--preset", default=DEFAULT_PRESET, help="rule preset (default: %(default)s)")
    _add_list_option(
        g.add_argument, "--enable", "RULES", "comma-separated rules to add to the preset"
    )
    _add_list_option(
        g.add_argument, "--disable", "RULES", "comma-separated rules to remove from the preset"
    )
    f = p.add_argument_group("filtering and output")
    f.add_argument(
        "--max-size",
        type=_at_least(1, "--max-size"),
        metavar="N",
        help="keep only words whose ESDB size is N or less (35 common ... 80 rare)",
    )
    f.add_argument(
        "--sort",
        type=SortKey,
        choices=list(SortKey),
        default=SortKey.TIER,
        help="order: tier (ESDB size), hex / -hex (numeric value; write --sort=-hex), "
        "alpha, random (default: %(default)s)",
    )
    f.add_argument("--seed", type=int, help="seed for --sort random")
    f.add_argument(
        "--limit", type=_at_least(1, "--limit"), metavar="N", help="print at most N rows"
    )
    f.add_argument("--upper", action="store_true", help="print hex in uppercase")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(prog="oxf1eece", description="Find hexspeak words and tags.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_ in (
        ("list", "print words spellable in hex as TSV: hex, word, pos, size, rules, gloss"),
        ("search", "pick words interactively with fzf"),
    ):
        sp = sub.add_parser(name, parents=[common], help=help_, description=help_)
        _add_list_option(
            sp.add_argument,
            "--pos",
            "POS",
            f"comma-separated parts of speech to keep ({', '.join(POS_CHOICES)})",
            _pos_list,
        )
        sp.add_argument(
            "--length",
            type=_at_least(1, "--length"),
            metavar="N",
            help="keep only N-digit hex spellings",
        )

    tp = sub.add_parser(
        "tag",
        parents=[common],
        help="print adjective+noun tags as TSV: hex, adj+noun, size, rules",
        description="Print adjective+noun tags whose joined hex has exactly DIGITS digits. "
        "A tag's size is the larger (rarer) of its two words' sizes, or empty if either "
        "word has none.",
    )
    tp.add_argument(
        "digits", type=_at_least(2, "DIGITS"), help="total number of hex digits, e.g. 8"
    )

    sub.add_parser("rules", help="show the available rules and presets")
    return parser


def _ruleset(args: argparse.Namespace) -> RuleSet:
    return load_catalog().resolve(args.preset, args.enable, args.disable)


def _hex(s: str, upper: bool) -> str:
    return s.upper() if upper else s


def _rules_field(names: Sequence[str]) -> str:
    return ",".join(names) or "-"


def _size_field(size: int | None) -> str:
    return "" if size is None else str(size)


def _hit_rows(hits: Sequence[Hit], upper: bool) -> Iterator[str]:
    for h in hits:
        e = h.entry
        gloss = f"[{e.lemma}] {e.gloss}" if e.inflected else e.gloss
        yield (
            "\t".join(
                (
                    _hex(h.hex, upper),
                    e.word,
                    e.pos.value,
                    _size_field(e.size),
                    _rules_field(h.derivation.rules),
                    gloss,
                )
            )
            + "\n"
        )


def _tag_rows(tags: Sequence[Tag], upper: bool) -> Iterator[str]:
    for t in tags:
        rules = sorted(set(t.adj.derivation.rules) | set(t.noun.derivation.rules))
        yield (
            "\t".join(
                (
                    _hex(t.hex, upper),
                    t.label,
                    _size_field(t.size),
                    _rules_field(rules),
                )
            )
            + "\n"
        )


def _select_hits(args: argparse.Namespace) -> list[Hit]:
    pos = frozenset[Pos](args.pos) or None
    hits = sieve(load_lexicon(), _ruleset(args), pos=pos, max_size=args.max_size)
    if args.length is not None:
        hits = [h for h in hits if len(h.hex) == args.length]
    return sort_items(hits, args.sort, args.seed)[: args.limit]


def _print_rules() -> None:
    catalog = load_catalog()
    print("rules (the letters a-f need none):")
    for r in catalog.rules.values():
        print(f"  {r.name:<6} {r.source} -> {r.target}")
    print("presets:")
    for name, members in catalog.presets.items():
        default = " (default)" if name == DEFAULT_PRESET else ""
        print(f"  {name}{default}: {' '.join(members) or '(a-f only)'}")


def main(argv: Sequence[str] | None = None) -> int:
    # Glosses contain non-ASCII text; write UTF-8 whatever the locale says.
    stdout = sys.stdout
    if isinstance(stdout, io.TextIOWrapper):
        stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        match args.command:
            case "rules":
                _print_rules()
            case "list":
                sys.stdout.writelines(_hit_rows(_select_hits(args), args.upper))
            case "search":
                rows = list(_hit_rows(_select_hits(args), args.upper))
                sys.stdout.writelines(fzf_select(rows, preview_field=6))
            case "tag":
                hits = sieve(
                    load_lexicon(),
                    _ruleset(args),
                    pos=frozenset({Pos.ADJ, Pos.NOUN}),
                    max_size=args.max_size,
                )
                tags = sort_items(generate_tags(hits, args.digits), args.sort, args.seed)
                sys.stdout.writelines(_tag_rows(tags[: args.limit], args.upper))
            case _:
                raise AssertionError(f"unhandled command {args.command!r}")
        # Flush here so a closed pipe surfaces inside this try, not at interpreter exit.
        sys.stdout.flush()
    except (RuleError, LexiconError, FzfNotFoundError) as e:
        print(f"oxf1eece: error: {e}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # Downstream (e.g. `| head`) closed the pipe. Point stdout at devnull so the
        # interpreter's final flush does not raise again (Python docs, "Note on SIGPIPE").
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1
    return 0
