"""
Hierarchical labels in Cypher: `:Label+` means the class and every subclass.

Instances carry only their leaf label, so a query over a class has to name its
subclasses too. Written by hand (`(p:Metadata|KnowledgeMetadata|OntologyMetadata)`) that union goes stale
with every new subclass. A plus after a label asks the ontology instead:

    MATCH (p:GitProject+)-[:HAS_COMMIT]->(c:GitCommit+)
 →  MATCH (p:GitProject|NfProject)-[:HAS_COMMIT]->(c:GitCommit|NfCommit)

`:Label+` is never valid Cypher (label expressions use `| & ! %`), so no
existing query changes meaning. The expansion is textual and runs before the
query is sent; `expand` is pure - the caller supplies the lookup.

Where it applies: a node pattern or a label predicate (`WHERE n:Label+`), on
the label that follows the colon - `(n:Metadata+&Node)` expands, `(n:Node&Metadata+)`
does not and Neo4j rejects it.
Where it does not: inside a string, a comment or a map entry (left alone -
`{n: a+1}` is arithmetic), on a relationship type (refused), and in a clause that writes
labels - `MERGE`, `CREATE`, `SET`, `REMOVE` - where a union cannot be written
(refused). A `MATCH (n:Label+) SET n.x = 1` is fine: the plus is in the MATCH.
"""
import re

PLACEHOLDER = re.compile(r":\s*(`?)([A-Za-z_][A-Za-z0-9_]*)\1\+")
_CLAUSE = re.compile(
    r"\b(OPTIONAL\s+MATCH|MATCH|MERGE|CREATE|WHERE|WITH|RETURN|SET|REMOVE|DELETE|UNWIND|CALL|FOREACH)\b", re.I)
_WRITES = {"MERGE", "CREATE", "SET", "REMOVE"}
_OPEN, _CLOSE = "([{", ")]}"


class LabelExpansionError(ValueError):
    """A `:Label+` that cannot be expanded: unknown class, or a place it may not stand."""


def has_placeholder(query) -> bool:
    return bool(PLACEHOLDER.search(query))


def _contexts(query):
    """Per character: the innermost open bracket (`(`, `[`, `{` or "") - or None
    inside a string literal or a comment."""
    out, stack, i, n = [], [], 0, len(query)
    while i < n:
        ch = query[i]
        if ch in "'\"":
            j = i + 1
            while j < n and query[j] != ch:
                j += 2 if query[j] == "\\" else 1
            j = min(j + 1, n)
            out.extend([None] * (j - i))
            i = j
            continue
        if query.startswith("//", i):
            j = query.find("\n", i)
            j = n if j < 0 else j
            out.extend([None] * (j - i))
            i = j
            continue
        if ch in _OPEN:
            stack.append(ch)
        elif ch in _CLOSE and stack:
            stack.pop()
        out.append(stack[-1] if stack else "")
        i += 1
    return out


def _clause(query, contexts, pos) -> str:
    """The clause keyword governing `pos`: the last one before it outside strings."""
    last = ""
    for m in _CLAUSE.finditer(query, 0, pos):
        if contexts[m.start()] is not None:
            last = m.group(1).upper().split()[-1]
    return last


def _map_key(query, colon) -> bool:
    """Inside braces: is the name before this colon a map key (`{k: …`, `, k: …`)
    rather than a variable in a subquery (`EXISTS { … WHERE n:Label+ }`)?"""
    head = query[:colon].rstrip()
    name = re.search(r"[A-Za-z0-9_`]*$", head).group()
    return head[:len(head) - len(name)].rstrip()[-1:] in ("{", ",")


def expand(query, resolve) -> str:
    """`query` with every `:Label+` replaced by the class and its descendants.

    `resolve(label)` returns the labels at or below `label`, or an empty list
    when no such class is declared. Raises `LabelExpansionError`.
    """
    if not has_placeholder(query):
        return query
    contexts = _contexts(query)
    out, at = [], 0
    for m in PLACEHOLDER.finditer(query):
        ctx = contexts[m.start()]
        if ctx is None or (ctx == "{" and _map_key(query, m.start())):
            continue  # a string, a comment, a map entry: not ours
        label = m.group(2)
        if ctx == "[":
            raise LabelExpansionError(f":{label}+ stands on a relationship type - only node labels expand")
        clause = _clause(query, contexts, m.start())
        if clause in _WRITES:
            raise LabelExpansionError(f":{label}+ in {clause} - a write names exactly one label")
        labels = resolve(label)
        if not labels:
            raise LabelExpansionError(f":{label}+ - no class {label!r} in this base's ontology")
        ordered = [label] + sorted(x for x in labels if x != label)
        union = "|".join(ordered)
        before = query[:m.start()].rstrip()[-1:]
        after = query[m.end():].lstrip()[:1]
        if len(ordered) > 1 and ((before and before in "&|!") or (after and after in "&|!:")):
            union = f"({union})"
        out += [query[at:m.start()], ":", union]
        at = m.end()
    out.append(query[at:])
    return "".join(out)
