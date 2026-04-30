"""Safe numeric evaluation for agents (FinTeam-style accountant pattern)."""

from __future__ import annotations

import ast
import operator
from typing import Annotated, Union

from langchain_core.tools import tool

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_UOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_ast(node: ast.AST) -> Union[int, float]:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value) if isinstance(node.value, float) else int(node.value)
        raise ValueError("only numeric constants allowed")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UOPS:
        return _UOPS[type(node.op)](_eval_ast(node.operand))
    if isinstance(node, ast.Expr):
        return _eval_ast(node.value)  # type: ignore
    raise ValueError("unsupported expression; use + - * / ** % and parentheses only")


@tool
def evaluate_math_expression(
    expression: Annotated[str, "Arithmetic expression using digits, + - * / ** %, parentheses, decimals"],
) -> str:
    """Evaluate a numeric expression safely in-process. Use for implied growth, margin math, or checking multiple ratios—do not do multi-step arithmetic in prose."""
    expression = (expression or "").strip()
    if not expression:
        return "Error: empty expression"
    try:
        tree = ast.parse(expression, mode="eval")
        out = _eval_ast(tree.body)
        return str(out)
    except Exception as exc:
        return f"Error evaluating expression: {exc}"
