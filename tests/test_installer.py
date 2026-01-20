"""
Tests for installgvtools.sh

These tests verify the bash installer script functionality.
Run with: python3 -m pytest tests/ -v
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parent.parent / "installgvtools.sh"


def run_installer(*args, cwd=None):
    """Run the installer script with arguments."""
    result = subprocess.run(
        [str(SCRIPT_PATH)] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd or SCRIPT_PATH.parent,
        env={**os.environ, "NO_COLOR": "1"}
    )
    return result


class TestInstallerHelp:
    """Test help and version commands."""
    
    def test_help_command(self):
        result = run_installer("--help")
        assert result.returncode == 0
        assert "gvoltools installer" in result.stdout
        assert "Commands:" in result.stdout
    
    def test_h_flag(self):
        result = run_installer("-h")
        assert result.returncode == 0
        assert "Usage:" in result.stdout
    
    def test_version_command(self):
        result = run_installer("--version")
        assert result.returncode == 0
        assert "installgvtools" in result.stdout
    
    def test_no_args_shows_usage(self):
        result = run_installer()
        assert "Usage:" in result.stdout


class TestInstallerList:
    """Test list command."""
    
    def test_list_shows_tools(self):
        result = run_installer("list")
        assert result.returncode == 0
        assert "gvolkeymanager" in result.stdout


class TestInstallerStatus:
    """Test status command."""
    
    def test_status_missing_tool_fails(self):
        result = run_installer("status")
        assert result.returncode != 0
        assert "Missing tool name" in result.stderr or "error" in result.stderr.lower()
    
    def test_status_nonexistent_tool_fails(self):
        result = run_installer("status", "nonexistent-tool-xyz")
        assert result.returncode != 0


class TestInstallerInstallUninstall:
    """Test install and uninstall flow."""
    
    def test_install_requires_tool_name(self):
        result = run_installer("install")
        assert result.returncode != 0
    
    def test_uninstall_requires_tool_name(self):
        result = run_installer("uninstall")
        assert result.returncode != 0
    
    def test_install_nonexistent_tool_fails(self):
        result = run_installer("install", "nonexistent-tool-xyz")
        assert result.returncode != 0


class TestInstallerUnknownCommand:
    """Test error handling for unknown commands."""
    
    def test_unknown_command_fails(self):
        result = run_installer("unknowncommand")
        assert result.returncode != 0
        assert "Unknown command" in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
