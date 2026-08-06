# Roadmap for refactoring

## Goal
- Now that a PoC version is done, the need for a number of reworks has become apparent.
- This moves the PyPERG project and MGFF language closer towards its stable and long-term form.
 Further changes will be incremental for a while, with new backends and features being added on top of the existing
- We need to solve a number of improvisations, hard-coded behaviors and hacks that we made

## Attributes
- Attributes can currently only be added after macro defs. We require attributes for the whole generator and a target
- Currently no target requires attrs, but Kate and TextMate generators use a 'Language' top-level macro as a hack for providing global attributes
- Solution: support attribute lines (`> ...`) on the top of the whole file, prefix group and target group
- They can have multiple lines. The file/target/prefix attrs will be written before any definition or a sub-scope

## Highlight style attributes
- Separate classes from highlight styles. Use classes for token matching only, `style(HighlightStyle)` for the visual style
- `class(Variable VarName)` becomes `class(VarName) style(Variable)`
- Used for Kate and TextMate grammar generators

## Output/storage fields syntax
- Currently only the regex generator supports named fields, with the syntax `name:(Rule)`
- Decouple the field naming from the location where the rule is used
- Couple the field name with the match rule and its metadata i.e. its attributes
- Introduce an attribute `store(name)` which always stores outputs of a rule to the same field of its caller

If we had:
```mgff
Expression = ....
Condition = Expression
Block = ....
IfStatement = if condition:(Condition) : block:Block
```
Now we will have:
```mgff
Expression = ....
Condition = Expression
          > store(condition)
Block = ....
      > store(block)
IfStatement = if Condition : Block
```
... which is more readable AND has all the complexities in one attribute list

This will be used for token storing, instead of a hard-coded token stream

## Custom output streams
- Currently the Lex target always outputs an unnamed stream of tokens, and Parse target always outputs a parse tree per the match rules
- This limits what we can do
- From now on, the token output will just be a named list. For token outputs naming classes won't be enough
- New token output system:
    - attribute `push(List_field_name)` adds the current match and its data to List_field_name. `push(tokens)` adds the match, with `class(Classname)` and `style(HighlightStyle)`, to the stream called 'tokens'.
    - `push(List_field_name)` and `store(Data_field_name)` are analoguous. The first adds the match to the list field as a new item, the other assigns the field with this match. Overriding (storing multiple times to the same field of the same structure) shouldn't be allowed.
- This would support separate output channels like Antlr has

## Multi-target generators
- Currently all generators that support multiple targets are fixed on 'Lex' -> 'Parse' sequence,
with hard-coded exceptions and expectations for each one
- Rather than the fixed final 'Parse' target, and text-processing 'Lex' target,
  require only the 'Parse' target and have the user choose the targets before it, if any
- Each target can have a target attribute `post(Prev_target_name)` - it specifies that this target runs *after* the Prev_target_name
- Each target can have a target attribute `over(List_field_name)` - it specifies that this target processes the list List_field_name and executes match rules on it. The first stage is always textual in language grammars, so grammar parser generators don't need 'over' attribute for the first target (the one without a 'post' attribute). The input is already a "character list", i.e. a string. After a lexing process,
the input for a parsing stage could be a list of tokens, matched by their classes instead of characters.
- This system would be a base for support of multi-phase compilation, like the C preprocessor for example