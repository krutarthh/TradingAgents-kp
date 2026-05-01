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


@tool
def implied_cagr(
    start_value: Annotated[float, "starting value (must be > 0)"],
    end_value: Annotated[float, "ending value (must be > 0)"],
    years: Annotated[float, "number of years (must be > 0)"],
) -> str:
    """Compute implied CAGR for deterministic valuation sanity checks."""
    try:
        if start_value <= 0 or end_value <= 0 or years <= 0:
            return "Error: start_value, end_value, and years must be > 0"
        cagr = (end_value / start_value) ** (1.0 / years) - 1.0
        return str(cagr)
    except Exception as exc:
        return f"Error computing implied CAGR: {exc}"


@tool
def valuation_sensitivity_table(
    base_revenue: Annotated[float, "base annual revenue"],
    base_margin: Annotated[float, "base operating margin as decimal (e.g., 0.25)"],
    base_multiple: Annotated[float, "base EV/EBITDA or P/E-like multiple"],
) -> str:
    """Return a compact deterministic sensitivity table for valuation triangulation."""
    try:
        if base_revenue <= 0 or base_multiple <= 0:
            return "Error: base_revenue and base_multiple must be > 0"
        margin_shocks = [-0.03, 0.0, 0.03]
        mult_shocks = [-2.0, 0.0, 2.0]
        lines = [
            "| Margin | Multiple | Implied Value Index |",
            "|---|---:|---:|",
        ]
        for ms in margin_shocks:
            m = max(0.01, base_margin + ms)
            for xs in mult_shocks:
                x = max(0.5, base_multiple + xs)
                implied = base_revenue * m * x
                lines.append(f"| {m:.2%} | {x:.2f}x | {implied:.2f} |")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error computing valuation sensitivity table: {exc}"
