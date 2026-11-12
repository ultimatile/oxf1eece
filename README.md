# hexsieve

Find English words and adjective+noun tags that can be spelled in hexadecimal digits
(hexspeak, such as `deadbeef` or `c0ffee`), with configurable letter-to-digit rules.

## Install

```sh
uv tool install git+https://github.com/ultimatile/hexsieve
```

Upgrade with `uv tool upgrade hexsieve`, uninstall with `uv tool uninstall hexsieve`.

Requires Python 3.14 or later (uv installs it if missing). `hexsieve search` also needs
[fzf](https://github.com/junegunn/fzf) on `PATH`.

## Usage

Find 8-digit adjective+noun tags made of common words:

```console
$ hexsieve tag 8 --max-size 35 --sort random --seed 7 --limit 5
1dea1dab	ideal+dab	35	i1,l1
01df1ea5	old+fleas	35	l1,o0,s5
fe11ace5	fell+aces	35	l1,s5
0be5eb00	obese+boo	35	o0,s5
5afec0b5	safe+cobs	35	o0,s5
```

The columns are the hex spelling, the words, their size (see below) and the rules used.

| Command | Prints |
| --- | --- |
| `hexsieve list` | words, as TSV: hex, word, part of speech, size, rules, definition |
| `hexsieve tag DIGITS` | adjective+noun tags whose joined hex is exactly `DIGITS` long, as TSV: hex, adj+noun, size, rules |
| `hexsieve search` | the `list` rows in fzf, with the definition in a preview pane; prints the rows you pick |
| `hexsieve rules` | the available rules and presets |

### Conversion rules

The letters a–f need no rule. Other letters are converted by named rules, grouped into
presets:

| Preset | Rules |
| --- | --- |
| `strict` | none (a–f only) |
| `classic` (default) | `o0 i1 l1 s5` |
| `leet` | `o0 i1 l1 s5 t7 g9 z2` |

Choose a preset with `--preset` and adjust it with comma-separated `--enable` / `--disable`:

```sh
hexsieve list --preset classic --enable t7 --disable l1
```

`hexsieve rules` shows every rule, including multi-letter ones such as `ate8` (with `l1`, `late` → `18`).

### Filtering and sorting

Most words have a *size* from the English Speller Database, from 35 for common words up
to 80 for rare but valid ones; the rest show an empty size and come last when sorting by
size. A tag's size is that of its rarer word, and is empty if either word has none.

| Option | Effect |
| --- | --- |
| `--max-size N` | keep words of size `N` or less; words without a size are dropped |
| `--pos noun,adj` | (`list`, `search`) keep these parts of speech: `noun`, `verb`, `adj`, `adv` |
| `--length N` | (`list`, `search`) keep `N`-digit hex spellings |
| `--sort KEY` | `tier` (by size, the default), `hex` / `-hex` (by numeric value; write `--sort=-hex`), `alpha`, `random` |
| `--seed N` | seed for `--sort random` |
| `--limit N` | print at most `N` rows |
| `--upper` | print hex in uppercase |

Inflected forms (plurals, past tenses, …) are included; their definition starts with the
base word in brackets, e.g. `[fade]` for `faded`. Different words with the same hex
spelling, such as `ball` and `bail` (`ba11`), are listed as separate rows.

## Word data

The bundled word list is derived from [Open English WordNet](https://github.com/globalwordnet/english-wordnet)
(CC BY 4.0) and the [English Speller Database](https://github.com/en-wl/wordlist)
(formerly SCOWL); attributions and licence texts are in
[`src/hexsieve/data/licenses/`](src/hexsieve/data/licenses/). To regenerate it, run
`uv run scripts/build_lexicon.py`.
