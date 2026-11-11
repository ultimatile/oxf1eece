"""Build src/hexsieve/data/lexicon.tsv.gz from pinned OEWN and ESDB sources.

Run with `uv run scripts/build_lexicon.py`. Sources are downloaded into `.cache/sources/`
(checked against pinned SHA-256 digests) unless already present.

- OEWN 2025 (the edition without the Namenet proper nouns) supplies lemmas, parts of
  speech and glosses; only single-word lowercase lemmas are kept.
- ESDB supplies each word's size and the inflected forms of OEWN lemmas. Only ESDB data of
  size 80 or less is used: larger sizes bring in UK Advanced Cryptics Dictionary words,
  whose licence would add a further notice requirement.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hexsieve.lexicon import Entry, Pos, format_rows

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class Source:
    url: str
    sha256: str
    filename: str


OEWN = Source(
    "https://github.com/globalwordnet/english-wordnet/releases/download/2025-edition/"
    "english-wordnet-2025.xml.gz",
    "9ca6d1dcb75f822fdd66617f7d9da48142ace38dd544d6ad5e2feca1674ad3fe",
    "english-wordnet-2025.xml.gz",
)
ESDB = Source(
    "https://raw.githubusercontent.com/en-wl/wordlist/"
    "1e5b7d3a72f47a71da5d28686c1dd4b397178485/data/scowl-pre.txt",
    "a5fe3f11682a6ab9d31f2ea2a185833b1a01be7af83409c671bd0756a870f6c7",
    "scowl-pre.txt",
)

ESDB_MAX_SIZE = 80
GLOSSES_PER_ENTRY = 2
WORD = re.compile(r"[a-z]+")

OEWN_POS = {"n": Pos.NOUN, "v": Pos.VERB, "a": Pos.ADJ, "s": Pos.ADJ, "r": Pos.ADV}
# ESDB POS tag -> POS of the inflected forms listed on that line. `m` (noun/verb) lists
# -ed / -ing verb forms and an -s form that may also be a noun plural; all are recorded
# as verb forms only, so that no -ed / -ing form is ever tagged as a noun. `a`
# (adjective/adverb) lists comparatives and superlatives, which serve both. Lines with any
# other tag (including the combined `n_v` / `aj_av`, which the pinned data does not use)
# contribute sizes but no inflected forms.
ESDB_POS = {
    "n": (Pos.NOUN,),
    "v": (Pos.VERB,),
    "m": (Pos.VERB,),
    "aj": (Pos.ADJ,),
    "av": (Pos.ADV,),
    "a": (Pos.ADJ, Pos.ADV),
}


def fetch(src: Source, cache_dir: Path) -> Path:
    path = cache_dir / src.filename
    if not path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        print(f"downloading {src.url}", file=sys.stderr)
        tmp = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(src.url) as resp, tmp.open("wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        tmp.rename(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != src.sha256:
        raise SystemExit(f"{path}: sha256 {digest} does not match pinned {src.sha256}")
    return path


# --- OEWN -------------------------------------------------------------------------------


class ReadableBytes(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


def parse_oewn(xml: ReadableBytes) -> dict[tuple[str, Pos], list[str]]:
    """Return {(lemma, pos): glosses} for single-word, lowercase ASCII lemmas in WN-LMF XML.

    Each list holds the first GLOSSES_PER_ENTRY distinct definitions, in sense order.
    """
    senses: dict[tuple[str, Pos], list[str]] = defaultdict(list)
    definitions: dict[str, str] = {}
    for _, el in ET.iterparse(xml, events=("end",)):
        if el.tag == "LexicalEntry":
            lemma = el.find("Lemma")
            word = "" if lemma is None else lemma.get("writtenForm", "")
            pos = None if lemma is None else OEWN_POS.get(lemma.get("partOfSpeech", ""))
            if pos is not None and WORD.fullmatch(word):
                senses[(word, pos)].extend(s.get("synset", "") for s in el.iter("Sense"))
            el.clear()
        elif el.tag == "Synset":
            d = el.find("Definition")
            if d is not None and d.text:
                definitions[el.get("id", "")] = " ".join(d.text.split())
            el.clear()
    out: dict[tuple[str, Pos], list[str]] = {}
    for key, synsets in senses.items():
        glosses = list(dict.fromkeys(definitions[s] for s in synsets if s in definitions))
        out[key] = glosses[:GLOSSES_PER_ENTRY]
    return out


# --- ESDB -------------------------------------------------------------------------------

# LEMMA_INFO := ([GROUP-ANNOTATION] WORD [ANNOTATION] | '-') [' <' POS ['/' CLASS] '>']
#               [' {' DEFN-NOTE '}'] [' (' USAGE-NOTE ')']
LEMMA_INFO = re.compile(
    r"(?P<word>-|[-@!]?[^\s<{(]+?[*\-@~!†]?)(?: <(?P<pos>[a-z_]*)(?:/[^>]*)?>)?"
    r"(?: \{[^}]*\})?(?: \([^)]*\))?"
)
# VARIANT-INFO prefix. The OVERRIDE form `+` is not used by the pinned data and not handled.
VARIANT_INFO = re.compile(r"[ABZCD_][.=?v~V@x-]?(?: [ABZCD_][.=?v~V@x-]?)*(?: \{\d+\})?")
# ENTRY := DERIVED | '(' [DERIVED-VARIANT-INFO ' ' ... ': '] DERIVED '|' ... ')'
DERIVED_ENTRY = re.compile(r"\s*\(([^)]*)\)|([^,]+)")


@dataclass(frozen=True, slots=True)
class EsdbLine:
    size: int
    lemma: str
    pos: str
    derived: tuple[str, ...]


def _clean_word(token: str) -> str | None:
    word = token.lstrip("-@!").rstrip("*-@~!†")
    return word if WORD.fullmatch(word) else None


def _is_invalid(variant_info: str) -> bool:
    """Whether a variant-info prefix marks a spelling with level `x` (ESDB: invalid)."""
    return any(t.endswith("x") for t in variant_info.split())


def _derived_words(derived: str) -> list[str]:
    """The derived forms, annotation marks stripped, that are plain lowercase words.

    Variant markers (`x: `, `v: ` before a bracketed alternative) are removed, and forms
    marked invalid (level `x`) are dropped.
    """
    words: list[str] = []
    for m in DERIVED_ENTRY.finditer(derived):
        alternatives = m[1].split("|") if m[1] is not None else [m[2]]
        for alt in alternatives:
            info, sep, form = alt.strip().rpartition(": ")
            if sep and _is_invalid(info):
                continue
            if (word := _clean_word(form.strip())) is not None:
                words.append(word)
    return words


def parse_esdb(lines: Iterable[str]) -> Iterator[EsdbLine]:
    """Yield one EsdbLine per data line, resolving `-` (same lemma) continuation lines.

    Spelling-variant prefixes (`A Bv C: `, `_~: `) are skipped, and so is any line or
    bracketed derived form whose spelling is marked invalid (variant level `x`); an invalid
    lemma line leaves the group's lemma unchanged for the continuation lines after it. A
    line whose lemma, once ESDB's annotation marks (`!`, `-`, `@`, `*`, `~`, `†`) are
    stripped, is not a plain lowercase word (e.g. `Bob`) is skipped together with the
    continuation lines that follow it. Derived forms are stripped the same way and dropped
    unless plain lowercase words (possessives, hyphenated or capitalised forms go). Lines
    without a `: ` separator, a size or a parsable lemma are skipped.
    """
    lemma: str | None = None
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            lemma = None  # blank line ends the group
            continue
        info, sep, rest = line.partition(": ")
        if not sep:
            continue
        sizes = [int(s) for s in re.findall(r"\d+", re.sub(r"\[[^\]]*\]", "", info))]
        if not sizes:
            continue
        head, _, derived = rest.partition(": ")
        invalid = False
        while VARIANT_INFO.fullmatch(head):
            invalid = invalid or _is_invalid(head)
            head, _, derived = derived.partition(": ")
        m = LEMMA_INFO.fullmatch(head)
        if m is None or invalid:
            continue
        if m["word"] != "-":
            lemma = _clean_word(m["word"])
        if lemma is None:
            continue
        yield EsdbLine(
            min(sizes),
            lemma,
            m["pos"] or "",
            tuple(w for w in _derived_words(derived) if w != lemma),
        )


# --- join -------------------------------------------------------------------------------


def build_entries(oewn: dict[tuple[str, Pos], list[str]], esdb: Iterable[EsdbLine]) -> list[Entry]:
    sizes: dict[str, int] = {}
    inflections: dict[tuple[str, Pos], str] = {}  # (form, pos) -> lemma
    for line in esdb:
        if line.size > ESDB_MAX_SIZE:
            continue
        for w in (line.lemma, *line.derived):
            sizes[w] = min(sizes.get(w, line.size), line.size)
        for pos in ESDB_POS.get(line.pos, ()):
            if (line.lemma, pos) not in oewn:
                continue
            for form in line.derived:
                if (form, pos) not in oewn:
                    inflections.setdefault((form, pos), line.lemma)

    def gloss(key: tuple[str, Pos]) -> str:
        return " | ".join(oewn[key]).replace("\t", " ")

    entries = [Entry(w, p, sizes.get(w), w, gloss((w, p))) for (w, p) in oewn]
    entries += [
        Entry(form, pos, sizes.get(form), lemma, gloss((lemma, pos)))
        for (form, pos), lemma in inflections.items()
    ]
    entries.sort(key=lambda e: (e.word, e.pos.value))
    return entries


def write_lexicon(entries: Iterable[Entry], out: Path) -> None:
    data = "".join(format_rows(entries)).encode("utf-8")
    with out.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as f:
        f.write(data)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--cache-dir", type=Path, default=ROOT / ".cache" / "sources")
    ap.add_argument(
        "--out", type=Path, default=ROOT / "src" / "hexsieve" / "data" / "lexicon.tsv.gz"
    )
    args = ap.parse_args()

    with gzip.open(fetch(OEWN, args.cache_dir)) as f:
        oewn = parse_oewn(f)
    with fetch(ESDB, args.cache_dir).open(encoding="utf-8") as f:
        entries = build_entries(oewn, parse_esdb(f))
    write_lexicon(entries, args.out)
    sized = sum(e.size is not None for e in entries)
    inflected = sum(e.inflected for e in entries)
    print(
        f"wrote {args.out}: {len(entries)} entries "
        f"({inflected} inflected forms, {sized} with size)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
