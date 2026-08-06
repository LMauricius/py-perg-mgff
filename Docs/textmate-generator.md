# The TextMate generator

```
pyperg generate mygrammar.mgff -g textmate -o out/
```

This backend writes a **TextMate grammar**: the format Visual Studio Code
highlights with, and the one Sublime Text, Zed, shiki and GitHub's linguist read
too. VS Code's engine reads nothing else — there is no way to hand it a KDE
syntax definition, and a language server does not replace a grammar, since
semantic tokens refine a highlighting that must already exist.

Highlighting is only part of what VS Code calls language support, so one grammar
gives a folder that is a working extension:

```
out/
├── package.json                    what the language is called, and what it owns
├── language-configuration.json     brackets, folding, auto-closing, comments
└── syntaxes/
    └── Toy.tmLanguage.json         the grammar itself
```

Try it without installing anything:

```sh
code --extensionDevelopmentPath=$PWD/out sample.toy
```

or copy the folder into `~/.vscode/extensions/` to keep it. A project that only
wants the grammar — to feed shiki, say — can take the one file and ignore the
other two.

The backend reads the grammar's **chain of phases**, and every phase starts at a
macro named `File`. The chain is what `post(…)` on each target says, and it ends
at `Parse` — see *The phases it reads* below.

---

## How TextMate highlights

TextMate runs a stack of **patterns** over the text, one line at a time. A
`match` pattern consumes what it matched. A `begin`/`end` pattern pushes, matches
its own nested patterns until the `end` expression fires, and pops.

That is a pushdown machine over text — the same machine Kate's contexts are — so
both backends derive the machine once, from `Parse`, and differ only in how they
spell it:

| Machine | Kate | TextMate |
| --- | --- | --- |
| a context | a `<context>` | a repository entry |
| what a context colours | its `attribute` | `contentName` |
| a rule pushing a context | `context="X"` | `begin`, with nested `patterns` |
| a rule popping one | `#pop` | the `end` expression |
| a context ending at the line's end | `lineEndContext="#pop"` | `end: "$"` |
| a context carrying on to the next line | `lineEndContext="Name"` | an `end` that fires on the first line not carrying it on |
| a fixed pair that folds | `beginRegion`/`endRegion` | the pair in `language-configuration.json` |
| a marker that is a word | `WordDetect` | `\b…\b` |
| a `<list>` of keywords | `<list>` | `\b(?:a\|b\|c)\b` |

And so the same two conclusions hold:

- **The earlier phases map exactly.** A token is a regular pattern, and a
  regular pattern is precisely what a `match` matches.
- **The last phase maps closely.** Every entry holds what its place in the grammar
  reaches, so a marker is a keyword only where a line may open with one. What
  neither backend can do is reject: the output highlights and folds what your
  grammar describes, and colours malformed input all the same.

## The phases it reads

Every target names the phase it runs after, and the chain ends at `Parse`:

```mgff
t Lex (
    ...
)

t Parse (
    > post(Lex) over(tokens)
    ...
)
```

The first phase — the one with no `post` — reads the text. Each later one either
reads the text again, or reads the list an earlier phase filled with `push(…)`,
which is what `over(…)` says. A grammar of a single phase calls it `Parse`, and
becomes one flat context of the matches its `File` names.

What follows calls the first phase `Lex` and the last `Parse`, which is the usual
arrangement; nothing but the last name is fixed.

**What `over(…)` changes** is what a terminal of the later phase means. Where a
phase reads text, `\(` is that character; where it reads a list, it is *the match
whose class is `\(`*. So the earlier phase names what it produces —

```mgff
d LParen = \(
        > class(\() style(Normal) push(tokens)
```

— and the later phase goes on writing `\( Expr \)`, meaning the token. A
terminal naming a class nothing pushes is reported, which is what catches the
class misspelled on either side.

## The first phase

`File` lists the tokens in the order they should be tried:

```mgff
t Lex (
    d Digit = 0-9
    d Int   = ( Digit )+
            > style(DecVal)

    d File = ( (Space)/(Comment)/(Keyword)/(Int)/(Ident) )*
)
```

Mind the spelling of the choice: it carries no whitespace around its separator,
since a space there would split it into separate items.

**Each token becomes a repository entry of its own**, included wherever it may
appear — `tokens` for a grammar of a single phase, and every context that reaches
it once there are several:

```json
"tokens": {
  "patterns": [{ "include": "#space" }, { "include": "#int" }]
},
"int": {
  "name": "constant.numeric.integer.toy",
  "match": "[0-9]+"
}
```

Splitting them up costs nothing at run time and makes the output worth reading —
and worth editing, if you ever need to hand-tune one pattern.

**Order is yours.** TextMate takes the first pattern that matches at a position,
so the order in `File` is how you say that a keyword beats an identifier.

**Only what `File` names becomes a pattern.** `Digit` above is a helper: it is
inlined into the expression for `Int` and never tried on its own.

A `Lex` production that reaches itself is an error, because a `match` is an
expression and an expression cannot recurse. Nesting belongs to `Parse`.

## The last phase

`File` is the starting production, and from it the backend derives the machine:
a set of contexts, where a context is *a place a line may begin* and holds the
rules its place in the grammar reaches — and nothing else.

A production becomes a **span** when it opens with a fixed character and either
closes with one or runs to a line break; a **token** when it carries a `style`
and has a regular form; and is **transparent** otherwise, its parts belonging to
whoever reached it.

```mgff
t Parse (
    d Definition = DefMarker WS Head Gap EqualsMarker Items NL
    d Comment    = CommentMarker Items NL
                 > style(Comment)
    d Group      = \\( Items \\)
    d Line       = (Definition)/(Comment)
    d File       = ( (Line)/(NL) )*
)
```

A span becomes a `begin`/`end` entry. Where it ends is the interesting part, and
there are three answers:

```json
"group":   { "begin": "\\(", "end": "\\)" },
"comment": { "begin": "#",  "end": "$", "contentName": "comment.toy" },
"definition": { "begin": "\\bd\\b", "end": "^(?!\\s*(?:\\||/|>|#)|\\s*$)" }
```

- a **closing character**, which is also the pair VS Code folds and auto-closes;
- the **end of the line**, for a role that covers one line;
- the **first line that does not carry the role on**, for one that reaches
  further — a definition and its `|`, `/` and `>` lines.

The last is a zero-width `end` anchored at a line's start, not a `while`. A
`while` is tested at the start of every line whatever is open at the time, and
would cut a group that spans lines in half; an `end` waits until the spans inside
have closed, which is what the machine describes and what Kate does.

**`contentName` is how a comment colours its body.** The scope on the entry
itself (`meta.<name>`) says what the region *is*; `contentName` colours what it
holds, so a group nested inside a comment is still comment-coloured.

**Every token is an entry of its own**, included wherever it is reachable rather
than written out again in each entry that can reach it. Where the same macro is
reached with different styles — a name is a name in a body and an attribute on
an attribute line — each gets an entry and a scope of its own.

Since a context holds only what it reaches, **`Parse` names every token it wants
coloured**, the ones a parser would skip among them:

```mgff
d Skipped = Space
          / Comment
```

A grammar of a single phase is a machine of one context: `tokens`, built straight
from the order `File` names. A target that is on no chain — one nothing runs
after, and that runs after nothing — is reported: it would never run.

## Scope names

A TextMate grammar says what a token *is* by giving it a **scope name**: a dotted
path such as `keyword.control.toy`. A theme matches a scope by prefix and
colours the longest prefix it knows, which is why the path runs general to
specific and ends in the language's own identifier — so two languages that both
have keywords can still be themed apart.

The `style`, `class` and `autoclass` attributes are exactly the ones the Kate backend
reads, and mean the same thing; only the spelling of the result differs. See
[the Kate generator's documentation](kate-generator.md#attributes) for
`style`, `class`, `autoclass` and named attribute lists.

| `style` | Scope prefix | | `style` | Scope prefix |
| --- | --- | --- | --- | --- |
| `Normal` | *(none)* | | `DataType` | `storage.type` |
| `Keyword` | `keyword` | | `DecVal` | `constant.numeric.integer` |
| `Function` | `entity.name.function` | | `BaseN` | `constant.numeric.other` |
| `Variable` | `variable.other` | | `Float` | `constant.numeric.float` |
| `ControlFlow` | `keyword.control` | | `Constant` | `constant.language` |
| `Operator` | `keyword.operator` | | `Comment` | `comment` |
| `BuiltIn` | `support.function.builtin` | | `Documentation` | `comment.block.documentation` |
| `Extension` | `support.other` | | `Annotation` | `entity.name.function.decorator` |
| `Preprocessor` | `meta.preprocessor` | | `CommentVar` | `comment.block.documentation.variable` |
| `Attribute` | `entity.other.attribute-name` | | `RegionMarker` | `comment.other.region` |
| `Char` | `string.quoted.single` | | `Information` | `comment.other.information` |
| `SpecialChar` | `constant.character.escape` | | `Warning` | `invalid.deprecated` |
| `String` | `string.quoted.double` | | `Alert` | `invalid.illegal.alert` |
| `VerbatimString` | `string.quoted.other` | | `Error` | `invalid.illegal.error` |
| `SpecialString` | `string.interpolated` | | `Others` | `entity.other` |
| `Import` | `keyword.control.import` | | | |

**`Normal` is no scope at all.** Unmatched text in TextMate already shows in the
editor's default colour, so a pattern that names nothing is exactly right for
whitespace and punctuation. Where Kate has to say `dsNormal`, this says nothing.

**Qualifiers.** The style a theme knows contributes the prefix, and
every other class follows as a segment of its own — the same idea as Kate's
dotted itemData name:

```mgff
d Number = ( Digit )+ ( . ( Digit )+ )?
        > style(Float Literal)
```

```json
"name": "constant.numeric.float.literal.toy"
```

A theme that only knows `constant.numeric` colours it as a number; one that
wants to pick out your literals can match the whole path. A class naming no
known prefix still becomes a segment, so `style(Keyword Mine)` gives
`keyword.mine.toy`.

---

## Matching characters

There is one way to match text — an [Oniguruma][oniguruma] regular expression —
so there is no table of rules to choose from and no reason to break a production
into several patterns. A production becomes **one** expression, which is both
the fastest thing TextMate can do and the most readable output.

Character sets and Unicode categories work exactly as they do for Kate:

| Written | Emitted |
| --- | --- |
| `a` | `a` |
| `0-9` | `[0-9]` |
| `a-z\|A-Z\|_` | `[a-zA-Z_]` |
| `Lu` | `\p{Lu}` |
| `Letter\|Decimal_Number\|_` | `[\p{L}\p{Nd}_]` |

### Word boundaries

Kate's `keyword` and `WordDetect` rules only match between word boundaries.
TextMate has no such rule, so a production whose alternatives are **all plain
words** is wrapped in `\b…\b`:

```mgff
d Keyword = l e t
          | i f
          | e l s e
          | w h i l e
        > style(Keyword)
```

```json
"match": "\\b(?:while|else|let|if)\\b"
```

Without the boundaries the `if` of `iffy` would be coloured as a keyword. Unlike
Kate this applies to a single-word production too, since `\b` costs nothing
where Kate would have had to pay for a slower rule.

### Choice and preference

Regular expressions take the first alternative that succeeds, which is MGFF's
`/`. For `|`, whose match is the longest, the options are ordered longest fixed
option first — exact whenever the options have fixed lengths, which is the usual
case of `<=` before `<`, and an approximation otherwise. Note above that the
boundaries also repair an order-based choice: `\b(?:if|iffy)\b` still matches
`iffy` whole, because `if` cannot end in the middle of a word.

---

## The extension around the grammar

### Brackets come from the grammar

VS Code folds, matches and auto-closes by the pairs in
`language-configuration.json` — **not** by anything in the TextMate grammar. So
the bracketing productions reach both files: the grammar, as the spans they
highlight, and the configuration, as the pairs the editor folds:

```json
{
  "brackets": [["(", ")"]],
  "autoClosingPairs": [{ "open": "(", "close": ")" }],
  "surroundingPairs": [["(", ")"]]
}
```

This is why `Parse` is worth writing even though its highlighting contribution
is modest: folding and bracket matching come out of it for free.

### Comment markers are not guessed

Comment toggling (<kbd>Ctrl</kbd>+<kbd>/</kbd>) needs a marker, and the backend
will not derive one from a `Comment` production. Its leading literal looks like
a line-comment marker and frequently is not — a block comment opens the same way
— and toggling with the wrong marker damages a file. Say so instead:

```mgff
> lineComment(#) blockComment(#{ #})
```

### Describing the language

The attributes at the top of the file — the `>` lines above its first definition
— fill in the manifest. Most of it is shared with the Kate backend, so one grammar can describe itself once
and generate both.

| Attribute | Default |
| --- | --- |
| `name` | The grammar file's name, in Pascal case. Also names the grammar file. |
| `id` | `name` split into words and joined with `-`, in lower case, so `MyToy` gives `my-toy`. Every scope name ends in it. |
| `scope` | `source.<id>`. A grammar describing markup should say `text.<id>` instead. |
| `extensions` | `*.<id>`. Written as globs, as Kate wants them, and rewritten to `.toy` for VS Code. |
| `version` | `0.0.1`. A manifest needs a semantic version, so a plain `version(1)` written for Kate is padded out to `1.0.0` rather than rejected. |
| `description` | `<name> language support.` |
| `mimetype`, `publisher`, `license` | Left out. |
| `lineComment`, `blockComment` | Left out; see above. |

`section`, `kateversion`, `priority` and the deliminator settings are Kate's
alone and are ignored here.

---

## A worked example

`tests/fixtures/textmate.mgff` is the same small language `kate.mgff` describes,
plus the settings only an editor extension needs. Generating from it gives:

```json
{
  "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
  "name": "Toy",
  "scopeName": "source.toy",
  "fileTypes": [
    "toy"
  ],
  "patterns": [
    {
      "include": "#grammar"
    }
  ],
  "repository": {
    "grammar": {
      "patterns": [
        {
          "include": "#atom"
        },
        {
          "include": "#comment"
        },
        {
          "include": "#keyword"
        },
        {
          "include": "#number"
        },
        {
          "include": "#ident"
        },
        {
          "include": "#space"
        },
        {
          "include": "#op"
        }
      ]
    },
    "atom": {
      "name": "meta.atom.toy",
      "begin": "\\(",
      "beginCaptures": {
        "0": {
          "name": "punctuation.section.atom.begin.toy"
        }
      },
      "end": "\\)",
      "endCaptures": {
        "0": {
          "name": "punctuation.section.atom.end.toy"
        }
      },
      "patterns": [
        {
          "include": "#atom"
        },
        {
          "include": "#comment"
        },
        {
          "include": "#keyword"
        },
        {
          "include": "#number"
        },
        {
          "include": "#ident"
        },
        {
          "include": "#space"
        },
        {
          "include": "#op"
        }
      ]
    },
    "comment": {
      "name": "comment.toy",
      "match": "#[\\p{L}\\p{Nd} \\t]*"
    },
    "keyword": {
      "name": "keyword.toy",
      "match": "\\b(?:while|else|let|if)\\b"
    },
    "number": {
      "name": "constant.numeric.float.toy",
      "match": "[0-9]+(?:\\.[0-9]+)?"
    },
    "ident": {
      "name": "variable.other.toy",
      "match": "[\\p{L}_][\\p{L}\\p{Nd}_]*"
    },
    "space": {
      "match": "[ \\t]+"
    },
    "op": {
      "name": "keyword.operator.toy",
      "match": "(?:<=|>=|==|\\+|-|\\*|=)"
    }
  }
}
```

Reading it back against the grammar: the four keywords became one bounded
alternation, the length-based operators put their two-character forms first,
`class(Number Literal) style(Float)` scoped the number as a float while naming
what it is, `autoclass` classed `Comment` by its own name, `style(Normal)` left
`Space` and the parentheses unscoped, and the bracketing `Atom` production became
a span that nests — and a bracket pair that folds. `Parse` is `over(tokens)`, so
its `\( Expr \)` found `LParen` and `RParen` by the classes they carry.

---

## Limitations

- **`Parse` output does not validate.** It highlights and folds what your
  grammar describes; a grammar that accepts only well-formed input still colours
  malformed input.
- **A context holds what it reaches.** A token `Parse` never names is never
  matched, which is why a grammar written for a highlighter names the tokens a
  parser would skip.
- **A line role ends where the next line says.** A definition ends at the first
  line beginning with none of its continuation markers; whether that line
  *should* have followed is not something a highlighter can see.
- **No recursive tokens.** A `Lex` production that reaches itself is rejected,
  because a `match` is an expression. Nesting has to be written as a bracketing
  `Parse` production.
- **One line at a time.** A `match` pattern is matched within a line, so a token
  cannot span one. A construct that does has to be written as a span — a
  production opening and closing with fixed characters — which is what
  `begin`/`end` is for.
- **Longest-match choice is ordered, not measured.** For `|` the options are
  emitted longest fixed option first, which is exact for fixed-length options
  and an approximation otherwise.
- **No case-insensitive matching.** MGFF has no spelling for it.
- **A token that can match nothing is left out**, with a note on standard error.
  A zero-width pattern makes no progress and so can never highlight anything.
- **Nothing is skipped.** As with Kate, `skip` has no meaning: an editor shows
  every character, and a token styled `Normal` is what "invisible" means here.

[oniguruma]: https://github.com/kkos/oniguruma/blob/master/doc/RE
