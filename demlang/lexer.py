from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from demlang.errors import DemlangSyntaxError
from demlang.symbols import SymbolTable


@dataclass
class _TrieNode:
    children: dict[str, "_TrieNode"] = field(default_factory=dict)
    symbol_id: int | None = None


@dataclass(frozen=True)
class Lexeme:
    kind: str
    text: str
    position: int
    symbol_id: int | None = None


def _identifier_char(char: str) -> bool:
    return char.isalnum() or char in "_′″'"


class Lexer:
    """Dynamic longest-match lexer built from symbol names and aliases."""

    def __init__(self, table: SymbolTable) -> None:
        root = cast(_TrieNode | None, table._lexer_root)
        if root is None:
            root = _TrieNode()
            for spelling, symbol_id in table.spellings.items():
                node = root
                for char in spelling:
                    node = node.children.setdefault(char, _TrieNode())
                node.symbol_id = symbol_id
            object.__setattr__(table, "_lexer_root", root)
        self._root = root

    def tokenize(self, text: str) -> list[Lexeme]:
        result: list[Lexeme] = []
        pos = 0
        while pos < len(text):
            if text[pos].isspace():
                pos += 1
                continue

            if _identifier_char(text[pos]):
                end = pos + 1
                while end < len(text) and _identifier_char(text[end]):
                    end += 1
                word = text[pos:end]
                match = self._longest(text, pos)
                if match is not None and match[0] > end:
                    match_end, symbol_id = match
                    result.append(
                        Lexeme("symbol", text[pos:match_end], pos, symbol_id)
                    )
                    pos = match_end
                    continue
                if match is not None and match[0] == end:
                    result.append(Lexeme("word", word, pos, match[1]))
                else:
                    result.append(Lexeme("word", word, pos))
                pos = end
                continue

            match = self._longest(text, pos)
            if match is not None:
                end, symbol_id = match
                result.append(Lexeme("symbol", text[pos:end], pos, symbol_id))
                pos = end
                continue

            punctuation = {"(": "lparen", ")": "rparen", ",": "comma", ".": "dot"}
            kind = punctuation.get(text[pos])
            if kind is None:
                raise DemlangSyntaxError(f"unexpected character {text[pos]!r}", pos)
            result.append(Lexeme(kind, text[pos], pos))
            pos += 1
        result.append(Lexeme("eof", "", len(text)))
        return result

    def _longest(self, text: str, start: int) -> tuple[int, int] | None:
        node = self._root
        best: tuple[int, int] | None = None
        pos = start
        while pos < len(text) and text[pos] in node.children:
            node = node.children[text[pos]]
            pos += 1
            if node.symbol_id is not None:
                best = (pos, node.symbol_id)
        return best
