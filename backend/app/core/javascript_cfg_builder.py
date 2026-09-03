"""
Module — JavaScript/TS CFG Builder
==================================
Builds a Control Flow Graph from JS/TS source using line + brace structure
(no full AST available from the regex parser).

Produces the same CFGGraph anatomy as the C/Python builders.
Supported: if/else if/else, while, for, do-while, switch/case (structural),
return, plain statements grouped into blocks.
"""

from __future__ import annotations

import itertools
import re

import networkx as nx

from app.core.cfg_builder import CFGGraph

_id_counter = itertools.count()


def _new_id() -> str:
    return f"BB_{next(_id_counter)}"


# Preprocessor: strip comments (keep strings intact)
def _strip_comments(source: str) -> str:
    out = []
    i, n = 0, len(source)
    in_str, ch = False, ""
    while i < n:
        c = source[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 2
                continue
            if c == ch:
                in_str = False
            i += 1
        elif c in "\"'`":
            in_str, ch = True, c
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and source[i + 1] == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                i += 1
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _count_code_braces(line: str) -> tuple[int, int]:
    """Net open/close braces on a line, ignoring strings."""
    opens = closes = 0
    in_str, ch = False, ""
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == ch:
                in_str = False
        elif c in "\"'`":
            in_str, ch = True, c
        elif c == "{":
            opens += 1
        elif c == "}":
            closes += 1
        i += 1
    return opens, closes


class _Line:
    __slots__ = ("text", "no")
    def __init__(self, text: str, no: int):
        self.text = text
        self.no = no


class _JSCFGBuilder:
    """Recursive line-block walker for JS/TS source."""

    BRANCH_RE = re.compile(r"^\s*(?:async\s+)?(if|while|for|switch|do)\b\s*[\({]?(.*)$")
    RETURN_RE = re.compile(r"^\s*return\b")

    def __init__(self, g: nx.DiGraph, exit_node: str):
        self.g = g
        self.exit_node = exit_node

    def _add_node(self, label, block_type, statements=None, source_lines=None):
        nid = _new_id()
        self.g.add_node(nid, label=label, block_type=block_type,
                        statements=statements or [],
                        source_lines=source_lines or [])
        return nid

    def _connect(self, preds, dst, label="sequential", condition=None):
        for p in preds:
            self.g.add_edge(p, dst, label=label, condition=condition)

    # ------------------------------------------------------------------
    def build(self, lines: list[_Line], preds: list[str]) -> list[str]:
        """Process a flat list of body lines; returns open tail nodes."""
        current = preds
        block: list[_Line] = []
        i = 0

        def flush():
            nonlocal block, current
            if not block:
                return current
            texts = [ln.text.strip().rstrip(";") for ln in block]
            nid = self._add_node(
                label=texts[0] if len(texts) == 1 else f"{texts[0]} [+{len(texts) - 1}]",
                block_type="body",
                statements=texts,
                source_lines=[ln.no for ln in block],
            )
            self._connect(current, nid)
            block.clear()
            return [nid]

        while i < len(lines):
            ln = lines[i]
            m = self.BRANCH_RE.match(ln.text)
            if m:
                current = flush()
                kw = m.group(1)
                if kw == "do":
                    current, i = self._build_do(lines, i, current)
                else:
                    current, i = self._build_conditional(lines, i, current, kw)
                continue
            if self.RETURN_RE.match(ln.text):
                block.append(ln)
                current = flush()
                if current:
                    self._connect(current, self.exit_node)
                current = []
                i += 1
                continue
            block.append(ln)
            i += 1

        return flush()

    # ------------------------------------------------------------------
    def _find_block_end(self, lines: list[_Line], start: int) -> int:
        """Given index of a line containing the body's opening '{', return the
        index just past its matching '}'. If the statement has no '{', the
        block is the single line itself."""
        depth = 0
        seen_open = False
        for j in range(start, len(lines)):
            o, c = _count_code_braces(lines[j].text)
            depth += o - c
            if o > 0:
                seen_open = True
            if seen_open and depth <= 0:
                return j + 1
            if not seen_open and o == 0 and c == 0 and ";" in lines[j].text and j > start:
                return j
        return len(lines)

    def _split_header_body(self, lines: list[_Line], start: int):
        """Return (header_text, body_lines, next_index). Handles one-line
        bodies like `if (x) return 1;`."""
        line = lines[start]
        o, c = _count_code_braces(line.text)
        if o > c:
            end = self._find_block_end(lines, start)
            body = lines[start + 1:end - 1] if end - 1 > start + 1 or _count_code_braces(lines[end - 1].text)[1] else lines[start + 1:end]
            body = [l for l in body if l.text.strip() != "}"]
            return line.text, body, end
        inner = line.text.strip()
        if ")" in inner:
            header_end = inner.index(")")
            after = inner[header_end + 1:].strip()
            if after:
                body = [_Line(after, line.no)]
                return inner[:header_end + 1], body, start + 1
        if start + 1 < len(lines):
            return inner, [lines[start + 1]], start + 2
        return inner, [], start + 1

    def _else_follows(self, lines: list[_Line], idx: int):
        """If an else/else-if directly follows the block ending at idx, return
        (else_lines_start, else_end, next_idx) else None."""
        if idx >= len(lines):
            return None
        text = lines[idx].text.strip()
        if re.match(r"^}\s*else\b", text) or text.startswith("else"):
            header = lines[idx].text
            o, c = _count_code_braces(header)
            if o > c or "{" in header.split("else")[-1]:
                end = self._find_block_end(lines, idx)
                body = [l for l in lines[idx + 1:end] if l.text.strip() != "}" and not l.text.strip().startswith("} else")]
                return idx, body, end
            if idx + 1 < len(lines):
                return idx, [lines[idx + 1]], idx + 2
            return None
        return None

    def _extract_cond_expr(self, header: str, kw: str) -> str:
        m = re.search(r"\((.*)\)", header)
        if m:
            return m.group(1).strip()
        return header.strip()

    def _build_conditional(self, lines: list[_Line], idx: int, preds: list[str], kw: str) -> tuple[list[str], int]:
        header_text, body_lines, next_idx = self._split_header_body(lines, idx)
        cond_str = self._extract_cond_expr(header_text, kw)
        cond_node = self._add_node(
            label=f"{kw} ({cond_str})",
            block_type="condition",
            statements=[header_text.strip()],
            source_lines=[lines[idx].no],
        )
        self._connect(preds, cond_node)

        if kw == "if":
            true_entry = self._add_node(label="[true-branch]", block_type="body")
            self.g.add_edge(cond_node, true_entry, label="true", condition=cond_str)
            true_tails = self.build(body_lines, [true_entry])

            else_info = self._else_follows(lines, next_idx)
            if else_info:
                else_line, else_body, else_end = else_info
                false_entry = self._add_node(label="[false-branch]", block_type="body")
                self.g.add_edge(cond_node, false_entry, label="false", condition=f"!({cond_str})")
                else_text = lines[else_line].text.strip() if else_line < len(lines) else ""
                if re.match(r"^else\s+if\b", else_text):
                    # else-if chain: rewrite `else if (...)` as a virtual `if (...)`
                    # header and recurse so the nested condition gets its own node
                    new_text = re.sub(r"^else\s+if\b", "if", lines[else_line].text)
                    sub = [_Line(new_text, lines[else_line].no)] + lines[else_line + 1:]
                    false_tails, sub_next = self._build_conditional(sub, 0, [false_entry], "if")
                    else_end = (else_line + 1) + sub_next
                    false_tails = false_tails
                else:
                    false_tails = self.build(else_body, [false_entry])
                merge = self._add_node(label="[merge]", block_type="merge")
                self._connect(list(true_tails) + list(false_tails), merge)
                return [merge], else_end
            else:
                merge = self._add_node(label="[merge]", block_type="merge")
                self._connect(true_tails, merge)
                self.g.add_edge(cond_node, merge, label="false", condition=f"!({cond_str})")
                return [merge], next_idx
        elif kw in ("while", "for"):
            body_entry = self._add_node(label="[loop-body]", block_type="body")
            self.g.add_edge(cond_node, body_entry, label="true", condition=cond_str)
            body_tails = self.build(body_lines, [body_entry])
            self._connect(body_tails, cond_node, label="back_edge")
            merge = self._add_node(label="[merge]", block_type="merge")
            self.g.add_edge(cond_node, merge, label="false", condition=f"!({cond_str})")
            return [merge], next_idx
        else:  # switch or other
            body_tails = self.build(body_lines, [cond_node])
            return body_tails, next_idx

    def _build_do(self, lines: list[_Line], idx: int, preds: list[str]) -> tuple[list[str], int]:
        header_text, body_lines, next_idx = self._split_header_body(lines, idx)
        body_entry = self._add_node(label="[do-body]", block_type="body")
        self._connect(preds, body_entry)
        body_tails = self.build(body_lines, [body_entry])

        cond_str = "condition"
        cond_no = lines[idx].no
        if next_idx < len(lines) and "while" in lines[next_idx].text:
            m = re.search(r"while\s*\((.*)\)", lines[next_idx].text)
            if m:
                cond_str = m.group(1).strip()
            cond_no = lines[next_idx].no
            next_idx += 1

        cond_node = self._add_node(
            label=f"while ({cond_str})",
            block_type="condition",
            statements=[f"while ({cond_str})"],
            source_lines=[cond_no],
        )
        self._connect(body_tails, cond_node)
        self.g.add_edge(cond_node, body_entry, label="back_edge", condition=cond_str)
        merge = self._add_node(label="[merge]", block_type="merge")
        self.g.add_edge(cond_node, merge, label="false", condition=f"!({cond_str})")
        return [merge], next_idx


def _find_js_function_lines(source: str, function_name: str) -> list[_Line]:
    cleaned = _strip_comments(source)
    raw_lines = cleaned.splitlines()
    all_lines = [_Line(line, i + 1) for i, line in enumerate(raw_lines) if line.strip()]

    fn_pattern = re.compile(rf"(?:function\s+{function_name}|const\s+{function_name}\s*=|(?:async\s+)?function\s+{function_name})\b")
    fn_start = -1
    for idx, l in enumerate(all_lines):
        if fn_pattern.search(l.text):
            fn_start = idx
            break

    if fn_start == -1:
        any_fn = re.compile(r"(?:function\s+([a-zA-Z0-9_$]+)|(?:async\s+)?function\s+([a-zA-Z0-9_$]+))\b")
        for idx, l in enumerate(all_lines):
            if any_fn.search(l.text):
                fn_start = idx
                break

    if fn_start != -1:
        body_lines = []
        depth = 0
        seen_open = False
        for l in all_lines[fn_start:]:
            o, c = _count_code_braces(l.text)
            depth += o - c
            if o > 0:
                seen_open = True
            if seen_open:
                body_lines.append(l)
                if depth <= 0:
                    break
        if body_lines:
            inner = body_lines[1:-1] if len(body_lines) > 2 and body_lines[-1].text.strip() == "}" else body_lines[1:]
            return _split_else_lines(inner)

    return _split_else_lines(all_lines)


def _split_else_lines(lines: list[_Line]) -> list[_Line]:
    """Split `} else ...` so the closing brace and the else clause live on
    separate lines. This makes block scanning and else-if chains uniform."""
    out: list[_Line] = []
    pattern = re.compile(r"^(.*\})\s*(else\b.*)$")
    for l in lines:
        m = pattern.match(l.text.strip())
        if m and not l.text.strip().startswith("else"):
            out.append(_Line(m.group(1), l.no))
            out.append(_Line(m.group(2), l.no))
        else:
            out.append(l)
    return out


def build_cfg_javascript(source_code: str, function_name: str = "main") -> CFGGraph:
    """
    Build a CFG from JS/TS source code.
    """
    global _id_counter
    _id_counter = itertools.count()

    g = nx.DiGraph()
    entry = _new_id()
    exit_id = _new_id()
    g.add_node(entry, label="ENTRY", block_type="entry", statements=[], source_lines=[])
    g.add_node(exit_id, label="EXIT", block_type="exit", statements=[], source_lines=[])

    lines = _find_js_function_lines(source_code, function_name)
    if not lines:
        g.add_edge(entry, exit_id, label="sequential", condition=None)
        return CFGGraph(graph=g, entry_node=entry, exit_node=exit_id,
                        function_name=function_name, cyclomatic_complexity=1,
                        node_count=2, edge_count=1)

    builder = _JSCFGBuilder(g, exit_id)
    tails = builder.build(lines, [entry])
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
