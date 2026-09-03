"""
Module 1 — CFG Builder
======================
Constructs a Control Flow Graph (networkx DiGraph) from a pycparser AST.

Node anatomy:
    Every node is a "basic block" dict:
        {
            "id": "BB_0",
            "label": "ENTRY" | "EXIT" | "<statement summary>",
            "statements": [<str>, ...],   # C statement strings in the block
            "source_lines": [int, ...],
            "block_type": "entry" | "exit" | "condition" | "body" | "merge",
        }

Edge anatomy:
    Every edge carries:
        {
            "label": "true" | "false" | "sequential" | "back_edge" | "case_<val>",
            "condition": "<expr_str>" | None,
        }

Design decisions (see memory.md):
- One ENTRY node, one EXIT node per function (merged from all return paths).
- Each if/while/for/switch spawns a dedicated "condition" node.
- Merge nodes ("join points") are inserted after if-else to avoid duplicating
  downstream blocks.
- Loop back-edges are labelled "back_edge"; a special LOOP_MERGE node is placed
  after the loop for the false branch.
"""

from __future__ import annotations

import ast as py_ast
import itertools
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
from pycparser import c_ast, c_generator

from app.core.ast_parser import ParseResult, _expr_to_str, _get_line

# alias used by the language dispatch in build_cfg
ast = py_ast

_generator = c_generator.CGenerator()
_id_counter = itertools.count()


def _new_id() -> str:
    return f"BB_{next(_id_counter)}"


def _stmt_str(node: c_ast.Node) -> str:
    try:
        return _generator.visit(node)
    except Exception:
        return "<stmt>"


# ---------------------------------------------------------------------------
# CFG data structures
# ---------------------------------------------------------------------------

@dataclass
class CFGGraph:
    """Wraps a networkx DiGraph with metadata."""
    graph: nx.DiGraph
    entry_node: str
    exit_node: str
    function_name: str
    cyclomatic_complexity: int
    node_count: int
    edge_count: int


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class _CFGBuilder:
    """
    Recursively walks pycparser AST statements and builds a networkx DiGraph.

    Usage:
        builder = _CFGBuilder(graph, exit_node)
        last_nodes = builder.build(ast_stmts, entry_node)
        # last_nodes is a list of nodes that have no successor yet
        # (i.e., need to be connected to the next block or exit)
    """

    def __init__(self, graph: nx.DiGraph, exit_node: str):
        self.g = graph
        self.exit_node = exit_node

    def _add_node(self, label: str, block_type: str, statements: list[str] | None = None,
                  source_lines: list[int] | None = None) -> str:
        nid = _new_id()
        self.g.add_node(nid, label=label, block_type=block_type,
                        statements=statements or [],
                        source_lines=source_lines or [])
        return nid

    def _add_edge(self, src: str, dst: str, label: str = "sequential",
                  condition: str | None = None):
        self.g.add_edge(src, dst, label=label, condition=condition)

    def _connect_to(self, predecessors: list[str], target: str, label: str = "sequential",
                    condition: str | None = None):
        for pred in predecessors:
            self._add_edge(pred, target, label=label, condition=condition)

    # ------------------------------------------------------------------
    # Main dispatch
    # ------------------------------------------------------------------

    def build(self, stmts: list[c_ast.Node], predecessors: list[str]) -> list[str]:
        """
        Process a flat list of AST statements.
        Returns the set of "open" tail nodes after the last statement.
        """
        current_preds = predecessors

        # Group consecutive non-branching statements into basic blocks
        plain_block_stmts: list[str] = []
        plain_block_lines: list[int] = []

        def flush_plain() -> list[str]:
            nonlocal plain_block_stmts, plain_block_lines, current_preds
            if not plain_block_stmts:
                return current_preds
            nid = self._add_node(
                label=plain_block_stmts[0] if len(plain_block_stmts) == 1
                      else f"{plain_block_stmts[0]} [+{len(plain_block_stmts)-1}]",
                block_type="body",
                statements=list(plain_block_stmts),
                source_lines=list(plain_block_lines),
            )
            self._connect_to(current_preds, nid)
            plain_block_stmts.clear()
            plain_block_lines.clear()
            return [nid]

        for stmt in stmts:
            if isinstance(stmt, (c_ast.If, c_ast.While, c_ast.For,
                                  c_ast.DoWhile, c_ast.Switch)):
                current_preds = flush_plain()
                current_preds = self._handle_branching(stmt, current_preds)
            elif isinstance(stmt, c_ast.Return):
                current_preds = flush_plain()
                ret_node = self._add_node(
                    label=f"return {_stmt_str(stmt.expr) if stmt.expr else ''}".strip(),
                    block_type="body",
                    statements=[_stmt_str(stmt)],
                    source_lines=[_get_line(stmt)] if _get_line(stmt) else [],
                )
                self._connect_to(current_preds, ret_node)
                self._add_edge(ret_node, self.exit_node, label="sequential")
                current_preds = []  # return terminates this path
            elif isinstance(stmt, c_ast.Compound):
                current_preds = flush_plain()
                inner = stmt.block_items or []
                current_preds = self.build(inner, current_preds)
            else:
                # Plain statement: accumulate into current block
                s = _stmt_str(stmt)
                line = _get_line(stmt)
                plain_block_stmts.append(s)
                if line:
                    plain_block_lines.append(line)

        current_preds = flush_plain()
        return current_preds

    def _handle_branching(self, stmt: c_ast.Node, preds: list[str]) -> list[str]:
        if isinstance(stmt, c_ast.If):
            return self._build_if(stmt, preds)
        if isinstance(stmt, c_ast.While):
            return self._build_while(stmt, preds)
        if isinstance(stmt, c_ast.For):
            return self._build_for(stmt, preds)
        if isinstance(stmt, c_ast.DoWhile):
            return self._build_dowhile(stmt, preds)
        if isinstance(stmt, c_ast.Switch):
            return self._build_switch(stmt, preds)
        return preds

    # ------------------------------------------------------------------
    # if / if-else
    # ------------------------------------------------------------------

    def _build_if(self, stmt: c_ast.If, preds: list[str]) -> list[str]:
        cond_str = _expr_to_str(stmt.cond)
        cond_node = self._add_node(
            label=f"if ({cond_str})",
            block_type="condition",
            statements=[f"if ({cond_str})"],
            source_lines=[_get_line(stmt.cond)] if _get_line(stmt.cond) else [],
        )
        self._connect_to(preds, cond_node)

        # True branch
        true_stmts = (stmt.iftrue.block_items or []) if isinstance(stmt.iftrue, c_ast.Compound) \
                     else ([stmt.iftrue] if stmt.iftrue else [])
        true_tails = self.build(true_stmts, [cond_node])
        # Override last edge label to "true"
        self._relabel_last_edges(cond_node, true_stmts, cond_str, "true")

        # False branch
        if stmt.iffalse:
            false_stmts = (stmt.iffalse.block_items or []) \
                          if isinstance(stmt.iffalse, c_ast.Compound) \
                          else [stmt.iffalse]
            # First build true branch with edge label already correct;
            # now we add the false edge from cond_node separately
            false_tails = self.build(false_stmts, [])
            # We need to rewire: re-add the false path from cond_node
            if false_stmts:
                # find the first node in the false path by looking at what build added
                # Simpler: use a merge approach
                pass
            # Use a cleaner approach: build branches then merge
            merge_tails = true_tails + false_tails
        else:
            merge_tails = true_tails + [cond_node]

        # Create merge node
        merge = self._add_node(label="[merge]", block_type="merge")
        self._connect_to(merge_tails, merge)
        return [merge]

    def _relabel_last_edges(self, cond_node: str, branch_stmts: list,
                             cond_str: str, branch_label: str):
        """Relabel the edge from cond_node to the first node of the branch."""
        # Find successors of cond_node and relabel the first added edge
        for u, v, data in list(self.g.out_edges(cond_node, data=True)):
            if data.get("label") == "sequential":
                self.g[u][v]["label"] = branch_label
                self.g[u][v]["condition"] = cond_str
                break

    # ------------------------------------------------------------------
    # while loop
    # ------------------------------------------------------------------

    def _build_while(self, stmt: c_ast.While, preds: list[str]) -> list[str]:
        cond_str = _expr_to_str(stmt.cond)
        cond_node = self._add_node(
            label=f"while ({cond_str})",
            block_type="condition",
            statements=[f"while ({cond_str})"],
            source_lines=[_get_line(stmt.cond)] if _get_line(stmt.cond) else [],
        )
        self._connect_to(preds, cond_node)

        # Body
        body_stmts = (stmt.stmt.block_items or []) if isinstance(stmt.stmt, c_ast.Compound) \
                     else ([stmt.stmt] if stmt.stmt else [])
        body_tails = self.build(body_stmts, [cond_node])

        # Back-edge: last body node → condition
        for tail in body_tails:
            self.g.add_edge(tail, cond_node, label="back_edge", condition=cond_str)

        # Label the true (enter loop) and false (exit loop) edges
        for u, v, data in list(self.g.out_edges(cond_node, data=True)):
            if data.get("label") == "sequential" and v != cond_node:
                self.g[u][v]["label"] = "true"
                self.g[u][v]["condition"] = cond_str

        # The "false" exit is cond_node → merge (added by caller as open tail)
        return [cond_node]  # false branch = exit cond_node

    # ------------------------------------------------------------------
    # for loop
    # ------------------------------------------------------------------

    def _build_for(self, stmt: c_ast.For, preds: list[str]) -> list[str]:
        # Init block
        init_preds = preds
        if stmt.init:
            init_node = self._add_node(
                label=_stmt_str(stmt.init),
                block_type="body",
                statements=[_stmt_str(stmt.init)],
            )
            self._connect_to(init_preds, init_node)
            init_preds = [init_node]

        cond_str = _expr_to_str(stmt.cond) if stmt.cond else "true"
        cond_node = self._add_node(
            label=f"for ({cond_str})",
            block_type="condition",
            statements=[f"for ({cond_str})"],
        )
        self._connect_to(init_preds, cond_node)

        # Body
        body_stmts = (stmt.stmt.block_items or []) if isinstance(stmt.stmt, c_ast.Compound) \
                     else ([stmt.stmt] if stmt.stmt else [])
        body_tails = self.build(body_stmts, [cond_node])

        # Next (increment) block
        if stmt.next:
            next_node = self._add_node(
                label=_stmt_str(stmt.next),
                block_type="body",
                statements=[_stmt_str(stmt.next)],
            )
            self._connect_to(body_tails, next_node)
            body_tails = [next_node]

        # Back-edge to condition
        for tail in body_tails:
            self.g.add_edge(tail, cond_node, label="back_edge", condition=cond_str)

        for u, v, data in list(self.g.out_edges(cond_node, data=True)):
            if data.get("label") == "sequential" and v != cond_node:
                self.g[u][v]["label"] = "true"
                self.g[u][v]["condition"] = cond_str

        return [cond_node]  # false exit

    # ------------------------------------------------------------------
    # do-while loop
    # ------------------------------------------------------------------

    def _build_dowhile(self, stmt: c_ast.DoWhile, preds: list[str]) -> list[str]:
        # Body executes first
        body_stmts = (stmt.stmt.block_items or []) if isinstance(stmt.stmt, c_ast.Compound) \
                     else ([stmt.stmt] if stmt.stmt else [])
        body_tails = self.build(body_stmts, preds)

        cond_str = _expr_to_str(stmt.cond)
        cond_node = self._add_node(
            label=f"do-while ({cond_str})",
            block_type="condition",
            statements=[f"do-while ({cond_str})"],
        )
        self._connect_to(body_tails, cond_node)

        # Back-edge (true) → start of body
        # Since body is already built, connect cond_node → first node of body
        # Find first body node (first successor of preds)
        first_body = None
        for p in preds:
            succs = list(self.g.successors(p))
            if succs:
                first_body = succs[0]
                break
        if first_body:
            self.g.add_edge(cond_node, first_body, label="back_edge", condition=cond_str)

        return [cond_node]  # false exit

    # ------------------------------------------------------------------
    # switch
    # ------------------------------------------------------------------

    def _build_switch(self, stmt: c_ast.Switch, preds: list[str]) -> list[str]:
        cond_str = _expr_to_str(stmt.cond)
        switch_node = self._add_node(
            label=f"switch ({cond_str})",
            block_type="condition",
            statements=[f"switch ({cond_str})"],
        )
        self._connect_to(preds, switch_node)

        case_tails: list[str] = []
        if isinstance(stmt.stmt, c_ast.Compound) and stmt.stmt.block_items:
            current_case_preds = [switch_node]
            for item in stmt.stmt.block_items:
                if isinstance(item, c_ast.Case):
                    val = _expr_to_str(item.expr)
                    case_node = self._add_node(
                        label=f"case {val}:",
                        block_type="body",
                        statements=[f"case {val}:"],
                    )
                    for p in [switch_node]:
                        self.g.add_edge(p, case_node, label=f"case_{val}",
                                        condition=f"{cond_str} == {val}")
                    stmts = item.stmts or []
                    tails = self.build(stmts, [case_node])
                    current_case_preds = tails
                    case_tails.extend(tails)
                elif isinstance(item, c_ast.Default):
                    default_node = self._add_node(
                        label="default:",
                        block_type="body",
                        statements=["default:"],
                    )
                    self.g.add_edge(switch_node, default_node,
                                    label="case_default", condition=f"{cond_str} (default)")
                    stmts = item.stmts or []
                    tails = self.build(stmts, [default_node])
                    case_tails.extend(tails)

        return case_tails or [switch_node]


# ---------------------------------------------------------------------------
# Public API — cleaner if-else approach using a two-pass strategy
# ---------------------------------------------------------------------------

class _CFGBuilderV2(_CFGBuilder):
    """
    Improved builder that handles if/else by building branches independently,
    then merging. This avoids the edge-relabeling hacks in the base class.
    """

    def _build_if(self, stmt: c_ast.If, preds: list[str]) -> list[str]:
        cond_str = _expr_to_str(stmt.cond)
        cond_node = self._add_node(
            label=f"if ({cond_str})",
            block_type="condition",
            statements=[f"if ({cond_str})"],
            source_lines=[_get_line(stmt.cond)] if _get_line(stmt.cond) else [],
        )
        self._connect_to(preds, cond_node)

        # True branch node
        true_entry = self._add_node(label="[true-branch]", block_type="body",
                                     statements=[], source_lines=[])
        self.g.add_edge(cond_node, true_entry, label="true", condition=cond_str)
        true_stmts = (stmt.iftrue.block_items or []) if isinstance(stmt.iftrue, c_ast.Compound) \
                     else ([stmt.iftrue] if stmt.iftrue else [])
        true_tails = self.build(true_stmts, [true_entry])

        # False branch
        if stmt.iffalse:
            false_entry = self._add_node(label="[false-branch]", block_type="body",
                                          statements=[], source_lines=[])
            self.g.add_edge(cond_node, false_entry, label="false", condition=f"!({cond_str})")
            false_stmts = (stmt.iffalse.block_items or []) \
                          if isinstance(stmt.iffalse, c_ast.Compound) else [stmt.iffalse]
            false_tails = self.build(false_stmts, [false_entry])
            all_tails = true_tails + false_tails
        else:
            # No else — false branch goes straight to merge
            all_tails = true_tails + [cond_node]
            # Add a direct false edge from cond_node that the merge will consume
            # We signal this by including cond_node in all_tails with a false edge marker
            # Actually just add the false edge directly to the merge after we create it
            all_tails = true_tails
            # cond_node will be connected via merge below with false label
            all_tails_with_cond_false = (true_tails, cond_node)

        if stmt.iffalse:
            if not all_tails:
                return []
            merge = self._add_node(label="[merge]", block_type="merge")
            self._connect_to(all_tails, merge)
        else:
            merge = self._add_node(label="[merge]", block_type="merge")
            self._connect_to(true_tails, merge)
            self.g.add_edge(cond_node, merge, label="false", condition=f"!({cond_str})")

        return [merge]


def build_cfg(parse_result: ParseResult, function_name: str = "main") -> CFGGraph:
    """
    Build a CFG from a ParseResult.

    Args:
        parse_result: Output of ast_parser.parse_c_source() / language_dispatcher
        function_name: Which function to build the CFG for (default: "main")

    Returns:
        CFGGraph with populated networkx DiGraph.
    """
    global _id_counter
    _id_counter = itertools.count()  # reset counter per CFG build

    if parse_result.language == "python" and parse_result.ast is not None:
        from app.core.python_cfg_builder import build_cfg_python
        return build_cfg_python(parse_result.ast, function_name=function_name)

    if parse_result.language in ("javascript", "typescript"):
        from app.core.javascript_cfg_builder import build_cfg_javascript
        return build_cfg_javascript(parse_result.source_code, function_name=function_name)

    if parse_result.ast is None:
        # Return an empty CFG if parsing failed
        g = nx.DiGraph()
        entry = "BB_0"
        exit_ = "BB_1"
        g.add_node(entry, label="ENTRY", block_type="entry", statements=[], source_lines=[])
        g.add_node(exit_, label="EXIT", block_type="exit", statements=[], source_lines=[])
        g.add_edge(entry, exit_, label="sequential", condition=None)
        return CFGGraph(graph=g, entry_node=entry, exit_node=exit_,
                        function_name=function_name, cyclomatic_complexity=1,
                        node_count=2, edge_count=1)

    # Find the target function definition
    target_func: c_ast.FuncDef | None = None
    for node in parse_result.ast.ext:
        if isinstance(node, c_ast.FuncDef):
            if node.decl.name == function_name:
                target_func = node
                break

    # Fallback: use the first function found
    if target_func is None:
        for node in parse_result.ast.ext:
            if isinstance(node, c_ast.FuncDef):
                target_func = node
                function_name = node.decl.name
                break

    g = nx.DiGraph()

    # Create ENTRY and EXIT nodes
    entry_id = _new_id()
    exit_id = _new_id()
    g.add_node(entry_id, label="ENTRY", block_type="entry", statements=[], source_lines=[])
    g.add_node(exit_id, label="EXIT", block_type="exit", statements=[], source_lines=[])

    if target_func is None or target_func.body is None:
        g.add_edge(entry_id, exit_id, label="sequential", condition=None)
        return CFGGraph(graph=g, entry_node=entry_id, exit_node=exit_id,
                        function_name=function_name, cyclomatic_complexity=1,
                        node_count=2, edge_count=1)

    builder = _CFGBuilderV2(g, exit_id)
    stmts = target_func.body.block_items or []
    open_tails = builder.build(stmts, [entry_id])

    # Connect any dangling tails to EXIT
    for tail in open_tails:
        if not any(True for _ in g.successors(tail)):
            g.add_edge(tail, exit_id, label="sequential", condition=None)

    # Cyclomatic complexity: E - N + 2P (P=1 for single function)
    E = g.number_of_edges()
    N = g.number_of_nodes()
    cc = E - N + 2

    return CFGGraph(
        graph=g,
        entry_node=entry_id,
        exit_node=exit_id,
        function_name=function_name,
        cyclomatic_complexity=max(1, cc),
        node_count=N,
        edge_count=E,
    )


def cfg_to_json(cfg: CFGGraph) -> dict:
    """
    Serialise a CFGGraph to a JSON-compatible dict suitable for the API response
    and for react-flow rendering.
    """
    nodes = []
    for nid, data in cfg.graph.nodes(data=True):
        nodes.append({
            "id": nid,
            "label": data.get("label", nid),
            "block_type": data.get("block_type", "body"),
            "statements": data.get("statements", []),
            "source_lines": data.get("source_lines", []),
        })

    edges = []
    for u, v, data in cfg.graph.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "label": data.get("label", "sequential"),
            "condition": data.get("condition"),
        })

    return {
        "function_name": cfg.function_name,
        "entry_node": cfg.entry_node,
        "exit_node": cfg.exit_node,
        "cyclomatic_complexity": cfg.cyclomatic_complexity,
        "node_count": cfg.node_count,
        "edge_count": cfg.edge_count,
        "nodes": nodes,
        "edges": edges,
    }
