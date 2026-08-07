# Py-PERG

**P**arser **E**nvironment **R**e**g**enerator, in **Py**thon.

Py-PERG reads grammars written in MGFF and generates the lexers and parsers they
describe. The notation is documented in [Docs/mgff-specification.md](Docs/mgff-specification.md),
and the tool itself in [Docs/py-perg.md](Docs/py-perg.md).

## Status

The front end is complete: the MGFF lexical layer (Part 1), the grammar
semantics (Part 2: scopes, targets, macros) and the built-in constructs of
Part 3 (item shapes, character sets, expansion) all resolve into the model the
backends read.

| Backend    | What it writes                                                                                                                |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `kate`     | A KDE syntax definition, also read by pandoc. See [Docs/kate-generator.md](Docs/kate-generator.md).                           |
| `textmate` | A TextMate grammar, packaged as a Visual Studio Code extension. See [Docs/textmate-generator.md](Docs/textmate-generator.md). |
| `antlr`    | A combined ANTLR 4 grammar, lexer and parser in one `.g4`. See [Docs/antlr-generator.md](Docs/antlr-generator.md).            |
| `regex`    | One regular expression, starting from the `Match` macro. See [Docs/regex-generator.md](Docs/regex-generator.md).              |
| `dump`     | The resolved grammar as plain text, for inspection.                                                                           |
| `python`   | Not written yet.                                                                                                              |

## Install

```sh
pip install -e ".[dev]"
```

## Use

```sh
pyperg lex tests/fixtures/calc.mgff   # show the lexical structure of a grammar file
pyperg parse tests/fixtures/calc.mgff # show the scopes, targets and macros it defines
pyperg check tests/fixtures/calc.mgff # validate it
pyperg generate --list                # list the available generator backends
pyperg generate tests/fixtures/kate.mgff -g kate -o out/
pyperg --help
```
