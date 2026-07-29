# Py-PERG

**P**arser **E**nvironment **R**e**g**enerator, in **Py**thon.

Py-PERG reads grammars written in MGFF and generates the lexers and parsers they
describe. The notation is documented in [Docs/mgff-specification.md](Docs/mgff-specification.md),
and the tool itself in [Docs/py-perg.md](Docs/py-perg.md).

## Status

Early skeleton. The MGFF lexical layer (Part 1 of the specification) is implemented;
the grammar semantics and the code generators are still stubs.

## Install

```sh
pip install -e ".[dev]"
```

## Use

```sh
pyperg lex tests/fixtures/calc.mgff   # show the lexical structure of a grammar file
pyperg generate --list                # list the available generator backends
pyperg --help
```
