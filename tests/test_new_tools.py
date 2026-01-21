#!/usr/bin/env python3
"""
Tests for new GVTools (policy, sync, configrender, nginx, etc.)

Author: Gvol (gvol@nexusystems.org)
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tools_dir() -> Path:
    """Return the tools directory."""
    return Path(__file__).parent.parent / "tools"


@pytest.fixture
def temp_config(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / "config" / "gvtools"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def temp_data(tmp_path):
    """Create a temporary data directory."""
    data_dir = tmp_path / "data" / "gvtools"
    data_dir.mkdir(parents=True)
    return data_dir


# ─────────────────────────────────────────────────────────────────────────────
# New Tools Discovery
# ─────────────────────────────────────────────────────────────────────────────

NEW_TOOLS = [
    "gvpolicy",
    "gvsync",
    "gvconfigrender",
    "gvnginxctl",
    "gvrebootctl",
    "gvdnsprovider",
    "gvhealth",
    "gvmetrics",
    "gvtcptest",
    "gvjournal",
    "gvdeploy",
    "gvsystemdctl",
]


def find_new_tool_files(tools_dir: Path) -> list[Path]:
    """Find Python files for new tools."""
    tools = []
    for tool_name in NEW_TOOLS:
        tool_dir = tools_dir / tool_name
        files_dir = tool_dir / "files"
        if files_dir.exists():
            for py_file in files_dir.glob("*.py"):
                tools.append(py_file)
    return sorted(tools)


# ─────────────────────────────────────────────────────────────────────────────
# Syntax Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tool_name", NEW_TOOLS)
def test_new_tool_syntax(tools_dir: Path, tool_name: str) -> None:
    """Test Python syntax validity for new tools."""
    tool_file = tools_dir / tool_name / "files" / f"{tool_name}.py"
    
    if not tool_file.exists():
        pytest.skip(f"Tool {tool_name} not found")
    
    source = tool_file.read_text(encoding="utf-8")
    try:
        ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"Syntax error in {tool_name}: line {e.lineno}: {e.msg}")


@pytest.mark.parametrize("tool_name", NEW_TOOLS)
def test_new_tool_docstring(tools_dir: Path, tool_name: str) -> None:
    """Test that new tools have docstrings."""
    tool_file = tools_dir / tool_name / "files" / f"{tool_name}.py"
    
    if not tool_file.exists():
        pytest.skip(f"Tool {tool_name} not found")
    
    source = tool_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree)
    
    assert docstring is not None, f"{tool_name} has no module docstring"
    assert len(docstring) > 10, f"{tool_name} docstring is too short"


@pytest.mark.parametrize("tool_name", NEW_TOOLS)
def test_new_tool_setup_json(tools_dir: Path, tool_name: str) -> None:
    """Test that new tools have valid setup.json."""
    setup_file = tools_dir / tool_name / "setup.json"
    
    if not setup_file.exists():
        pytest.skip(f"Tool {tool_name} setup.json not found")
    
    content = setup_file.read_text(encoding="utf-8")
    setup = json.loads(content)
    
    assert "tool" in setup, f"{tool_name} setup.json missing 'tool'"
    assert "version" in setup, f"{tool_name} setup.json missing 'version'"
    assert "install" in setup, f"{tool_name} setup.json missing 'install'"
    assert "targets" in setup["install"], f"{tool_name} setup.json missing 'install.targets'"


# ─────────────────────────────────────────────────────────────────────────────
# Structure Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tool_name", NEW_TOOLS)
def test_new_tool_has_main(tools_dir: Path, tool_name: str) -> None:
    """Test that new tools have main() function."""
    tool_file = tools_dir / tool_name / "files" / f"{tool_name}.py"
    
    if not tool_file.exists():
        pytest.skip(f"Tool {tool_name} not found")
    
    source = tool_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    assert "main" in functions, f"{tool_name} has no main() function"


@pytest.mark.parametrize("tool_name", NEW_TOOLS)
def test_new_tool_imports_gvcore(tools_dir: Path, tool_name: str) -> None:
    """Test that new tools import gvcore."""
    tool_file = tools_dir / tool_name / "files" / f"{tool_name}.py"
    
    if not tool_file.exists():
        pytest.skip(f"Tool {tool_name} not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "from gvcore import" in source, f"{tool_name} doesn't import gvcore"


@pytest.mark.parametrize("tool_name", NEW_TOOLS)
def test_new_tool_uses_output(tools_dir: Path, tool_name: str) -> None:
    """Test that new tools use Output class for formatting."""
    tool_file = tools_dir / tool_name / "files" / f"{tool_name}.py"
    
    if not tool_file.exists():
        pytest.skip(f"Tool {tool_name} not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "Output." in source, f"{tool_name} doesn't use Output class"


# ─────────────────────────────────────────────────────────────────────────────
# Policy Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_policy_builtin_checks(tools_dir: Path) -> None:
    """Test that gvpolicy has builtin checks defined."""
    tool_file = tools_dir / "gvpolicy" / "files" / "gvpolicy.py"
    
    if not tool_file.exists():
        pytest.skip("gvpolicy not found")
    
    source = tool_file.read_text(encoding="utf-8")
    
    # Check for some expected builtin checks
    assert "ssh.password_disabled" in source, "Missing ssh.password_disabled check"
    assert "ssh.root_login_disabled" in source, "Missing ssh.root_login_disabled check"
    assert "disk.usage_below_90" in source, "Missing disk.usage_below_90 check"


def test_policy_waiver_support(tools_dir: Path) -> None:
    """Test that gvpolicy supports waivers."""
    tool_file = tools_dir / "gvpolicy" / "files" / "gvpolicy.py"
    
    if not tool_file.exists():
        pytest.skip("gvpolicy not found")
    
    source = tool_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    
    # Check for WaiverManager class
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert "PolicyWaiver" in classes, "Missing PolicyWaiver class"
    assert "WaiverManager" in classes, "Missing WaiverManager class"


# ─────────────────────────────────────────────────────────────────────────────
# Sync Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_sync_commands(tools_dir: Path) -> None:
    """Test that gvsync has expected commands."""
    tool_file = tools_dir / "gvsync" / "files" / "gvsync.py"
    
    if not tool_file.exists():
        pytest.skip("gvsync not found")
    
    source = tool_file.read_text(encoding="utf-8")
    
    # Check for command functions
    assert "def cmd_push" in source, "Missing cmd_push"
    assert "def cmd_pull" in source, "Missing cmd_pull"
    assert "def cmd_mirror" in source, "Missing cmd_mirror"
    assert "def cmd_diff" in source, "Missing cmd_diff"


def test_sync_rsync_builder(tools_dir: Path) -> None:
    """Test that gvsync has rsync command builder."""
    tool_file = tools_dir / "gvsync" / "files" / "gvsync.py"
    
    if not tool_file.exists():
        pytest.skip("gvsync not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "def build_rsync_command" in source, "Missing build_rsync_command function"


# ─────────────────────────────────────────────────────────────────────────────
# Config Render Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_configrender_template_engine(tools_dir: Path) -> None:
    """Test that gvconfigrender has template engine."""
    tool_file = tools_dir / "gvconfigrender" / "files" / "gvconfigrender.py"
    
    if not tool_file.exists():
        pytest.skip("gvconfigrender not found")
    
    source = tool_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert "Jinja2LikeTemplate" in classes or "Template" in classes or "TemplateVars" in classes


def test_configrender_commands(tools_dir: Path) -> None:
    """Test that gvconfigrender has expected commands."""
    tool_file = tools_dir / "gvconfigrender" / "files" / "gvconfigrender.py"
    
    if not tool_file.exists():
        pytest.skip("gvconfigrender not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "def cmd_render" in source, "Missing cmd_render"
    assert "def cmd_deploy" in source, "Missing cmd_deploy"


# ─────────────────────────────────────────────────────────────────────────────
# Nginx Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_nginx_commands(tools_dir: Path) -> None:
    """Test that gvnginxctl has expected commands."""
    tool_file = tools_dir / "gvnginxctl" / "files" / "gvnginxctl.py"
    
    if not tool_file.exists():
        pytest.skip("gvnginxctl not found")
    
    source = tool_file.read_text(encoding="utf-8")
    
    assert "def cmd_status" in source, "Missing cmd_status"
    assert "def cmd_test" in source, "Missing cmd_test"
    assert "def cmd_reload" in source, "Missing cmd_reload"
    assert "def cmd_restart" in source, "Missing cmd_restart"


def test_nginx_site_management(tools_dir: Path) -> None:
    """Test that gvnginxctl supports site enable/disable."""
    tool_file = tools_dir / "gvnginxctl" / "files" / "gvnginxctl.py"
    
    if not tool_file.exists():
        pytest.skip("gvnginxctl not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "def cmd_site_enable" in source, "Missing cmd_site_enable"
    assert "def cmd_site_disable" in source, "Missing cmd_site_disable"


# ─────────────────────────────────────────────────────────────────────────────
# Fleet SSH Key Linking Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_fleet_setkey_command(tools_dir: Path) -> None:
    """Test that gvfleet has setkey command."""
    tool_file = tools_dir / "gvfleet" / "files" / "gvfleet.py"
    
    if not tool_file.exists():
        pytest.skip("gvfleet not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "def cmd_setkey" in source, "Missing cmd_setkey"
    assert "def cmd_getkey" in source, "Missing cmd_getkey"


def test_fleet_setkey_parser(tools_dir: Path) -> None:
    """Test that gvfleet setkey has parser setup."""
    tool_file = tools_dir / "gvfleet" / "files" / "gvfleet.py"
    
    if not tool_file.exists():
        pytest.skip("gvfleet not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "def setup_setkey_parser" in source, "Missing setup_setkey_parser"
    assert "def setup_getkey_parser" in source, "Missing setup_getkey_parser"


# ─────────────────────────────────────────────────────────────────────────────
# Version Consistency Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_setup_json_version_consistency(tools_dir: Path) -> None:
    """Test that all new tools have consistent version in setup.json."""
    versions = {}
    
    for tool_name in NEW_TOOLS:
        setup_file = tools_dir / tool_name / "setup.json"
        if setup_file.exists():
            setup = json.loads(setup_file.read_text(encoding="utf-8"))
            versions[tool_name] = setup.get("version", "unknown")
    
    if not versions:
        pytest.skip("No tool setup.json files found")
    
    unique_versions = set(versions.values())
    assert len(unique_versions) == 1, f"Version mismatch: {versions}"


# ─────────────────────────────────────────────────────────────────────────────
# Alias Tests
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_ALIASES = {
    "gvpolicy": ["pol", "pl"],
    "gvsync": ["sync", "sx"],
    "gvconfigrender": ["render", "rr"],
    "gvnginxctl": ["ngx", "nx"],
    "gvrebootctl": ["reboot", "rb"],
    "gvdnsprovider": ["dnsprov", "dp"],
    "gvhealth": ["health", "hl"],
    "gvmetrics": ["metrics", "mx"],
    "gvtcptest": ["tcp", "tc"],
    "gvjournal": ["jrnl", "j"],
    "gvdeploy": ["dep", "run"],
    "gvsystemdctl": ["sd", "svc"],
}


@pytest.mark.parametrize("tool_name,aliases", list(EXPECTED_ALIASES.items()))
def test_tool_aliases(tools_dir: Path, tool_name: str, aliases: list[str]) -> None:
    """Test that tools have expected aliases in setup.json."""
    setup_file = tools_dir / tool_name / "setup.json"
    
    if not setup_file.exists():
        pytest.skip(f"Tool {tool_name} setup.json not found")
    
    setup = json.loads(setup_file.read_text(encoding="utf-8"))
    targets = setup.get("install", {}).get("targets", [])
    
    symlinks = []
    for target in targets:
        if target.get("type") == "symlink":
            link = Path(target.get("link", "")).name
            symlinks.append(link)
    
    for alias in aliases:
        assert alias in symlinks, f"Missing alias {alias} for {tool_name}"


# ─────────────────────────────────────────────────────────────────────────────
# JSON Mode Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tool_name", NEW_TOOLS)
def test_tool_supports_json_mode(tools_dir: Path, tool_name: str) -> None:
    """Test that tools support --json output mode."""
    tool_file = tools_dir / tool_name / "files" / f"{tool_name}.py"
    
    if not tool_file.exists():
        pytest.skip(f"Tool {tool_name} not found")
    
    source = tool_file.read_text(encoding="utf-8")
    assert "Output.json_mode" in source, f"{tool_name} doesn't check Output.json_mode"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Run tests directly."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=Path(__file__).parent.parent
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
