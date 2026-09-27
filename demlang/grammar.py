from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from dem.types import FormulaTypeName, SymbolTypeName, Token
from demlang.errors import DemlangSyntaxError
from demlang.lexer import Lexeme, Lexer
from demlang.symbols import SurfaceSymbol, SymbolTable


@dataclass
class _Expr:
    tokens: list[Token]
    formula_type: FormulaTypeName
    infix_symbol_id: int | None = None
    precedence: int | None = None


class _Parser:
    def __init__(
        self,
        text: str,
        table: SymbolTable,
        context: Mapping[str, int],
        *,
        convenience: bool,
    ) -> None:
        self.text = text
        self.table = table
        self.context = dict(context)
        self.items = Lexer(table).tokenize(text)
        self.index = 0
        self.scope: list[str] = []
        self.convenience = convenience

    @property
    def current(self) -> Lexeme:
        return self.items[self.index]

    def parse(self) -> list[Token]:
        if self.current.kind == "eof":
            raise DemlangSyntaxError("formula is empty", 0)
        expr = self._infix(0)
        if self.current.kind != "eof":
            raise DemlangSyntaxError("unexpected trailing input", self.current.position)
        return expr.tokens

    def _infix(self, minimum: int) -> _Expr:
        left = self._atom()
        chain_precedence: int | None = None
        chain_symbol: int | None = None
        while True:
            operator = self._symbol_for(self.current)
            if operator is None or operator.notation_kind != "infix":
                break
            precedence = operator.precedence
            if precedence is None or precedence < minimum:
                break
            if (
                not self.convenience
                and chain_precedence == precedence
                and chain_symbol != operator.id
            ):
                raise DemlangSyntaxError(
                    "operators with the same precedence require parentheses",
                    self.current.position,
                    expected_type=operator.meta.input_formula_type,
                )
            operator_position = self.current.position
            self.index += 1
            right = self._infix(precedence)
            expected = operator.meta.input_formula_type
            self._expect_type(left, expected, operator_position)
            self._expect_type(right, expected, operator_position)
            left = _Expr(
                [Token(symbol_id=operator.id), *left.tokens, *right.tokens],
                operator.meta.output_formula_type,
                infix_symbol_id=operator.id,
                precedence=precedence,
            )
            chain_precedence = precedence
            chain_symbol = operator.id
        return left

    def _atom(self) -> _Expr:
        item = self.current
        if item.kind == "lparen":
            self.index += 1
            expr = self._infix(0)
            self._take("rparen", "expected ')' after formula")
            return expr

        if item.kind not in {"word", "symbol"}:
            raise DemlangSyntaxError("expected a symbol, variable, or '('", item.position)

        if item.kind == "word" and item.text in self.scope:
            self.index += 1
            reverse_index = self.scope[::-1].index(item.text)
            return _Expr([Token(de_bruijn_index=reverse_index)], FormulaTypeName.TERM)

        symbol = self._symbol_for(item)
        if symbol is None and item.kind == "word":
            context_id = self.context.get(item.text)
            symbol = self.table.symbols.get(context_id) if context_id is not None else None
        if symbol is None:
            if self.table.is_ambiguous(item.text):
                raise DemlangSyntaxError(
                    f"ambiguous symbol {item.text!r}; use a qualified name",
                    item.position,
                    code="formula.ambiguous_symbol",
                )
            raise DemlangSyntaxError(f"unknown identifier {item.text!r}", item.position)
        self.index += 1

        if symbol.meta.is_quantifier:
            return self._binder(symbol, item.position)
        if symbol.notation_kind == "infix":
            raise DemlangSyntaxError("infix symbol requires a left operand", item.position)
        if symbol.meta.arity == 0:
            return _Expr([Token(symbol_id=symbol.id)], symbol.meta.output_formula_type)

        if self.current.kind != "lparen":
            raise DemlangSyntaxError(
                f"{symbol.name!r} requires {symbol.meta.arity} argument(s)",
                self.current.position,
                expected_type=symbol.meta.input_formula_type,
            )
        self.index += 1
        children: list[_Expr] = []
        for child_index in range(symbol.meta.arity):
            if child_index:
                self._take("comma", "expected ',' between arguments")
            child = self._infix(0)
            self._expect_type(child, symbol.meta.input_formula_type, item.position)
            children.append(child)
        self._take("rparen", "expected ')' after arguments")
        tokens = [Token(symbol_id=symbol.id)]
        for child in children:
            tokens.extend(child.tokens)
        return _Expr(tokens, symbol.meta.output_formula_type)

    def _binder(self, symbol: SurfaceSymbol, position: int) -> _Expr:
        names: list[str] = []
        while True:
            item = self.current
            if item.kind != "word":
                raise DemlangSyntaxError("expected a bound variable name", item.position)
            if item.text in names:
                raise DemlangSyntaxError("bound variable names must be distinct", item.position)
            names.append(item.text)
            self.index += 1
            if self.current.kind != "comma":
                break
            self.index += 1
        self._take("dot", "expected '.' after bound variable")
        self.scope.extend(names)
        try:
            body = self._infix(0)
        finally:
            del self.scope[-len(names):]
        self._expect_type(body, symbol.meta.input_formula_type, position)
        tokens = body.tokens
        for _ in reversed(names):
            tokens = [Token(symbol_id=symbol.id), *tokens]
        return _Expr(tokens, symbol.meta.output_formula_type)

    def _symbol_for(self, item: Lexeme) -> SurfaceSymbol | None:
        if item.symbol_id is not None:
            # A local declaration shadows a word-like global spelling.
            if item.kind == "word" and item.text in self.context:
                return self.table.symbols.get(self.context[item.text])
            return self.table.symbols.get(item.symbol_id)
        return self.table.resolve(item.text)

    def _take(self, kind: str, message: str) -> Lexeme:
        if self.current.kind != kind:
            raise DemlangSyntaxError(message, self.current.position)
        item = self.current
        self.index += 1
        return item

    def _expect_type(
        self,
        expr: _Expr,
        expected: FormulaTypeName | None,
        position: int,
    ) -> None:
        if expected is not None and expr.formula_type != expected:
            raise DemlangSyntaxError(
                f"expected {expected.value} but got {expr.formula_type.value}",
                position,
                expected_type=expected,
            )


def parse_core(
    text: str,
    table: SymbolTable,
    context: Mapping[str, int] | None = None,
) -> list[Token]:
    return _Parser(text, table, context or {}, convenience=False).parse()


def parse_convenience(
    text: str,
    table: SymbolTable,
    context: Mapping[str, int] | None = None,
) -> list[Token]:
    return _Parser(text, table, context or {}, convenience=True).parse()
