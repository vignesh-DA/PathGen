"""
Module 2 — Path Enumerator
==========================
Enumerates all distinct root-to-sink paths through the CFG,
respecting the configured loop-unrolling bound.

Strategy:
- Use a depth-first traversal of the networkx DiGraph.
- Detect back-edges (edges where target is already in the current path stack)
  and limit revisits to MAX_LOOP_ITERATIONS.
- Emit a path when EXIT node is reached.
- Cap total paths at MAX_PATHS to prevent combinatorial explosion.

Each emitted path is a list of (node_id, edge_label, condition) tuples
representing the sequence of decisions taken.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from app.config import settings
from app.core.cfg_builder import CFGGraph


@dataclass
class PathStep:
    node_id: str
    node_label: str
    edge_label: str | None        # label of edge FROM previous node TO this node
    edge_condition: str | None    # condition expression on that edge


@dataclass
class CFGPath:
    path_id: str
    steps: list[PathStep]        # ordered sequence from ENTRY to EXIT
    conditions_taken: list[dict] # [{condition_expr, branch_taken: "true"/"false"}]
    is_loop_bounded: bool        # True if any back-edge was bounded


def enumerate_paths(cfg: CFGGraph,
                    max_paths: int | None = None,
                    max_loop_iters: int | None = None) -> list[CFGPath]:
    """
    Enumerate all CFG paths from ENTRY to EXIT.

    Args:
        cfg: CFGGraph from cfg_builder
        max_paths: Override settings.max_paths
        max_loop_iters: Override settings.max_loop_iterations

    Returns:
        List of CFGPath objects, one per distinct execution path.
    """
    max_p = max_paths if max_paths is not None else settings.max_paths
    max_l = max_loop_iters if max_loop_iters is not None else settings.max_loop_iterations

    g = cfg.graph
    entry = cfg.entry_node
    exit_ = cfg.exit_node

    paths: list[CFGPath] = []
    path_counter = [0]

    def dfs(
        node: str,
        current_path: list[PathStep],
        visit_count: dict[str, int],
        conditions_taken: list[dict],
        has_back_edge: bool,
    ):
        if len(paths) >= max_p:
            return

        node_data = g.nodes[node]
        node_label = node_data.get("label", node)

        if node == exit_:
            # Emit this path
            path_counter[0] += 1
            paths.append(CFGPath(
                path_id=f"P{path_counter[0]:03d}",
                steps=list(current_path),
                conditions_taken=list(conditions_taken),
                is_loop_bounded=has_back_edge,
            ))
            return

        # Iterate outgoing edges
        for _, neighbor, edge_data in g.out_edges(node, data=True):
            edge_label = edge_data.get("label", "sequential")
            edge_cond = edge_data.get("condition")

            # Back-edge detection: neighbor is already in current path
            is_back_edge = edge_label == "back_edge" or neighbor in {
                s.node_id for s in current_path
            }

            # Loop bound check
            if is_back_edge:
                if visit_count.get(neighbor, 0) >= max_l:
                    continue  # skip: loop exhausted
                new_visit_count = dict(visit_count)
                new_visit_count[neighbor] = new_visit_count.get(neighbor, 0) + 1
            else:
                # Prevent infinite non-loop cycles (shouldn't happen in well-formed CFG)
                if visit_count.get(neighbor, 0) >= 1 and neighbor != exit_:
                    if edge_label not in ("sequential", "true", "false"):
                        continue
                new_visit_count = dict(visit_count)
                new_visit_count[neighbor] = new_visit_count.get(neighbor, 0) + 1

            # Record condition decision
            new_conditions = list(conditions_taken)
            if edge_cond and edge_label in ("true", "false"):
                new_conditions.append({
                    "condition_expr": edge_cond,
                    "branch_taken": edge_label,
                    "from_node": node,
                    "to_node": neighbor,
                })

            new_step = PathStep(
                node_id=neighbor,
                node_label=g.nodes[neighbor].get("label", neighbor),
                edge_label=edge_label,
                edge_condition=edge_cond,
            )

            dfs(
                neighbor,
                current_path + [new_step],
                new_visit_count,
                new_conditions,
                has_back_edge or is_back_edge,
            )

    entry_step = PathStep(
        node_id=entry,
        node_label=g.nodes[entry].get("label", "ENTRY"),
        edge_label=None,
        edge_condition=None,
    )
    dfs(entry, [entry_step], {entry: 1}, [], False)

    return paths
