"""
Module — Language Dispatcher
==============================
Unified entry point for multi-language parsing. Routes source code
to the appropriate parser based on language selection.

Supported languages:
- "c" — C source (pycparser)
- "python" — Python source (ast module)
- "javascript" / "typescript" — JS/TS source (regex-based)

All parsers return the same ParseResult structure, enabling the
downstream pipeline (CFG, solver, test cases) to be language-agnostic.
"""

from __future__ import annotations

from typing import Literal

from app.core.ast_parser import ParseResult, parse_c_source
from app.core.python_parser import parse_python_source
from app.core.javascript_parser import parse_javascript_source


# Supported language identifiers
SUPPORTED_LANGUAGES = ("c", "python", "javascript", "typescript")

Language = Literal["c", "python", "javascript", "typescript"]


def parse_source(source_code: str, language: str = "c") -> ParseResult:
    """
    Parse source code in the specified language.

    Args:
        source_code: Raw source code string.
        language: One of "c", "python", "javascript", "typescript".

    Returns:
        ParseResult with conditions and metadata.

    Raises:
        ValueError: If language is not supported.
    """
    lang = language.lower().strip()

    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language: '{language}'. "
            f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    if lang == "c":
        return parse_c_source(source_code)
    elif lang == "python":
        return parse_python_source(source_code)
    elif lang in ("javascript", "typescript"):
        return parse_javascript_source(source_code)
    else:
        # Should never reach here due to validation above
        raise ValueError(f"Unsupported language: '{language}'")


def get_language_from_filename(filename: str) -> str:
    """
    Infer language from file extension.

    Args:
        filename: Name of the source file.

    Returns:
        Language identifier string.
    """
    if filename.endswith(('.c', '.h')):
        return "c"
    elif filename.endswith(('.py', '.pyw')):
        return "python"
    elif filename.endswith(('.js', '.jsx', '.mjs', '.cjs')):
        return "javascript"
    elif filename.endswith(('.ts', '.tsx', '.mts', '.cts')):
        return "typescript"
    else:
        return "c"  # Default fallback
