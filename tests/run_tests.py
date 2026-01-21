#!/usr/bin/env python3
"""
Standalone test runner for GVTools - no external dependencies.

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

NO_COLOR = "NO_COLOR" in os.environ or not sys.stdout.isatty()

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


def find_all_tools(tools_dir: Path) -> list[tuple[str, Path]]:
    """Find all tool Python files."""
    tools = []
    for setup_file in sorted(tools_dir.glob("*/setup.json")):
        tool_dir = setup_file.parent
        tool_name = tool_dir.name
        files_dir = tool_dir / "files"
        if files_dir.exists():
            py_file = files_dir / f"{tool_name}.py"
            if py_file.exists():
                tools.append((tool_name, py_file))
    return tools


def test_syntax(path: Path) -> tuple[bool, str]:
    """Test Python syntax validity."""
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
        return True, "OK"
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def test_docstring(path: Path) -> tuple[bool, str]:
    """Test that module has docstring."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree)
        if docstring:
            first_line = docstring.split("\n")[0][:40]
            return True, first_line
        return False, "missing"
    except Exception as e:
        return False, str(e)


def test_main_function(path: Path) -> tuple[bool, str]:
    """Test that tool has main() function."""
    # gvcore is a library, not a CLI tool
    if "gvcore" in path.name:
        return True, "library"
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        if "main" in funcs:
            return True, "OK"
        return False, "no main()"
    except Exception as e:
        return False, str(e)


def test_gvcore_import(path: Path) -> tuple[bool, str]:
    """Test that tool imports gvcore."""
    try:
        source = path.read_text(encoding="utf-8")
        if "from gvcore import" in source:
            return True, "OK"
        # gvcore itself doesn't import gvcore
        if "gvcore" in path.name:
            return True, "self"
        return False, "not imported"
    except Exception as e:
        return False, str(e)


def test_setup_json(tools_dir: Path, tool_name: str) -> tuple[bool, str]:
    """Test that setup.json is valid."""
    setup_file = tools_dir / tool_name / "setup.json"
    if not setup_file.exists():
        return False, "missing"
    
    try:
        setup = json.loads(setup_file.read_text(encoding="utf-8"))
        missing = []
        if "tool" not in setup:
            missing.append("tool")
        if "version" not in setup:
            missing.append("version")
        if "install" not in setup:
            missing.append("install")
        
        if missing:
            return False, f"missing: {', '.join(missing)}"
        
        return True, setup.get("version", "?")
    except json.JSONDecodeError as e:
        return False, f"JSON error: {e}"
    except Exception as e:
        return False, str(e)


def test_help(path: Path) -> tuple[bool, str]:
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
        return False, f"exit {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:30]


def test_version(path: Path) -> tuple[bool, str]:
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
            return True, result.stdout.strip().split()[-1]
        return False, f"exit {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)[:30]


def test_json_mode_support(path: Path) -> tuple[bool, str]:
    """Test that tool supports --json mode."""
    try:
        # gvcore and some older utilities may not need json mode
        tool_name = path.stem
        if tool_name in ("gvcore", "gv"):
            return True, "N/A"
        
        source = path.read_text(encoding="utf-8")
        if "json_mode" in source:
            return True, "OK"
        return False, "missing"
    except Exception as e:
        return False, str(e)


def run_tests() -> int:
    """Run all tests."""
    root = Path(__file__).parent.parent
    tools_dir = root / "tools"
    
    tools = find_all_tools(tools_dir)
    
    if not tools:
        print(f"{c('Error:', Colors.RED)} No tools found in {tools_dir}")
        return 1
    
    print()
    print(f"{c('═' * 70, Colors.CYAN)}")
    print(f"{c(' GVTools Test Suite', Colors.BOLD)}")
    print(f"{c('═' * 70, Colors.CYAN)}")
    print(f"\nFound {len(tools)} tools\n")
    
    total_passed = 0
    total_failed = 0
    
    # Track which tests are skipped due to missing gvcore
    gvcore_tests_skipped = False
    
    for tool_name, tool_path in tools:
        print(f"{c('▸', Colors.CYAN)} {c(tool_name, Colors.BOLD)}")
        
        tool_passed = True
        
        # Static analysis tests (always run)
        tests_static = [
            ("syntax", test_syntax(tool_path)),
            ("docstring", test_docstring(tool_path)),
            ("main()", test_main_function(tool_path)),
            ("gvcore", test_gvcore_import(tool_path)),
            ("setup.json", test_setup_json(tools_dir, tool_name)),
        ]
        
        for test_name, (ok, msg) in tests_static:
            if ok:
                print(f"  {c('✓', Colors.GREEN)} {test_name}: {c(msg, Colors.DIM)}")
            else:
                print(f"  {c('✗', Colors.RED)} {test_name}: {c(msg, Colors.RED)}")
                tool_passed = False
        
        # CLI tests (may fail if gvcore not installed)
        # Skip for gvcore itself (it's a library)
        if tool_name != "gvcore":
            help_ok, help_msg = test_help(tool_path)
            version_ok, version_msg = test_version(tool_path)
            
            if help_ok:
                print(f"  {c('✓', Colors.GREEN)} --help: {c(help_msg, Colors.DIM)}")
            else:
                # Check if it's a gvcore import error
                if "gvcore" in help_msg.lower() or "no module" in help_msg.lower():
                    print(f"  {c('○', Colors.YELLOW)} --help: {c('skipped (gvcore not installed)', Colors.DIM)}")
                    gvcore_tests_skipped = True
                else:
                    print(f"  {c('✗', Colors.RED)} --help: {c(help_msg, Colors.RED)}")
                    tool_passed = False
            
            if version_ok:
                print(f"  {c('✓', Colors.GREEN)} --version: {c(version_msg, Colors.DIM)}")
            else:
                if "gvcore" in version_msg.lower() or "no module" in version_msg.lower():
                    print(f"  {c('○', Colors.YELLOW)} --version: {c('skipped (gvcore not installed)', Colors.DIM)}")
                    gvcore_tests_skipped = True
                else:
                    print(f"  {c('✗', Colors.RED)} --version: {c(version_msg, Colors.RED)}")
                    tool_passed = False
        
        # JSON mode test
        json_ok, json_msg = test_json_mode_support(tool_path)
        if json_ok:
            print(f"  {c('✓', Colors.GREEN)} json mode: {c(json_msg, Colors.DIM)}")
        else:
            print(f"  {c('✗', Colors.RED)} json mode: {c(json_msg, Colors.RED)}")
            tool_passed = False
        
        if tool_passed:
            total_passed += 1
        else:
            total_failed += 1
        
        print()
    
    print(f"{c('─' * 70, Colors.DIM)}")
    print(f"Tools: {c(str(total_passed), Colors.GREEN)} passed, {c(str(total_failed), Colors.RED)} failed")
    
    if gvcore_tests_skipped:
        print(f"{c('Note:', Colors.YELLOW)} Some CLI tests skipped because gvcore is not installed")
    
    print()
    
    return 0 if total_failed == 0 else 1


def main() -> None:
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print("Usage: python run_tests.py")
        print("\nRuns syntax, structure, and CLI tests for all gvtools.")
        sys.exit(0)
    
    exit_code = run_tests()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
