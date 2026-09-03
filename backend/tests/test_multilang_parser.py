"""
Tests for Multi-Language Parser Support
========================================
Validates that the language dispatcher correctly routes to
the appropriate parser and produces consistent output.
"""
import pytest

from app.core.language_dispatcher import parse_source, get_language_from_filename
from app.core.python_parser import parse_python_source
from app.core.javascript_parser import parse_javascript_source


class TestLanguageDispatcher:
    """Test the unified language dispatcher."""

    def test_dispatch_c_language(self):
        code = "int main() { if (x >= 10) { return 1; } }"
        result = parse_source(code, "c")
        assert result.conditions is not None

    def test_dispatch_python_language(self):
        code = "if x >= 10:\n    return 1"
        result = parse_source(code, "python")
        assert result.conditions is not None
        assert len(result.conditions) >= 1

    def test_dispatch_javascript_language(self):
        code = "if (x >= 10) { return 1; }"
        result = parse_source(code, "javascript")
        assert result.conditions is not None
        assert len(result.conditions) >= 1

    def test_dispatch_typescript_language(self):
        code = "if (x >= 10) { return 1; }"
        result = parse_source(code, "typescript")
        assert result.conditions is not None

    def test_unsupported_language_raises(self):
        with pytest.raises(ValueError, match="Unsupported language"):
            parse_source("code", "ruby")

    def test_case_insensitive_language(self):
        code = "if x >= 10:\n    return 1"
        result = parse_source(code, "PYTHON")
        assert result.conditions is not None


class TestPythonParser:
    """Test Python-specific parsing."""

    def test_simple_if(self):
        code = """
x = 15
if x >= 10:
    print("big")
"""
        result = parse_python_source(code)
        assert len(result.conditions) == 1
        assert result.conditions[0].operator == ">="
        assert "x" in result.conditions[0].variables

    def test_if_else(self):
        code = """
x = 15
if x >= 10:
    print("big")
else:
    print("small")
"""
        result = parse_python_source(code)
        assert len(result.conditions) == 1

    def test_nested_if(self):
        code = """
score = 85
if score >= 90:
    grade = "A"
elif score >= 75:
    grade = "B"
elif score >= 50:
    grade = "C"
else:
    grade = "F"
"""
        result = parse_python_source(code)
        assert len(result.conditions) == 3

    def test_while_loop(self):
        code = """
count = 0
while count < 10:
    count += 1
"""
        result = parse_python_source(code)
        assert len(result.conditions) == 1
        assert result.conditions[0].operator == "<"

    def test_type_inference(self):
        code = """
def foo(age: int) -> int:
    if age >= 18:
        return 1
    return 0
"""
        result = parse_python_source(code)
        assert len(result.conditions) == 1
        assert "age" in result.conditions[0].variables

    def test_syntax_error_handling(self):
        code = "def foo(\n  invalid syntax"
        result = parse_python_source(code)
        assert len(result.parse_errors) > 0


class TestJavaScriptParser:
    """Test JavaScript-specific parsing."""

    def test_simple_if(self):
        code = """
const x = 15;
if (x >= 10) {
    console.log("big");
}
"""
        result = parse_javascript_source(code)
        assert len(result.conditions) == 1
        assert result.conditions[0].operator in (">=", "===")

    def test_if_else_if(self):
        code = """
const score = 85;
if (score >= 90) {
    console.log("A");
} else if (score >= 75) {
    console.log("B");
} else if (score >= 50) {
    console.log("C");
} else {
    console.log("F");
}
"""
        result = parse_javascript_source(code)
        assert len(result.conditions) == 3

    def test_while_loop(self):
        code = """
let count = 0;
while (count < 10) {
    count++;
}
"""
        result = parse_javascript_source(code)
        assert len(result.conditions) == 1

    def test_for_loop(self):
        code = """
for (let i = 0; i < 10; i++) {
    console.log(i);
}
"""
        result = parse_javascript_source(code)
        assert len(result.conditions) == 1

    def test_switch_statement(self):
        code = """
switch (grade) {
    case "A":
        console.log("Excellent");
        break;
    case "B":
        console.log("Good");
        break;
}
"""
        result = parse_javascript_source(code)
        assert len(result.conditions) == 1
        assert result.conditions[0].ast_node_type == "Switch"

    def test_unbalanced_braces_error(self):
        code = "if (x > 0) {"
        result = parse_javascript_source(code)
        assert len(result.parse_errors) > 0


class TestFilenameLanguageDetection:
    """Test language detection from filenames."""

    def test_c_file(self):
        assert get_language_from_filename("main.c") == "c"
        assert get_language_from_filename("header.h") == "c"

    def test_python_file(self):
        assert get_language_from_filename("script.py") == "python"
        assert get_language_from_filename("script.pyw") == "python"

    def test_javascript_file(self):
        assert get_language_from_filename("app.js") == "javascript"
        assert get_language_from_filename("component.jsx") == "javascript"

    def test_typescript_file(self):
        assert get_language_from_filename("app.ts") == "typescript"
        assert get_language_from_filename("component.tsx") == "typescript"

    def test_unknown_extension_defaults_to_c(self):
        assert get_language_from_filename("file.txt") == "c"
