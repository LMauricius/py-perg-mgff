# MGFF: Language Specification

**M**acro **G**rammar **F**unctional **F**orm

It's ***not*** Mauricius' Grammar Functional Form 😉.

MGFF describes languages: their tokens and their grammar. It is given in three
parts. **Part 1** defines the *shape* of a file (how text splits into groups,
lines, and items) and assigns it no meaning. **Part 2** defines what those
pieces mean to a grammar generator. **Part 3** records the constructs that
established generators and targets provide; it is conventional rather than
required.

A domain-specific dialect may extend MGFF from **Part 2** onwards.

## Prelude

### Motivation - Why MGFF?

Originally I started working on MGFF due to minor frustrations with the usual EBNF -
big differences from the real parsed code, significant usage of commas,
separation of the lexer and the parser
and the usually required combination with Turing-complete languages.

While I'm not against using different tools best suited for different purposes,
I *am* bothered by combining different tools for the *same* purpose
because one of them is insufficient.
To me, that meant the first tool wasn't good enough to be used for the task in the first place,
and if almost every usage requires occasional usage of the more powerful tool,
the first one is bad in itself.

Another pet-peeve of mine were the toolsets built around existing grammar specifications - 
every one of them imposes some kind of a limitation on the grammar itself
due to the limitations of the parser generator.
Examples being lacking left-recursion and ambiguities introduced by the algorithm.
Some of these are trivial to fix, meaning the grammar was never bad,
just our communication with the program.

Since I believe humans shouldn't have to adapt to the machine but the other way around,
I decided to make something more obvious and flexible.

### Ideals

When defining the MGFF language I went through many small iterations,
trying to make a language that is:
- Clearly readable
- Intuitive, even for someone who doesn't 100% understand MGFF
- Usable when teaching the target language's grammar to a newbie
- Unambiguous and rigorously defined
- Extensible
- Not tied to string parsing
- Complete, to minimize the work required in another language for parser development
- Powerful enough to define languages higher in the Chomsky hierarchy
- Simple for regular languages

---

## Part 1: Lexical structure

An MGFF file is UTF-8 text.

The meta-notation below is EBNF, written *about* MGFF, not *in* it: `x?`
optional, `x*` zero or more, `x+` one or more, `x{n}` exactly *n* times,
`a | b` choice, `( )` grouping, `"x"` a literal character.

```
file    = lines
lines   = line (NL line)*
line    = WS* (item (WS+ item)*)? WS*
item    = text (group text)* group?
        | group (text group)* text?
group   = "(" lines ")"
text    = (escape | literal )+
escape  = "\" (SIMPLE | "0" | "x" HEX{2} | "u" HEX{4} | "U" HEX{8}
              | "<" NAME ">")
literal = CHAR except WS, "(", ")", "\", "\r", "\n"
WS      = " " | "\t"
NL      = "\r"? "\n"
SIMPLE  = one of ( ) \ _ a b f n r t v
HEX     = "0" … "9" | "a" … "f" | "A" … "F"
NAME    = ("A" … "Z" | "0" … "9" | "-" | "_")+
CHAR    = any Unicode character
```

Consequences of the grammar:

1. `(` and `)` are the only brackets. `[ ] { } < >` and every other character are ordinary text.
2. Whitespace separates items only outside parentheses. A group and the text
   glued to it form one item, however many inner spaces or newlines it has.
   Within an item, text and groups alternate, so two groups always have text
   between them; `(a)(b)` is an error.
3. A line ends at a newline that is not inside a group. A group may therefore
   span lines, and its contents are lines of its own.
4. There are no quotes. Literal text is written bare.

### Escapes

An escape denotes exactly one character. The set is closed: a
backslash followed by anything not listed below is an error, so `\*` is invalid
where `*` is already ordinary text. Whatever form produces it, the character
carries no special role; `\x28` is the text `(`, never the opening of a group.

| Escape       | Character                                                                                                                              |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `\(` `\)`    | The parenthesis itself.                                                                                                                |
| `\\`         | Backslash.                                                                                                                             |
| `\_`         | Space. This escape is particular to MGFF.                                                                                              |
| `\a`         | Alert, U+0007.                                                                                                                         |
| `\b`         | Backspace, U+0008.                                                                                                                     |
| `\f`         | Form feed, U+000C.                                                                                                                     |
| `\n`         | Line feed, U+000A.                                                                                                                     |
| `\r`         | Carriage return, U+000D.                                                                                                               |
| `\t`         | Horizontal tab, U+0009.                                                                                                                |
| `\v`         | Vertical tab, U+000B.                                                                                                                  |
| `\0`         | The null character.                                                                                                                    |
| `\xhh`       | Exactly two hexadecimal digits, read as a code point in U+0000-U+00FF.                                                                 |
| `\uhhhh`     | Exactly four hexadecimal digits, read as a code point.                                                                                 |
| `\UHHHHHHHH` | Exactly eight hexadecimal digits, read as a code point.                                                                                |
| `\<NAME>`    | The character with the given Unicode name, written in upper case with `_` in place of each space, as in `\<GREEK_SMALL_LETTER_ALPHA>`. |

A numeric escape denoting a value above U+10FFFF, or a surrogate code point, is
an error. A backslash followed by a space or a tab is likewise an error:
whitespace is written `\_` or `\t`.

### Example

The line

```
    d Number = Int (. (Digit)+)?
```

has five items: `d` · `Number` · `=` · `Int` · `( . ( Digit )+ )?`. The last is
one item: the text `?` glued to a group whose own items are `.` and
`( Digit )+`. By contrast `< =` is two items, since the separating space is
outside any group.

---

## Part 2: Grammar semantics

A line's role is fixed by its first item; an item's role is fixed by its shape.
A marker has its role only as a complete first item of a line; elsewhere it is
ordinary text.

### Line roles

| First item | Role                                           |
| ---------- | ---------------------------------------------- |
| *(none)*   | Blank line; ignored.                           |
| `#`        | Comment; the line is ignored.                  |
| `d`        | Macro definition: `d Head = Body`.             |
| `/`        | Order-based alternative of the current macro.  |
| `\|`       | Length-based alternative of the current macro. |
| `>`        | Attributes of the current macro, or of the scope. |
| `t`        | Generation target: `t Name ( … )`.             |
| `p`        | Name prefix: `p Prefix ( … )`.                 |

Any other first item is an error.

### Macros

```
d Head = Body
```

*Head* is the item after `d`: a **call-shape**, whose text gives the macro's name
and whose groups declare its parameters. A head of bare text is the simplest
case, a macro of no parameters. See *Parameters and expansion*.

The **first top-level item equal to `=`**, which must be right after the head item, 
separates head from body; later `=` items are ordinary.
Since the head is read only after `d`, a macro may bear
any name, including a marker character.

*Body* is the remaining items of the line: the macro's first
**alternative**, a sequence matched in order.

A definition may separate with `>` instead of `=`:

```
d Head > Attributes
```

The rest of the line is then attributes rather than a body, and the macro has no
alternatives at all. It matches nothing on its own and exists for the attributes
it carries, which is how a named list of attributes is written. Further `>` lines
add to them as usual, and an alternative line may not follow.

Further alternatives follow on lines starting with `/` or `|`, each holding one
sequence:

- All alternatives of one macro use the same marker; `/` and `|` never mix.
- A macro with no `/` or `|` line consists of a single alternative, or of none
  when its definition has no body.
- `#` lines between alternatives do not end the macro.
- `>` lines end the alternatives. Their remaining items are **attributes**
  (calls with or without arguments, e.g. `token`, `skip`, `skip(false)`), whose
  meaning is generator-specific. A macro may carry several `>` lines; their
  attributes accumulate. An alternative line after this is an error.

**Preference modes.**

- Order-based (`/`): the match is the first listed alternative that succeeds.
- Length-based (`|`): the match is the alternative consuming the most input;
  ties go to the earliest listed.

### Item roles

In a macro body, each item is interpreted by the first rule below that
matches its shape. Part 3 extends this list.

| Interpretation | Shape                                                     | Meaning                                                                                                                                             |
| -------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Subgroup       | `( … )` alone                                             | The rule formed by the group's lines, joined into a single sequence; the line breaks are a matter of layout. A subgroup holds no macro definitions. |
| Call           | any other item, e.g. `Digit`, `( Digit )+`, `sep(x)by(y)` | Match the macro named by the item's text, applied to the contents of its groups.                                                                    |

A call resolves to what is visible here: a macro, or a parameter of an enclosing
macro. Calls carrying arguments and calls carrying none rank equally in Part 2,
but Part 3 places shapes of its own between them.

### Parameters and expansion

A head with parameter slots defines a mixfix macro:

```
d sep(R)by(S) = R ( S R )*
```

This declares `sep(_)by(_)` with parameters `R` and `S`, the single item in
each slot. Text outside the slots (`sep`, `by`) belongs to the name.

A **call** repeats the skeleton with arguments in the slots, glued into one
item: `sep(Ident = Expr)by(,)`. A macro of no parameters is called by writing
its bare name, with nothing to fill.

**Expansion** is capture-free substitution: each occurrence of a parameter in
the body is replaced by its argument, a multi-item argument being wrapped in a
group so its grouping survives.

```
sep(Ident = Expr)by(,)   ⇒   (Ident = Expr) ( , (Ident = Expr) )*
```

Each call is interpreted as its expansion. Where the macro call-graph is
acyclic, a call is equivalent to its fully expanded form. Macros may, however,
be self-referencing or mutually recursive, so an implementation must expand
calls on demand rather than exhaustively.

The constructs of Part 3 are macros whose expansion is defined by the
generator rather than by MGFF, whether or not they take parameters.

### Targets and prefixes

`t Name ( … )` groups the macros inside it into one generation phase,
typically `Lex` for tokens and `Parse` for grammar.

`p Prefix ( … )` prepends the literal text `Prefix` to the name of every
macro defined directly inside it. Any separator must be part of `Prefix`
itself:

```
p Util_ (
    d pair = ( Expr , Expr )
    d list = sep(Expr)by(,)
)
```

defines `Util_pair` and `Util_list`. Nested prefixes concatenate. Inside the
prefix a macro may be called by its local name, outside by its full name.

Whether a later target may call an earlier target's macros is decided
by the generator, not by MGFF.

A macro may also be defined outside every target and prefix. It then carries
no prefix and is visible to all targets, which makes the outermost level the
natural home for shared utility macros.

### Attributes of a scope

A `>` line written **before the first definition or nested scope** of a scope has
no macro to attach to, and carries the attributes of that scope itself: of the
file, of a target, or of a prefix.

```
> name(Toy) section(Sources) extensions(*.toy)
> license(MIT)

t Parse (
    > post(Lex) over(tokens)

    d File = ( Expr )*
)
```

The file's attributes describe the grammar as a whole, which is where a generator
reads settings such as the name of the language it generates. A target's describe
the phase — see *Targets* in Part 3.

Several `>` lines accumulate, and `#` lines between them are ignored, exactly as
for a macro. A named list of attributes may be spliced in by naming it, and since
the attributes come above the definitions the list itself is written below them.
A `>` line **after** the scope's first definition or nested scope is an error: it
neither attaches to a macro nor sits where a scope's own attributes belong.

---

## Part 3: Built-in macros, attributes and features

The definitions below are built in to the established grammar generators and
targets. They belong to this specification because they are common and widely
understood, though MGFF is complete without them. A domain-specific use of MGFF
may define built-in macros and attributes of its own.

### Rule-matching macros

A macro that a target treats as a matching rule is a **production**. Every such
target provides these macros:

| Shape           | Meaning                    |
| --------------- | -------------------------- |
| `( R )+`        | one or more                |
| `( R )*`        | zero or more               |
| `( R )?`        | optional                   |
| `(O1)\|(O2)\|…` | inline length-based choice |
| `(O1)/(O2)/…`   | inline order-based choice  |

The choice forms carry no whitespace around their separator; a space there would
split the construct into separate items. An item in either choice shape is read
as a choice in preference to the general *Call* rule.

Where MGFF is used to specify lexers and parsers, these macros may be assumed
present throughout.

### Character matching macros

Targets that match textual characters, such as the `Lex` target, add one item
shape, a production name recognised by its pattern:

| Interpretation | Shape                                                                                                 | Meaning                                    |
| -------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| Character set  | paren-free, one or more parts separated by `\|`, e.g. `a`, `0-9`, `a-z\|A-Z\|_`, `Lu\|Decimal_Number` | One character from the union of the parts. |

A **part** is one of:

| Part      | Shape                                                | Meaning                                   |
| --------- | ---------------------------------------------------- | ----------------------------------------- |
| Character | a single character, e.g. `a`, `\_`, `é`              | That character, escapes resolved.         |
| Range     | `E-F`, both endpoints a single character, e.g. `0-9` | Any character from `E` to `F` inclusive.  |
| Category  | the name of a Unicode character category             | Any character belonging to that category. |

A category is named either by its two-letter abbreviation, as in `Lu` or `Nd`, or
by its long form, as in `Uppercase_Letter` or `Decimal_Number`. The one-letter
abbreviations (`L` for every letter, `N` for every number) are not available,
since a single character is a character part; the long form (`Letter`, `Number`)
serves instead. No category name is a single character, and none contains `-` or
`\|`, so the three part shapes never overlap. Which categories a target
recognises is generator-specific; a part of two or more characters that names no
recognised category is an error.

These are not to be confused with calls carrying arguments; a character set is
bare text, and the sets are assumed to be pre-defined in bulk. During name
lookup, a set of two or more parts is tried after a call carrying arguments and
before an argument-less call, and a set of a single part is tried last of all;
so a production may still be named `x` or `Letter` and be called by that name.
Character sets are therefore unlimited in number without reserving any names:
each is an ordinary item of bare text, recognised by its shape alone.

### Where a match goes

A grammar that only recognises text needs neither of these. One that produces
something — a parse tree, a list of tokens, a stream of anything — says where each
match ends up, and says it on the match itself:

| Attribute      | Meaning                                                        |
| -------------- | -------------------------------------------------------------- |
| `store(field)` | The match is assigned to `field` of whatever called it.        |
| `push(list)`   | The match is appended to the list called `list`.               |

```mgff
d Expression = ...
d Condition = Expression
            > store(condition)
d Block = ...
        > store(block)

d IfStatement = i f Condition : Block
```

`IfStatement` produces a structure with a `condition` and a `block`, without
either name appearing where the rule is used. `store` and `push` are the same
idea for a field holding one thing and a field holding many; storing the same
field twice from one caller is an error, and pushing is how to say "again".

A field or list name is a letter or an underscore followed by letters, digits or
underscores. A production may `push` to several lists at once, which is how one
match reaches a general stream and a channel of its own.

Naming the field on the rule rather than at the call site means a production is
written once and read the same way everywhere, and everything about a match — what
it is, what it looks like, where it goes — sits in one attribute list. It also
means a production used in two places writes the same field in both; where that
is not what was meant, the two uses want two productions.

---

## Appendix A: A complete example

```mgff
# A tiny calculator language.

t Lex (

    d Digit = 0-9
    d Alpha = a-z|A-Z
    d AlNum = a-z|A-Z|0-9

    d Int = ( Digit )+
          > token

    d Number = Int ( . ( Digit )+ )?
             > token  skip(false)

    d Ident = Alpha ( AlNum )*
            > token

    # length-based: "<=" (the two-item "< =") takes precedence over "<"
    d Op = < =
         | <
         | =
         | +
         | -
         | *
         | /
         > token string

    d Space  = ( \_|\t|\n )+
        > token  skip

    d LParen = \(
        > token
    d RParen = \)
        > token
)

# mixfix macro: an R, then zero or more (S R)
d sep(R)by(S) = R (S R)*

t Parse (

    # order-based: the first alternative that succeeds is the match
    d Expr = Term + Expr
           / Term - Expr
           / Term

    d Term = Factor * Term
           / Factor / Term
           # the second / on the line above is an ordinary item, not a marker
           / Factor

    d Factor = Number
             / Ident
             / \( Expr \)

    d Signed = ( (+)/(-) )? Number

    d AssignList = sep(Ident = Expr)by(,)
)
```

---

## Appendix B: Notes

**Layout is arbitrary.** Blank lines and indentation are runs of separators with no
items, so they carry no structure. Tabs separate items exactly like spaces.

**Marker characters as data.** Only the first item of a line is a marker. On the
line `/ Factor / Term` the leading `/` opens an alternative and the second `/`
is an ordinary item. Likewise the `=` inside `sep(Ident = Expr)by(,)` is nested in
a group and cannot be the head/body separator.

**Whitespace is not implicit.** Whitespace separates items in an MGFF file; it
says nothing about the input being matched. The alternative `< =` is a sequence
of two characters and matches only the string `<=`.

**Rule order matters.** A shape can be read more than one way, and the higher
rank wins: `a-z|A-Z` is a character set even where a production bears that name,
while the single-part `a` or `Letter` yields to the production.

**Calling is naming.** A macro of no parameters is called by writing its name,
so `Digit` and `sep(x)by(y)` are the same kind of item (a call) and are looked
up the same way. There is no separate notion of a reference.
