from __future__ import annotations

import hashlib
import io
from pathlib import Path

import build_lexicon
import pytest
from build_lexicon import (
    EsdbLine,
    Source,
    build_entries,
    fetch,
    parse_esdb,
    parse_oewn,
    write_lexicon,
)

from hexsieve.lexicon import Entry, LexiconError, Pos, format_rows, parse_rows, read_lexicon

ESDB_SAMPLE = """\
not a data line
[12dicts]: sizeless <n>
50 [12dicts]: A Bv C: abettor <n>: abettors
50 [12dicts]: _~: abbe <n>: abbes

60 [12dicts]: _: nonoccurrence <n>
60 [12dicts]: _x: nonoccurence <n>
60 [12dicts]: _: - <n>: nonoccurrences
60 [12dicts]: _x: - <n>: nonoccurences

35 [12dicts]: diss <v>: dissed, dissing, (disses | x: dises)
35 [12dicts]: appendix <n>: (appendices | v: appendixes)
50 [12dicts]: _V {1}: bogie <n> {:2}: bogies, bogie's

35 [12dicts] 85 [ukacd]: aid <n>
35 [12dicts] 85 [ukacd]: - <n>: aid's
35 [12dicts] 85 [ukacd]: - <n>: aids

35 [] [12dicts] [5d+2a] 80 [enable]: aid <v>
35 [12dicts]: - <v>: aided, aiding, aids

85 [ukacd]: !abject <m>: abjected, abjecting, abjects

35 [12dicts]: - <n>: orphaned

35 [12dicts]: - <v>: (abode | ~: abided), abiding, abides # comment
70 [moby]: Aida <n/person>: Aida's

60 [12dicts]: Bob <v>: bobbed, bobbing
60 [12dicts]: - <v>: bobs

70 [3of6]: A B: -draught <n> {british: game of checkers}: draughts

35 [12dicts]: A Bv: gibe <v> {insult}
35 [12dicts]: Av B: jibe <v> {insult}
35 [12dicts]: A Bv: - <v> {insult}: gibed, gibing, gibes
35 [12dicts]: Av B: - <v> {insult}: jibed, jibing, jibes

35 [12dicts]: big <aj>
## a comment line inside a group
35 [12dicts]: - <aj>: bigger, biggest
70 [moby]: big top <n>
70 [moby]: - <n>: bigtops
"""


def esdb_lines() -> list[EsdbLine]:
    return list(parse_esdb(io.StringIO(ESDB_SAMPLE)))


def esdb_words() -> set[str]:
    return {w for x in esdb_lines() for w in (x.lemma, *x.derived)}


def test_esdb_continuation_lines_inherit_the_group_lemma() -> None:
    lines = esdb_lines()
    assert EsdbLine(35, "aid", "v", ("aided", "aiding", "aids")) in lines
    assert EsdbLine(35, "aid", "n", ("aids",)) in lines  # possessive aid's is not a plain word


def test_esdb_size_ignores_digits_inside_source_tags() -> None:
    (line,) = [x for x in esdb_lines() if x.lemma == "aid" and x.pos == "v" and not x.derived]
    assert line.size == 35  # not 2 or 5 from the [5d+2a] tag


def test_esdb_strips_annotations_and_keeps_annotated_lemmas() -> None:
    lines = esdb_lines()
    assert EsdbLine(85, "abject", "m", ("abjected", "abjecting", "abjects")) in lines


def test_esdb_continuation_after_blank_line_has_no_lemma_and_is_skipped() -> None:
    words = esdb_words()
    assert "orphaned" not in words
    assert "abided" not in words  # its group started with a blank line, not a lemma


def test_esdb_skips_spelling_variant_prefixes() -> None:
    lines = esdb_lines()
    assert EsdbLine(50, "bogie", "n", ("bogies",)) in lines  # variant {N} and sense note {..}
    assert EsdbLine(50, "abettor", "n", ("abettors",)) in lines
    assert EsdbLine(50, "abbe", "n", ("abbes",)) in lines


def test_esdb_drops_invalid_spellings_and_unparsable_lines() -> None:
    assert esdb_words().isdisjoint({"nonoccurence", "nonoccurences", "sizeless", "not"})


def test_esdb_valid_continuation_after_an_invalid_line_keeps_the_group_lemma() -> None:
    assert EsdbLine(60, "nonoccurrence", "n", ("nonoccurrences",)) in esdb_lines()


def test_esdb_bracketed_variants_drop_markers_and_invalid_forms() -> None:
    lines = esdb_lines()
    assert EsdbLine(35, "diss", "v", ("dissed", "dissing", "disses")) in lines
    assert EsdbLine(35, "appendix", "n", ("appendices", "appendixes")) in lines
    assert esdb_words().isdisjoint({"x", "v", "dises"})


def test_esdb_skips_capitalised_lemmas_with_their_lowercase_forms() -> None:
    words = esdb_words()
    assert words.isdisjoint({"Aida", "Bob", "bobbed", "bobbing", "bobs"})


OEWN_SAMPLE = b"""<?xml version="1.0"?>
<LexicalResource><Lexicon id="oewn">
<LexicalEntry id="e1"><Lemma writtenForm="aid" partOfSpeech="v"/>
  <Sense id="s1" synset="v1"/><Sense id="s7" synset="v1b"/><Sense id="s2" synset="v2"/>
  <Sense id="s3" synset="v3"/>
</LexicalEntry>
<LexicalEntry id="e2"><Lemma writtenForm="aided" partOfSpeech="s"/>
  <Sense id="s4" synset="a1"/></LexicalEntry>
<LexicalEntry id="e3"><Lemma writtenForm="first aid" partOfSpeech="n"/>
  <Sense id="s5" synset="n1"/></LexicalEntry>
<LexicalEntry id="e4"><Lemma writtenForm="Aida" partOfSpeech="n"/>
  <Sense id="s6" synset="n1"/></LexicalEntry>
<Synset id="v1"><Definition>give help</Definition></Synset>
<Synset id="v1b"><Definition>give  help</Definition></Synset>
<Synset id="v2"><Definition>improve   the condition</Definition></Synset>
<Synset id="v3"><Definition>third sense</Definition></Synset>
<Synset id="a1"><Definition>having help</Definition></Synset>
<Synset id="n1"><Definition>unused</Definition></Synset>
</Lexicon></LexicalResource>
"""


def test_oewn_keeps_single_lowercase_words_and_first_two_distinct_glosses() -> None:
    # v1b repeats v1's definition (after whitespace folding), so v2 is the second gloss.
    oewn = parse_oewn(io.BytesIO(OEWN_SAMPLE))
    assert oewn == {
        ("aid", Pos.VERB): ["give help", "improve the condition"],
        ("aided", Pos.ADJ): ["having help"],
    }


def test_inflections_are_added_only_for_lemmas_oewn_has_in_that_pos() -> None:
    oewn = {("aid", Pos.VERB): ["give help"], ("aided", Pos.ADJ): ["having help"]}
    esdb = [
        EsdbLine(35, "aid", "v", ("aided", "aiding")),
        EsdbLine(35, "aid", "n", ("aids",)),  # OEWN has no noun "aid" here
    ]
    entries = {(e.word, e.pos): e for e in build_entries(oewn, esdb)}
    assert set(entries) == {
        ("aid", Pos.VERB),
        ("aided", Pos.ADJ),
        ("aided", Pos.VERB),
        ("aiding", Pos.VERB),
    }
    assert entries[("aided", Pos.VERB)] == Entry("aided", Pos.VERB, 35, "aid", "give help")
    assert entries[("aided", Pos.ADJ)].lemma == "aided"


def test_noun_verb_m_lines_add_their_forms_as_verbs_only() -> None:
    oewn = {("ahh", Pos.NOUN): ["g"], ("ahh", Pos.VERB): ["g"]}
    entries = build_entries(oewn, [EsdbLine(80, "ahh", "m", ("ahhed", "ahhing", "ahhs"))])
    assert {(e.word, e.pos) for e in entries if e.inflected} == {
        ("ahhed", Pos.VERB),
        ("ahhing", Pos.VERB),
        ("ahhs", Pos.VERB),
    }


def test_adjective_adverb_a_lines_add_their_forms_to_both() -> None:
    oewn = {("fast", Pos.ADJ): ["g"], ("fast", Pos.ADV): ["g"]}
    entries = build_entries(oewn, [EsdbLine(35, "fast", "a", ("faster", "fastest"))])
    assert {(e.word, e.pos) for e in entries if e.inflected} == {
        ("faster", Pos.ADJ),
        ("faster", Pos.ADV),
        ("fastest", Pos.ADJ),
        ("fastest", Pos.ADV),
    }


def test_lines_with_unmapped_pos_give_sizes_but_no_forms() -> None:
    oewn = {("aid", Pos.NOUN): ["g"], ("aid", Pos.VERB): ["g"]}
    entries = build_entries(oewn, [EsdbLine(35, "aid", "n_v", ("aided",))])
    assert {(e.word, e.pos, e.size) for e in entries} == {
        ("aid", Pos.NOUN, 35),
        ("aid", Pos.VERB, 35),
    }


def test_a_form_shared_by_two_lemmas_gets_a_row_for_each() -> None:
    oewn = {("base", Pos.NOUN): ["a support"], ("basis", Pos.NOUN): ["a foundation"]}
    # basis comes first in the input; rows are still ordered by lemma
    esdb = [EsdbLine(35, "basis", "n", ("bases",)), EsdbLine(35, "base", "n", ("bases",))]
    rows = [(e.word, e.lemma, e.gloss) for e in build_entries(oewn, esdb) if e.inflected]
    assert rows == [("bases", "base", "a support"), ("bases", "basis", "a foundation")]


def test_esdb_data_above_size_80_is_ignored() -> None:
    oewn = {("abject", Pos.VERB): ["cast down"]}
    entries = build_entries(oewn, [EsdbLine(85, "abject", "m", ("abjected",))])
    assert entries == [Entry("abject", Pos.VERB, None, "abject", "cast down")]


def test_word_size_is_its_smallest_size_on_any_line() -> None:
    oewn = {("aid", Pos.VERB): ["g"], ("aid", Pos.NOUN): ["g"]}
    esdb = [EsdbLine(60, "aid", "n", ()), EsdbLine(35, "aid", "v", ())]
    assert {e.size for e in build_entries(oewn, esdb)} == {35}


def test_lexicon_rows_round_trip() -> None:
    entries = [
        Entry("aided", Pos.VERB, 35, "aid", "give help"),
        Entry("acold", Pos.ADJ, None, "acold", "x"),
        Entry("zero", Pos.NOUN, 0, "zero", "x"),  # sizes come from r"\d+": never negative
        Entry("abc", Pos.NOUN, 80, "abc", ""),  # OEWN entry with no definition
    ]
    assert list(parse_rows(format_rows(entries))) == entries


def test_lexicon_file_round_trips_through_the_production_reader(tmp_path: Path) -> None:
    # A carriage return is not a row separator: only "\n" ends a row, on both sides.
    entries = [Entry("abc", Pos.NOUN, 35, "abc", gloss) for gloss in ("", "   ", "a\rb", "x | y")]
    entries += [Entry(f"abc{p.value}", p, None, "abc", "g") for p in Pos]  # every POS code
    out = tmp_path / "lexicon.tsv.gz"
    write_lexicon(entries, out)
    assert read_lexicon(out.read_bytes()) == tuple(entries)


@pytest.mark.parametrize(
    "entry",
    [
        Entry("ace", Pos.NOUN, 35, "ace", "a\tb"),
        Entry("ace", Pos.NOUN, 35, "ace", "a\nb"),
        Entry("a\tce", Pos.NOUN, 35, "ace", "g"),
        Entry("ace", Pos.NOUN, 35, "a\nce", "g"),
    ],
)
def test_lexicon_writer_rejects_separators_in_fields(entry: Entry) -> None:
    with pytest.raises(LexiconError, match="tab or newline"):
        list(format_rows([entry]))


def test_build_entries_strips_tabs_from_glosses() -> None:
    (entry,) = build_entries({("ace", Pos.NOUN): ["a\tb"]}, [])
    assert entry.gloss == "a b"


HEADER = "word\tpos\tsize\tlemma\tgloss\n"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("word\tpos\n", "unexpected lexicon header"),
        (HEADER + "ace\tn\t35\tace\n", "want 5 fields"),
        (HEADER + "ace\tq\t35\tace\tg\n", "line 2"),
        (HEADER + "ace\tn\tbig\tace\tg\n", "line 2"),
    ],
)
def test_lexicon_reader_rejects_malformed_rows(text: str, message: str) -> None:
    with pytest.raises(LexiconError, match=message):
        list(parse_rows(io.StringIO(text)))


def test_esdb_sense_note_may_contain_the_field_separator() -> None:
    assert EsdbLine(70, "draught", "n", ("draughts",)) in esdb_lines()


def test_esdb_continuation_belongs_to_the_lemma_with_its_spelling_prefix() -> None:
    lines = esdb_lines()
    assert EsdbLine(35, "gibe", "v", ("gibed", "gibing", "gibes")) in lines
    assert EsdbLine(35, "jibe", "v", ("jibed", "jibing", "jibes")) in lines


def test_esdb_comment_line_does_not_end_a_group() -> None:
    assert EsdbLine(35, "big", "aj", ("bigger", "biggest")) in esdb_lines()


def test_esdb_unparsable_lemma_owns_its_continuation_lines() -> None:
    assert "bigtops" not in esdb_words()


def source(content: bytes = b"good") -> Source:
    """A Source pinned to the digest of `content`."""
    return Source(
        "https://example.invalid/data.txt", hashlib.sha256(content).hexdigest(), "data.txt"
    )


def serve(monkeypatch: pytest.MonkeyPatch, body: bytes | Exception) -> None:
    """Make every download return `body`, or raise it if it is an exception."""

    def urlopen(_url: str) -> io.BytesIO:
        if isinstance(body, Exception):
            raise body
        return io.BytesIO(body)

    monkeypatch.setattr(build_lexicon.urllib.request, "urlopen", urlopen)


def test_fetch_returns_a_cached_file_with_the_pinned_digest(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_bytes(b"good")
    assert fetch(source(), tmp_path) == tmp_path / "data.txt"


def test_fetch_rejects_a_cached_file_with_the_wrong_digest(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_bytes(b"tampered")
    with pytest.raises(SystemExit, match="does not match pinned"):
        fetch(source(), tmp_path)


def test_fetch_caches_a_download_with_the_pinned_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve(monkeypatch, b"good")
    assert fetch(source(), tmp_path).read_bytes() == b"good"
    assert [p.name for p in tmp_path.iterdir()] == ["data.txt"]


@pytest.mark.parametrize(
    ("body", "error"), [(b"tampered", SystemExit), (OSError("connection reset"), OSError)]
)
def test_fetch_leaves_nothing_after_a_bad_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: bytes | Exception, error: type
) -> None:
    serve(monkeypatch, body)
    with pytest.raises(error):
        fetch(source(), tmp_path)
    assert list(tmp_path.iterdir()) == []
