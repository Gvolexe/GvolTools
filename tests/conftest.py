"""
Pytest configuration for gvoltools test suite.

Provides colorful and beautiful test output with custom formatting.
"""

import pytest
import sys
import os

# Colors for terminal output
class TC:
    """Terminal colors."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"


def colored(text: str, *codes: str) -> str:
    """Apply color codes if terminal supports it."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return "".join(codes) + text + TC.RESET


def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Add custom markers
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")


def pytest_report_header(config):
    """Custom header for test report."""
    lines = [
        "",
        colored("╭─────────────────────────────────────────────────╮", TC.CYAN),
        colored("│", TC.CYAN) + colored("           gvoltools test suite               ", TC.BOLD, TC.WHITE) + colored("│", TC.CYAN),
        colored("│", TC.CYAN) + colored("     Author: Gvol (gvol@nexusystems.org)      ", TC.DIM) + colored("│", TC.CYAN),
        colored("╰─────────────────────────────────────────────────╯", TC.CYAN),
        "",
    ]
    return lines


def pytest_collection_modifyitems(config, items):
    """Modify test collection."""
    # Sort tests by class name for better grouping
    items.sort(key=lambda x: (x.cls.__name__ if x.cls else "", x.name))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Custom test result formatting."""
    outcome = yield
    report = outcome.get_result()
    
    # Add emojis to test outcomes
    if report.when == "call":
        if report.passed:
            report.outcome_symbol = colored("✔ PASS", TC.GREEN, TC.BOLD)
        elif report.failed:
            report.outcome_symbol = colored("✖ FAIL", TC.RED, TC.BOLD)
        elif report.skipped:
            report.outcome_symbol = colored("⊘ SKIP", TC.YELLOW, TC.BOLD)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Custom summary at the end of test run."""
    stats = terminalreporter.stats
    
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    skipped = len(stats.get("skipped", []))
    total = passed + failed + skipped
    
    terminalreporter.write_line("")
    terminalreporter.write_line(colored("─" * 50, TC.DIM))
    
    if failed == 0:
        terminalreporter.write_line(
            colored("  ✨ All tests passed! ", TC.GREEN, TC.BOLD) +
            colored(f"({passed}/{total})", TC.DIM)
        )
        terminalreporter.write_line(colored("  🎉 Great job!", TC.GREEN))
    else:
        terminalreporter.write_line(
            colored(f"  ✖ {failed} test(s) failed ", TC.RED, TC.BOLD) +
            colored(f"({passed}/{total} passed)", TC.DIM)
        )
    
    terminalreporter.write_line(colored("─" * 50, TC.DIM))
    terminalreporter.write_line("")


# Fixtures

@pytest.fixture
def temp_config(tmp_path):
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_pubkey(tmp_path):
    """Create a sample SSH public key file."""
    pubkey = tmp_path / "test.pub"
    pubkey.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest test@example.com\n")
    return pubkey


@pytest.fixture
def sample_config(tmp_path):
    """Create a sample config file."""
    import json
    config_dir = tmp_path / "gvolkeymanager"
    config_dir.mkdir()
    config_file = config_dir / "keys.json"
    config_file.write_text(json.dumps({
        "keys": {
            "testkey": "/path/to/key.pub"
        }
    }, indent=2))
    return config_file
