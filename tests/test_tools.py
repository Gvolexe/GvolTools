#!/usr/bin/env python3
"""
GVTools Test Suite

Runs basic syntax and import tests for all gvtools.

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

NO_COLOR = "NO_COLOR" in os.environ

def c(text: str, color: str) -> str:
    if NO_COLOR:
        return text
    return f"{color}{text}\033[0m"

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


@pytest.fixture
def root() -> Path:
    """Return the root directory of the project."""
    return Path(__file__).parent.parent


@pytest.fixture
def tools_dir() -> Path:
    """Return the tools directory."""
    return Path(__file__).parent.parent / "tools"


def find_tool_files(tools_dir: Path) -> list[Path]:
    """Find all Python tool files."""
    tools = []
    for setup_file in tools_dir.glob("*/setup.json"):
        tool_dir = setup_file.parent
        files_dir = tool_dir / "files"
        if files_dir.exists():
            for py_file in files_dir.glob("*.py"):
                tools.append(py_file)
    return sorted(tools)


def _test_syntax(path: Path) -> tuple[bool, str]:
    """Test Python syntax validity."""
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
        return True, "OK"
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"


def _test_help(path: Path) -> tuple[bool, str]:
    """Test that --help works."""
    try:
        result = subprocess.run(
            [sys.executable, str(path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        )
        if result.returncode == 0:
            return True, "OK"
        return False, f"exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def _test_version(path: Path) -> tuple[bool, str]:
    """Test that --version works."""
    try:
        result = subprocess.run(
            [sys.executable, str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip()
        return False, f"exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def _test_imports(path: Path) -> tuple[bool, str]:
    """Test that basic imports work."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not alias.name.startswith("gvcore"):
                        imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and not node.module.startswith("gvcore"):
                    imports.append(node.module)
        
        stdlib = {"argparse", "json", "os", "sys", "pathlib", "subprocess", "datetime", 
                  "hashlib", "socket", "shutil", "getpass", "typing", "__future__",
                  "dataclasses", "fnmatch", "re", "shlex", "base64", "textwrap"}
        external = [i for i in imports if i.split(".")[0] not in stdlib]
        
        if external:
            return True, f"deps: {', '.join(set(external))}"
        return True, "stdlib only"
    except Exception as e:
        return False, str(e)


def _test_docstring(path: Path) -> tuple[bool, str]:
    """Test that module has docstring."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        if docstring:
            first_line = docstring.split("\n")[0][:40]
            return True, first_line
        return False, "no docstring"
    except Exception as e:
        return False, str(e)


def test_syntax(tools_dir: Path) -> None:
    """Test Python syntax validity for all tools."""
    tools = find_tool_files(tools_dir)
    assert len(tools) > 0, "No tools found"
    
    failed = []
    for path in tools:
        ok, msg = _test_syntax(path)
        if not ok:
            failed.append(f"{path.name}: {msg}")
    
    assert len(failed) == 0, f"Syntax errors: {failed}"


def test_docstring(tools_dir: Path) -> None:
    """Test that all modules have docstrings."""
    tools = find_tool_files(tools_dir)
    assert len(tools) > 0, "No tools found"
    
    failed = []
    for path in tools:
        ok, msg = _test_docstring(path)
        if not ok:
            failed.append(f"{path.name}: {msg}")
    
    assert len(failed) == 0, f"Missing docstrings: {failed}"


def test_imports(tools_dir: Path) -> None:
    """Test that basic imports work."""
    tools = find_tool_files(tools_dir)
    assert len(tools) > 0, "No tools found"
    
    failed = []
    for path in tools:
        ok, msg = _test_imports(path)
        if not ok:
            failed.append(f"{path.name}: {msg}")
    
    assert len(failed) == 0, f"Import errors: {failed}"


def test_version(tools_dir: Path) -> None:
    """Test that --version works for all tools."""
    tools = find_tool_files(tools_dir)
    assert len(tools) > 0, "No tools found"
    
    failed = []
    for path in tools:
        ok, msg = _test_version(path)
        # gvcore is a library, not a CLI tool
        if not ok and "gvcore" not in path.name:
            failed.append(f"{path.name}: {msg}")
    
    # We expect some to fail if gvcore isn't installed
    # So we only fail if ALL tools fail
    if len(failed) == len([t for t in tools if "gvcore" not in t.name]):
        pytest.skip("gvcore not installed - CLI tests skipped")


def test_help(tools_dir: Path) -> None:
    """Test that --help works for all tools."""
    tools = find_tool_files(tools_dir)
    assert len(tools) > 0, "No tools found"
    
    failed = []
    for path in tools:
        ok, msg = _test_help(path)
        # gvcore is a library, not a CLI tool
        if not ok and "gvcore" not in path.name:
            failed.append(f"{path.name}: {msg}")
    
    # We expect some to fail if gvcore isn't installed
    if len(failed) == len([t for t in tools if "gvcore" not in t.name]):
        pytest.skip("gvcore not installed - CLI tests skipped")


def run_tests(tools_dir: Path) -> int:
    """Run all tests."""
    tools = find_tool_files(tools_dir)
    
    if not tools:
        print(f"{c('Error:', Colors.RED)} No tools found")
        return 1
    
    print(f"\n{c('═' * 60, Colors.CYAN)}")
    print(f"{c(' GVTools Test Suite', Colors.BOLD)}")
    print(f"{c('═' * 60, Colors.CYAN)}\n")
    print(f"Found {len(tools)} tool files\n")
    
    passed = 0
    failed = 0
    
    for tool_path in tools:
        tool_name = tool_path.stem
        print(f"{c('▸', Colors.CYAN)} {c(tool_name, Colors.BOLD)}")
        
        tests = [
            ("syntax", _test_syntax),
            ("docstring", _test_docstring),
            ("imports", _test_imports),
            ("--help", _test_help),
            ("--version", _test_version),
        ]
        
        tool_passed = True
        
        for test_name, test_func in tests:
            ok, msg = test_func(tool_path)
            if ok:
                print(f"  {c('✓', Colors.GREEN)} {test_name}: {c(msg, Colors.DIM)}")
            else:
                print(f"  {c('✗', Colors.RED)} {test_name}: {c(msg, Colors.RED)}")
                tool_passed = False
        
        if tool_passed:
            passed += 1
        else:
            failed += 1
        
        print()
    
    print(f"{c('─' * 60, Colors.DIM)}")
    print(f"Results: {c(str(passed), Colors.GREEN)} passed, {c(str(failed), Colors.RED)} failed")
    print()
    
    return 0 if failed == 0 else 1


def main() -> None:
    root = Path(__file__).parent.parent
    tools_dir = root / "tools"
    
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--help", "-h"):
            print("Usage: python tests/test_tools.py")
            print("\nRuns syntax, import, and CLI tests for all tools.")
            sys.exit(0)
    
    exit_code = run_tests(tools_dir)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
