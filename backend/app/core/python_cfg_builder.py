"""
Module — Python CFG Builder
===========================
Builds a Control Flow Graph (networkx DiGraph) from a Python `ast` tree.

Produces the same CFGGraph anatomy as the C builder:
    nodes: {id, label, block_type: entry|exit|condition|body|merge, statements, source_lines}
    edges: {label: true|false|sequential|back_edge, condition}

Supported constructs: if/elif/else, while, for, return, and plain statements
grouped into basic blocks.
"""

from __future__ import annotations

import ast
import itertools

import networkx as nx

from app.core.cfg_builder import CFGGraph

_id_counter = itertools.count()


def _new_id() -> str:
    return f"BB_{next(_id_counter)}"


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)  # Python 3.9+
    except AttributeError:
        return "<expr>"


def _find_function(tree: ast.Module, function_name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return node
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


class _PyCFGBuilder:
    """Recursive statement walker producing the same node/edge anatomy as the C builder."""

    def __init__(self, g: nx.DiGraph, exit_node: str):
        self.g = g
        self.exit_node = exit_node

    def _add_node(self, label: str, block_type: str,
                  statements=None, source_lines=None) -> str:
        nid = _new_id()
        self.g.add_node(nid, label=label, block_type=block_type,
                        statements=statements or [],
                        source_lines=source_lines or [])
        return nid

    def _connect(self, preds, dst: str, label: str = "sequential",
                 condition=None) -> None:
        for p in preds:
            self.g.add_edge(p, dst, label=label, condition=condition)

    # ------------------------------------------------------------------
    def build(self, stmts, preds):
        """Process a list of statements; returns open tail nodes."""
        current = preds
        block: list[str] = []
        lines: list[int] = []

        def flush():
            nonlocal block, lines
            if not block:
                return current
            nid = self._add_node(
                label=block[0] if len(block) == 1 else f"{block[0]} [+{len(block) - 1}]",
                block_type="body",
                statements=list(block),
                source_lines=list(lines),
            )
            self._connect(current, nid)
            block.clear()
            lines.clear()
            return [nid]

        for stmt in stmts:
            if isinstance(stmt, ast.If):
                current = flush()
                current = self._build_if(stmt, current)
            elif isinstance(stmt, (ast.While, ast.For, ast.AsyncFor)):
                current = flush()
                current = self._build_loop(stmt, current)
            elif isinstance(stmt, ast.Return):
                block.append(_unparse(stmt))
                lines.append(stmt.lineno)
                current = flush()
                if current:
                    self._connect(current, self.exit_node)
                current = []  # return terminates this path
            else:
                # Plain statements (incl. break/continue/pass — loop-edge
                # analysis for those is a future enhancement).
                block.append(_unparse(stmt))
                lines.append(stmt.lineno)

        return flush()

    # ------------------------------------------------------------------
    def _build_if(self, stmt: ast.If, preds) -> list[str]:
        cond_str = _unparse(stmt.test)
        cond_node = self._add_node(
            label=f"if ({cond_str})",
            block_type="condition",
            statements=[f"if {cond_str}:"],
            source_lines=[stmt.lineno],
        )
        self._connect(preds, cond_node)

        # TRUE branch
        true_entry = self._add_node(label="[true-branch]", block_type="body")
        self.g.add_edge(cond_node, true_entry, label="true", condition=cond_str)
        true_tails = self.build(stmt.body, [true_entry])

        # FALSE branch (else / elif — an elif is a nested If inside orelse)
        if stmt.orelse:
            false_entry = self._add_node(label="[false-branch]", block_type="body")
            self.g.add_edge(cond_node, false_entry, label="false",
                            condition=f"not ({cond_str})")
            false_tails = self.build(stmt.orelse, [false_entry])
            merge = self._add_node(label="[merge]", block_type="merge")
            self._connect(list(true_tails) + list(false_tails), merge)
        else:
            merge = self._add_node(label="[merge]", block_type="merge")
            self._connect(true_tails, merge)
            self.g.add_edge(cond_node, merge, label="false",
                            condition=f"not ({cond_str})")
        return [merge]

    # ------------------------------------------------------------------
    def _build_loop(self, stmt, preds) -> list[str]:
        if isinstance(stmt, ast.While):
            cond_str = _unparse(stmt.test)
            head_label = f"while ({cond_str})"
            head_stmts = [f"while {cond_str}:"]
        else:
            target = _unparse(stmt.target)
            it = _unparse(stmt.iter)
            cond_str = f"{target} in {it}"
            head_label = f"for {target} in {it}:"
            head_stmts = [head_label]

        head = self._add_node(label=head_label, block_type="condition",
                              statements=head_stmts, source_lines=[stmt.lineno])
        self._connect(preds, head)

        body_entry = self._add_node(label="[loop-body]", block_type="body")
        self.g.add_edge(head, body_entry, label="true", condition=cond_str)
        body_tails = self.build(stmt.body, [body_entry])
        # Back edge to loop head
        self._connect(body_tails, head, label="back_edge")

        merge = self._add_node(label="[merge]", block_type="merge")
        self.g.add_edge(head, merge, label="false", condition=f"not ({cond_str})")
        return [merge]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cfg_python(tree: ast.Module, function_name: str = "main") -> CFGGraph:
    """
    Build a CFG from a Python ast.Module.

    Args:
        tree: Parsed Python module (from `ast.parse`).
        function_name: Target function name (falls back to the first found).

    Returns:
        CFGGraph with the same anatomy as the C builder's output.
    """
    global _id_counter
    _id_counter = itertools.count()

    g = nx.DiGraph()
    entry = _new_id()
    exit_id = _new_id()
    g.add_node(entry, label="ENTRY", block_type="entry", statements=[], source_lines=[])
    g.add_node(exit_id, label="EXIT", block_type="exit", statements=[], source_lines=[])

    target = _find_function(tree, function_name)
    if target is None:
        g.add_edge(entry, exit_id, label="sequential", condition=None)
        return CFGGraph(graph=g, entry_node=entry, exit_node=exit_id,
                        function_name=function_name, cyclomatic_complexity=1,
                        node_count=2, edge_count=1)

    if target.name != function_name:
        function_name = target.name

    builder = _PyCFGBuilder(g, exit_id)
    tails = builder.build(target.body, [entry])
    for tail in tails:
        if not any(True for _ in g.successors(tail)):
            g.add_edge(tail, exit_id, label="sequential", condition=None)

    E = g.number_of_edges()
    N = g.number_of_nodes()
    cc = E - N + 2
    return CFGGraph(
        graph=g, entry_node=entry, exit_node=exit_id,
        function_name=function_name, cyclomatic_complexity=max(1, cc),
        node_count=N, edge_count=E,
    )
