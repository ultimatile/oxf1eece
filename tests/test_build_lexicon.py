from __future__ import annotations

import io

from build_lexicon import EsdbLine, build_entries, parse_esdb, parse_oewn

from hexsieve.lexicon import Entry, Pos, format_rows, parse_rows

ESDB_SAMPLE = """\
35 [12dicts] 85 [ukacd]: aid <n>
35 [12dicts] 85 [ukacd]: - <n>: aid's
35 [12dicts] 85 [ukacd]: - <n>: aids

35 [] [12dicts] [5d+2a] 80 [enable]: aid <v>
35 [12dicts]: - <v>: aided, aiding, aids

85 [ukacd]: !abject <m>: abjected, abjecting, abjects

- <n>: orphaned

35 [12dicts]: - <v>: (abode | ~: abided), abiding, abides # comment
70 [moby]: Aida <n/person>: Aida's
"""


def test_esdb_continuation_lines_inherit_the_group_lemma() -> None:
    lines = list(parse_esdb(io.StringIO(ESDB_SAMPLE)))
    assert EsdbLine(35, "aid", "v", ("aided", "aiding", "aids")) in lines
    assert EsdbLine(35, "aid", "n", ("aids",)) in lines  # possessive aid's is not a plain word


def test_esdb_size_ignores_digits_inside_source_tags() -> None:
    (line,) = [x for x in parse_esdb(io.StringIO(ESDB_SAMPLE)) if x.pos == "v" and not x.derived]
    assert line.size == 35  # not 2 or 5 from the [5d+2a] tag


def test_esdb_strips_annotations_and_keeps_annotated_lemmas() -> None:
    lines = list(parse_esdb(io.StringIO(ESDB_SAMPLE)))
    assert EsdbLine(85, "abject", "m", ("abjected", "abjecting", "abjects")) in lines


def test_esdb_continuation_after_blank_line_has_no_lemma_and_is_skipped() -> None:
    words = {w for x in parse_esdb(io.StringIO(ESDB_SAMPLE)) for w in (x.lemma, *x.derived)}
    assert "orphaned" not in words
    assert "abided" not in words  # its group started with a blank line, not a lemma


def test_esdb_skips_capitalised_lemmas() -> None:
    assert all(x.lemma != "Aida" for x in parse_esdb(io.StringIO(ESDB_SAMPLE)))


OEWN_SAMPLE = b"""<?xml version="1.0"?>
<LexicalResource><Lexicon id="oewn">
<LexicalEntry id="e1"><Lemma writtenForm="aid" partOfSpeech="v"/>
  <Sense id="s1" synset="v1"/><Sense id="s2" synset="v2"/><Sense id="s3" synset="v3"/>
</LexicalEntry>
<LexicalEntry id="e2"><Lemma writtenForm="aided" partOfSpeech="s"/>
  <Sense id="s4" synset="a1"/></LexicalEntry>
<LexicalEntry id="e3"><Lemma writtenForm="first aid" partOfSpeech="n"/>
  <Sense id="s5" synset="n1"/></LexicalEntry>
<LexicalEntry id="e4"><Lemma writtenForm="Aida" partOfSpeech="n"/>
  <Sense id="s6" synset="n1"/></LexicalEntry>
<Synset id="v1"><Definition>give help</Definition></Synset>
<Synset id="v2"><Definition>improve   the condition</Definition></Synset>
<Synset id="v3"><Definition>third sense</Definition></Synset>
<Synset id="a1"><Definition>having help</Definition></Synset>
<Synset id="n1"><Definition>unused</Definition></Synset>
</Lexicon></LexicalResource>
"""


def test_oewn_keeps_single_lowercase_words_and_first_two_glosses() -> None:
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
    ]
    assert list(parse_rows(format_rows(entries))) == entries
