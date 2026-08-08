# Py-PERG

**P**arser **E**nvironment **R**e**g**enerator, in **Py**thon.

Py-PERG reads grammars written in MGFF and generates the lexers and parsers they
describe. The notation is documented in [Docs/mgff-specification.md](Docs/mgff-specification.md),
and the tool itself in [Docs/py-perg.md](Docs/py-perg.md).

## Generators

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

## Examples

```sh
pyperg check tests/fixtures/calc.mgff # validate a grammar file
pyperg debug tests/fixtures/calc.mgff # show the scopes, targets and macros it defines
pyperg generate --list                # list the available generator backends
pyperg generate tests/fixtures/kate.mgff -g kate -o out/
pyperg --help
```
