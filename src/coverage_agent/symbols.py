"""Name the function that owns an uncovered line."""

from dataclasses import dataclass

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

_PARSER = Parser(Language(tspython.language()))
_SYMBOLS = {"function_definition", "class_definition"}


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    start_line: int
    end_line: int
    snippet: str


def enclosing_symbol(source: str, line: int) -> Symbol | None:
    """Return the smallest function or class that contains the 1-based line."""
    tree = _PARSER.parse(source.encode("utf-8"))
    found: list[tuple[int, Symbol]] = []

    def walk(node) -> None:
        if node.type in _SYMBOLS:
            name_node = node.child_by_field_name("name")
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            if start <= line <= end and name_node is not None:
                name = source.encode("utf-8")[name_node.start_byte : name_node.end_byte].decode(
                    "utf-8"
                )
                snippet = "\n".join(source.splitlines()[start - 1 : end])
                found.append((end - start, Symbol(name, node.type, start, end, snippet)))
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[0][1]
