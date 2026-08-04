# The Kate generator

```
pyperg generate mygrammar.mgff -g kate -o out/
```

This backend writes a **KDE syntax definition**: the XML format that Kate,
KWrite and KDevelop read for syntax highlighting, and that pandoc reads through
skylighting when it highlights a fenced code block. One grammar gives one `.xml`
file, ready to drop into `~/.local/share/org.kde.syntax-highlighting/syntax/` or
to pass to `pandoc --syntax-definition`.

The backend reads two targets, `Lex` and `Parse`, and both start at a macro
named `File`.

---

## How Kate highlights

Kate does not parse. It runs a stack of **contexts** over the text, one line at
a time. A context is an ordered list of rules; at each position Kate tries them
in order and the first one that matches wins, colouring what it matched and
optionally pushing another context, popping back, or staying put.

```mermaid
stateDiagram-v2
    [*] --> File
    File --> Definition: <code>d</code> pushes
    Definition --> DefinitionLine: line end
    DefinitionLine --> AltLine: <code>|</code> pushes
    DefinitionLine --> [*]: any other line pops the chain
    File --> CommentLine: <code>#</code> pushes
    CommentLine --> CommentGroup: <code>(</code> pushes
    CommentLine --> [*]: line end
```

That machine reads nesting, which is why brackets and comments fold correctly in
Kate. What it cannot do is backtrack, or let a rule call itself. So:

- **`Lex` maps exactly.** A token is a regular pattern, and a regular pattern is
  precisely what a Kate rule matches.
- **`Parse` maps closely.** Every context holds what its place in the grammar
  reaches, so a marker is a keyword only where a line may open with one and a
  group holds only what its own lines may hold. What Kate still cannot do is
  reject: the output highlights and folds what your grammar describes, but a
  malformed file is coloured all the same. If you need a real parser, that is
  what the other backends are for.

---

## The `Lex` target

`File` is the starting production, and it lists the tokens in the order Kate
should try them:

```mgff
t Lex (
    d Digit = 0-9
    d Int   = ( Digit )+
            > class(DecVal)

    d File = ( (Space)/(Comment)/(Keyword)/(Int)/(Ident) )*
)
```

Mind the spelling of the choice: it carries no whitespace around its separator,
since a space there would split it into separate items.

Two things follow from writing it this way.

**Order is yours.** Kate takes the first rule that matches, so the order in
`File` is how you say that a keyword beats an identifier, or that a comment beats
an operator.

**Only what `File` names becomes a rule.** `Digit` above is a helper: it is
inlined into the expression for `Int` and never tried on its own. Nothing is
matched that the grammar did not ask for.

Inside a production, a length-based choice (`|`) is emitted longest match first,
so `<=` is tried before `<` without you having to order it by hand. An
order-based choice (`/`) is emitted as written.

A `Lex` production that reaches itself is an error: a Kate rule matches with an
expression, and an expression cannot recurse.

## The `Parse` target

`File` is the starting production here too, and from it the backend derives a
**machine**: a set of contexts, where a context is *a place a line may begin*
and holds the rules its place in the grammar reaches — and nothing else.

That last part is what makes the output context-sensitive. A marker is a keyword
where a line may open with one and ordinary text everywhere else; a group whose
lines hold no definitions holds no `d` rule; a comment stays a comment across
the lines a group inside it spans.

A production becomes one of three things:

| Interpretation | Shape | Becomes |
| --- | --- | --- |
| Span | opens with a fixed character and closes with one | a context, pushed by the opening and popped by the closing, and a region that folds |
| Span | opens with a fixed character and runs to a line break | a context, pushed by the opening and popped where the line ends |
| Token | carries a `class` and has a regular form | one rule, coloured by its classes |
| Transparent | anything else | nothing of its own; its parts belong to whoever reached it |

```mgff
t Parse (
    d Definition = DefMarker WS Head Gap EqualsMarker Items NL
    d Comment    = CommentMarker Items NL
                 > class(Comment)
    d Group      = \( Items \)
    d Line       = (Definition)/(Comment)
    d File       = ( (Line)/(NL) )*
)
```

`Definition` opens with `d` and runs to the line break, so `d` pushes a context
that pops where the line ends. `Comment` does the same and carries a class, so
everything that context holds is a comment — the lines a `Group` inside it
reaches included, since the group is a context of its own and Kate pops only the
context on top.

**A line role may reach past its first line.** A definition covers its `|`, `/`
and `>` lines, and those become a **chain**: the context of the first line names
the next in `lineEndContext`, that one loops on itself, and a line beginning with
something none of its rules knows pops the whole chain through a `lookAhead`
rule — so the scope below reads that line from its first character.

**A marker spelled as a letter matches between deliminators.** `d`, `t` and `p`
become `WordDetect` rather than `DetectChar`, so the `d` of `Digit` opens
nothing.

**`Lex` keeps two jobs**: the expression each token matches with, and the order
tokens are tried in where a context holds several. Since a context holds only
what it reaches, **`Parse` names every token it wants coloured** — the ones a
parser would skip among them:

```mgff
d Skipped = Space
          / Comment
```

A grammar with only a `Lex` target is a machine of one context, `Tokens`, built
straight from that order. A target that is neither `Lex` nor `Parse` is skipped,
with a note on standard error.

## Attributes

### `class(Class1 Class2 …)`

Kate gives every rule an *itemData*, and every itemData a **default style** —
`dsKeyword`, `dsComment`, `dsString` and so on. A theme colours the default
styles, and skylighting maps them onto pandoc's token types. The default style
is therefore the whole of what a highlighted token *means*, and `class` is how
you choose one:

```mgff
d Keyword = i f
          | e l s e
        > class(Keyword)
```

gives

```xml
<keyword String="keyword" attribute="Keyword"/>
…
<itemData name="Keyword" defStyleNum="dsKeyword"/>
```

A class is passed through as it is written, so anything in this list reaches
Kate as that exact style:

| | | | |
| --- | --- | --- | --- |
| `Normal` | `Keyword` | `Function` | `Variable` |
| `ControlFlow` | `Operator` | `BuiltIn` | `Extension` |
| `Preprocessor` | `Attribute` | `Char` | `SpecialChar` |
| `String` | `VerbatimString` | `SpecialString` | `Import` |
| `DataType` | `DecVal` | `BaseN` | `Float` |
| `Constant` | `Comment` | `Documentation` | `Annotation` |
| `CommentVar` | `RegionMarker` | `Information` | `Warning` |
| `Alert` | `Error` | `Others` | |

The match ignores capitalisation, so `class(keyword)` and `class(Keyword)` are
the same thing.

**Several classes.** Kate allows one style per rule, so when you give several,
the first one naming a default style decides the colour and all of them are
joined with `.` to name the itemData:

```mgff
d Number = ( Digit )+ ( . ( Digit )+ )?
        > class(Float Literal)
```

```xml
<itemData name="Float.Literal" defStyleNum="dsFloat"/>
```

Nothing is rejected. A class naming no default style is kept in the itemData
name and nothing more, which is enough for a Kate theme to target it by name; if
*no* class names a style, the token is `dsNormal`. This is how you keep a
distinction the default styles do not make — `class(Keyword Control)` and
`class(Keyword Modifier)` are both keywords to a theme that does not care, and
two different things to one that does.

### `autoclass`

`autoclass` asks for the class to be derived from the macro's own name, which is
usually enough:

```mgff
d Comment = # ( Anything )*
        > autoclass
```

The name is tried four ways, in order, and the first that answers wins:

1. **The name is a default style.** `Comment`, `Keyword`, `String` — matched
   ignoring capitalisation.
2. **The name is a known synonym.** The table below.
3. **A word of the name is one of the above.** The name is split at separators
   and at case changes, and the **last** matching word wins, because the last
   word says what the token is and the ones before it only qualify it. So
   `LineComment` is a `Comment` and `HexNumber` is whatever `Number` is.
4. **Nothing matched.** The token is `Normal`, and a line goes to standard error
   naming the macro, so you know to write an explicit `class` for it.

The synonyms:

| Style | Names |
| --- | --- |
| `Variable` | `ident`, `identifier`, `name`, `symbol`, `var` |
| `DecVal` | `number`, `num`, `int`, `integer`, `digit`, `digits` |
| `Float` | `real`, `double` |
| `BaseN` | `hex`, `oct`, `octal`, `bin`, `binary` |
| `String` | `str`, `text`, `quoted` |
| `Char` | `character`, `charlit` |
| `SpecialChar` | `escape` |
| `Keyword` | `kw`, `keywords`, `reserved`, `tag` |
| `BuiltIn` | `builtin` |
| `DataType` | `type`, `datatype` |
| `Function` | `func`, `fun`, `call` |
| `Constant` | `const`, `literal` |
| `ControlFlow` | `flow`, `control` |
| `Operator` | `op`, `ops` |
| `Comment` | `comments`, `line_comment`, `block_comment` |
| `Documentation` | `doc`, `docs` |
| `Preprocessor` | `pragma`, `directive` |
| `Import` | `include`, `use` |
| `Attribute` | `attr` |
| `Others` | `label` |
| `Normal` | `punct`, `punctuation`, `space`, `spaces`, `whitespace`, `ws`, `newline`, `lparen`, `rparen`, `lbrace`, `rbrace`, `lbracket`, `rbracket`, `comma`, `semicolon` |

Prefer `autoclass` while a grammar is taking shape, and an explicit `class` for
anything the derivation gets wrong — an explicit `class` is never second-guessed.

A production carrying neither attribute is `Normal`.

### Naming a list of attributes

An attribute-only macro is a named list of attributes, and naming it among
another macro's attributes splices it in. This is the tidy way to give many
tokens the same treatment:

```mgff
d Highlighted > autoclass

t Lex (
    d Ident = Letter ( AlNum )*
        > Highlighted
)
```

### `token`, `skip` and `string`

These are the attributes the other backends use, and the Kate backend passes
over them. It is worth being clear why `skip` in particular does nothing here:
Kate has no notion of discarding a token, since every character of a document
must be coloured as *something*. A skipped token is still highlighted — usually
as `Normal`, which is what makes it invisible.

### Describing the language

A file-scope attribute-only macro named `Language` fills in the root element:

```mgff
d Language > name(Toy) section(Sources) extensions(*.toy) mimetype(text/x-toy)
```

| Attribute | Default |
| --- | --- |
| `name` | The grammar file's name, in Pascal case. Also names the output file. |
| `section` | `Sources` |
| `extensions` | `*.<name in lower case>` |
| `version` | `1` |
| `kateversion` | `5.79` |
| `mimetype`, `author`, `license`, `priority` | Left out. |
| `casesensitive` | `1` |
| `weakDeliminator`, `additionalDeliminator` | Left out. |

An attribute written with several arguments joins them with a space, so
`extensions(*.toy *.t)` reaches Kate as the list it looks like.

---

## Matching characters

Kate offers a dozen ways to match text and tries every rule of a context at
every position, so the choice matters: `DetectChar` compares one character,
while `RegExpr` starts an expression engine. The backend walks this table top to
bottom and takes the first row that fits.

| Rule | Chosen for | Example |
| --- | --- | --- |
| `DetectSpaces` | A run of whitespace. | `( \_\|\t )+` |
| `DetectChar` | One fixed character. | `+` |
| `Detect2Chars` | Two fixed characters. | `< =` |
| `WordDetect` | A longer fixed string, beginning and ending inside a word. | `t h e n` |
| `StringDetect` | Any other fixed string. | `- - >` |
| `AnyChar` | One character out of a handful of fixed ones. | `+\|-\|*` |
| `keyword` | A choice of fixed words, collected into a `<list>`. | `i f \| e l s e` |
| `RegExpr` | Anything else with a regular form. | `( Digit )+` |

`RangeDetect` is deliberately not used. It matches everything between a fixed
opening and closing character, which is wider than any grammar that spells out
what may appear between them, and quietly widening a rule is worse than paying
for an expression.

### Why fusing matters

MGFF has no multi-character literal: a part of a character set is one character,
so the two-character operator `<=` is written as the two items `< =`. Before
choosing a rule the backend **fuses** runs of single-character nodes back into
strings, which is what makes everything from `DetectChar` to `StringDetect`
reachable at all. Without it, `< =` would become the expression `<=`, and a
keyword list would never be recognised.

### Character sets and Unicode

A character set becomes a character class, and a Unicode category becomes
`\p{…}`, which both Kate's engine and skylighting's understand:

| Written | Emitted |
| --- | --- |
| `a` | `a` |
| `0-9` | `[0-9]` |
| `a-z\|A-Z\|_` | `[a-zA-Z_]` |
| `Lu` | `\p{Lu}` |
| `Letter\|Decimal_Number\|_` | `[\p{L}\p{Nd}_]` |

Both spellings of a category work — the two-letter abbreviation `Lu` and the
long form `Uppercase_Letter` — as do the group names `Letter`, `Number`, `Mark`,
`Punctuation`, `Symbol`, `Separator` and `Other`.

### Choice and preference

Regular expressions take the first alternative that succeeds, which is MGFF's
`/`. For `|`, whose match is the longest, the options are ordered longest fixed
option first. That is exact whenever the options have fixed lengths — the usual
case, `<=` before `<` — and an approximation otherwise. The same ordering is
applied when a production becomes several rules, since Kate too takes the first
rule that matches.

---

## A worked example

`tests/fixtures/kate.mgff` is a small language written to exercise all of the
above. Generating from it:

```
pyperg generate tests/fixtures/kate.mgff -g kate -o out/
```

gives `out/Toy.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE language SYSTEM "language.dtd">
<language name="Toy" version="1" kateversion="5.79" section="Sources" extensions="*.toy" mimetype="text/x-toy">
  <highlighting>
    <list name="keyword">
      <item>let</item>
      <item>if</item>
      <item>else</item>
      <item>while</item>
    </list>
    <contexts>
      <context name="File" attribute="Normal" lineEndContext="#stay">
        <DetectChar char="(" attribute="Normal" context="Atom" beginRegion="Atom"/>
        <RegExpr String="#[\p{L}\p{Nd} \t]*" attribute="Comment"/>
        <keyword String="keyword" attribute="Keyword"/>
        <RegExpr String="[0-9]+(?:\.[0-9]+)?" attribute="Float.Literal"/>
        <RegExpr String="[\p{L}_][\p{L}\p{Nd}_]*" attribute="Variable"/>
        <DetectSpaces attribute="Normal"/>
        <Detect2Chars char="&lt;" char1="=" attribute="Operator"/>
        <Detect2Chars char="&gt;" char1="=" attribute="Operator"/>
        <Detect2Chars char="=" char1="=" attribute="Operator"/>
        <DetectChar char="+" attribute="Operator"/>
        <DetectChar char="-" attribute="Operator"/>
        <DetectChar char="*" attribute="Operator"/>
        <DetectChar char="=" attribute="Operator"/>
      </context>
      <context name="Atom" attribute="Normal" lineEndContext="#stay">
        <DetectChar char=")" attribute="Normal" context="#pop" endRegion="Atom"/>
        <DetectChar char="(" attribute="Normal" context="Atom" beginRegion="Atom"/>
        <RegExpr String="#[\p{L}\p{Nd} \t]*" attribute="Comment"/>
        <keyword String="keyword" attribute="Keyword"/>
        <RegExpr String="[0-9]+(?:\.[0-9]+)?" attribute="Float.Literal"/>
        <RegExpr String="[\p{L}_][\p{L}\p{Nd}_]*" attribute="Variable"/>
        <DetectSpaces attribute="Normal"/>
        <Detect2Chars char="&lt;" char1="=" attribute="Operator"/>
        <Detect2Chars char="&gt;" char1="=" attribute="Operator"/>
        <Detect2Chars char="=" char1="=" attribute="Operator"/>
        <DetectChar char="+" attribute="Operator"/>
        <DetectChar char="-" attribute="Operator"/>
        <DetectChar char="*" attribute="Operator"/>
        <DetectChar char="=" attribute="Operator"/>
      </context>
    </contexts>
    <itemDatas>
      <itemData name="Normal" defStyleNum="dsNormal"/>
      <itemData name="Comment" defStyleNum="dsComment"/>
      <itemData name="Keyword" defStyleNum="dsKeyword"/>
      <itemData name="Float.Literal" defStyleNum="dsFloat"/>
      <itemData name="Variable" defStyleNum="dsVariable"/>
      <itemData name="Operator" defStyleNum="dsOperator"/>
    </itemDatas>
  </highlighting>
  <general>
    <keywords casesensitive="1"/>
  </general>
</language>
```

Reading it back against the grammar: the four keywords became a hashed list, the
length-based operators put their two-character forms first, `class(Float
Literal)` kept both classes in the itemData name while colouring as a float,
`autoclass` found `Comment` by name and `Variable` through `Ident`, and the
bracketing `Atom` production became a context that folds — holding the tokens
`Parse` names inside it, which is why `Skipped` is written at all.

### Trying it out

```bash
# In Kate
cp out/Toy.xml ~/.local/share/org.kde.syntax-highlighting/syntax/
kate sample.toy

# In pandoc
pandoc --syntax-definition out/Toy.xml sample.md -o sample.html
```

---

## Limitations

- **`Parse` output does not validate.** It highlights and folds what your
  grammar describes; a grammar that accepts only well-formed input still colours
  malformed input.
- **A context holds what it reaches.** A token `Parse` never names is never
  matched, which is why a grammar written for a highlighter names the tokens a
  parser would skip.
- **A chain is left by the line that follows it.** A definition ends at the
  first line beginning with none of `|`, `/`, `>` or `#`, which is what Kate
  can see; whether that line *should* have followed is not.
- **No recursive tokens.** A `Lex` production that reaches itself is rejected,
  because a Kate rule matches with an expression.
- **One style per rule.** Extra classes survive in the itemData name, but Kate
  colours by the first one that names a default style.
- **Longest-match choice is ordered, not measured.** For `|` the options are
  emitted longest fixed option first, which is exact for fixed-length options
  and an approximation otherwise.
- **No case-insensitive matching.** MGFF has no spelling for it, so keywords are
  case-sensitive unless `Language > casesensitive(0)` says otherwise.
- **Nothing is skipped.** Kate colours every character, so `skip` has no
  meaning here.
