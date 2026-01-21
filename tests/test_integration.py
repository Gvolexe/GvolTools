#!/usr/bin/env python3
"""
GVTools Integration Test Suite

Tests tool integration and shared library functionality.

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import json
import os
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


def _test_setup_json_validity(root: Path) -> tuple[int, int]:
    """Test that all setup.json files are valid."""
    passed = 0
    failed = 0
    
    print(f"\n{c('Testing setup.json files...', Colors.BOLD)}\n")
    
    for setup_file in sorted(root.glob("*/setup.json")):
        tool_name = setup_file.parent.name
        
        try:
            data = json.loads(setup_file.read_text())
            
            required_fields = ["tool", "version", "description", "install"]
            missing = [f for f in required_fields if f not in data]
            
            if missing:
                print(f"  {c('✗', Colors.RED)} {tool_name}: missing fields: {missing}")
                failed += 1
                continue
            
            targets = data.get("install", {}).get("targets", [])
            if not targets:
                print(f"  {c('✗', Colors.RED)} {tool_name}: no install targets")
                failed += 1
                continue
            
            deps = data.get("deps", {})
            if deps:
                for platform in ["arch", "debian"]:
                    if platform in deps and not isinstance(deps[platform], list):
                        print(f"  {c('✗', Colors.RED)} {tool_name}: deps.{platform} is not a list")
                        failed += 1
                        continue
            
            print(f"  {c('✓', Colors.GREEN)} {tool_name}: valid")
            passed += 1
            
        except json.JSONDecodeError as e:
            print(f"  {c('✗', Colors.RED)} {tool_name}: invalid JSON: {e}")
            failed += 1
        except Exception as e:
            print(f"  {c('✗', Colors.RED)} {tool_name}: {e}")
            failed += 1
    
    return passed, failed


def test_setup_json_validity(root: Path) -> None:
    """Test that all setup.json files are valid."""
    passed, failed = _test_setup_json_validity(root)
    assert failed == 0, f"{failed} setup.json files invalid"
    assert passed > 0, "No setup.json files found"


def _test_gvcore_structure(root: Path) -> tuple[int, int]:
    """Test gvcore shared library structure."""
    passed = 0
    failed = 0
    
    print(f"\n{c('Testing gvcore...', Colors.BOLD)}\n")
    
    gvcore_path = root / "gvcore" / "files" / "gvcore.py"
    
    if not gvcore_path.exists():
        print(f"  {c('✗', Colors.RED)} gvcore.py not found")
        return 0, 1
    
    source = gvcore_path.read_text()
    
    required_components = [
        "class Colors",
        "class Output",
        "class Host",
        "class Inventory",
        "class TargetSelector",
        "class Target",
        "class SSHProfile",
        "class SSHProfileManager",
        "def ssh_connect",
        "def ssh_exec",
        "def add_common_args",
        "def add_target_args",
        "GVTOOLS_CONFIG",
        "TOOL_REGISTRY",
    ]
    
    for component in required_components:
        if component in source:
            print(f"  {c('✓', Colors.GREEN)} {component}")
            passed += 1
        else:
            print(f"  {c('✗', Colors.RED)} {component} not found")
            failed += 1
    
    return passed, failed


def test_gvcore_structure(root: Path) -> None:
    """Test gvcore shared library structure."""
    passed, failed = _test_gvcore_structure(root)
    assert failed == 0, f"{failed} gvcore components missing"


def _test_tool_consistency(root: Path) -> tuple[int, int]:
    """Test that all tools have consistent structure."""
    passed = 0
    failed = 0
    
    print(f"\n{c('Testing tool consistency...', Colors.BOLD)}\n")
    
    for setup_file in sorted(root.glob("*/setup.json")):
        tool_dir = setup_file.parent
        tool_name = tool_dir.name
        
        if tool_name == "gvcore":
            continue
        
        try:
            data = json.loads(setup_file.read_text())
            
            files_dir = tool_dir / "files"
            main_file = files_dir / f"{tool_name}.py"
            
            if not main_file.exists():
                print(f"  {c('✗', Colors.RED)} {tool_name}: {main_file.name} not found")
                failed += 1
                continue
            
            source = main_file.read_text()
            
            checks = []
            
            if "__version__" in source:
                checks.append("version")
            else:
                print(f"  {c('✗', Colors.RED)} {tool_name}: no __version__")
                failed += 1
                continue
            
            if "def main(" in source:
                checks.append("main()")
            else:
                print(f"  {c('✗', Colors.RED)} {tool_name}: no main()")
                failed += 1
                continue
            
            if "argparse" in source:
                checks.append("argparse")
            
            install_targets = data.get("install", {}).get("targets", [])
            symlinks = [t for t in install_targets if t.get("type") == "symlink"]
            if symlinks:
                alias_names = [Path(t["link"]).name.replace("~/.local/bin/", "") for t in symlinks]
                checks.append(f"aliases: {', '.join(alias_names)}")
            
            print(f"  {c('✓', Colors.GREEN)} {tool_name}: {' | '.join(checks)}")
            passed += 1
            
        except Exception as e:
            print(f"  {c('✗', Colors.RED)} {tool_name}: {e}")
            failed += 1
    
    return passed, failed


def test_tool_consistency(root: Path) -> None:
    """Test that all tools have consistent structure."""
    passed, failed = _test_tool_consistency(root)
    assert failed == 0, f"{failed} tools have inconsistent structure"


def _test_installer(root: Path) -> tuple[int, int]:
    """Test installer script."""
    passed = 0
    failed = 0
    
    print(f"\n{c('Testing installer...', Colors.BOLD)}\n")
    
    installer = root / "installgvtools.sh"
    
    if not installer.exists():
        print(f"  {c('✗', Colors.RED)} installgvtools.sh not found")
        return 0, 1
    
    source = installer.read_text()
    
    checks = [
        ("shebang", "#!/usr/bin/env bash"),
        ("set flags", "set -euo pipefail"),
        ("install cmd", "install)"),
        ("install-all cmd", "install-all)"),
        ("uninstall cmd", "uninstall)"),
        ("status cmd", "status)"),
        ("requires support", "requires"),
    ]
    
    for name, pattern in checks:
        if pattern in source:
            print(f"  {c('✓', Colors.GREEN)} {name}")
            passed += 1
        else:
            print(f"  {c('✗', Colors.RED)} {name} not found")
            failed += 1
    
    return passed, failed


def test_installer(root: Path) -> None:
    """Test installer script."""
    passed, failed = _test_installer(root)
    assert failed == 0, f"{failed} installer checks failed"


def main() -> None:
    root = Path(__file__).parent.parent
    
    print(f"\n{c('═' * 60, Colors.CYAN)}")
    print(f"{c(' GVTools Integration Tests', Colors.BOLD)}")
    print(f"{c('═' * 60, Colors.CYAN)}")
    
    total_passed = 0
    total_failed = 0
    
    p, f = _test_setup_json_validity(root)
    total_passed += p
    total_failed += f
    
    p, f = _test_gvcore_structure(root)
    total_passed += p
    total_failed += f
    
    p, f = _test_tool_consistency(root)
    total_passed += p
    total_failed += f
    
    p, f = _test_installer(root)
    total_passed += p
    total_failed += f
    
    print(f"\n{c('─' * 60, Colors.DIM)}")
    print(f"Total: {c(str(total_passed), Colors.GREEN)} passed, {c(str(total_failed), Colors.RED)} failed")
    print()
    
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
