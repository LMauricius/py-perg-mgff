# Py-PERG

**P**arser **E**nvironment **R**e**g**enerator, in **Py**thon.

Py-PERG reads grammars written in MGFF and generates the lexers and parsers they
describe. The notation is documented in [Docs/mgff-specification.md](Docs/mgff-specification.md),
and the tool itself in [Docs/py-perg.md](Docs/py-perg.md).

## Status

Early skeleton. The MGFF lexical layer (Part 1) and the grammar semantics
(Part 2: scopes, targets, macros) are implemented; the built-in constructs of
Part 3 and the code generators are still stubs.

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
pyperg --help
```
