"""
Tests for gvolkeymanager

Run with: python3 -m pytest tests/ -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add the module path
sys.path.insert(0, str(Path(__file__).parent.parent / "gvolkeymanager" / "files"))

# Import after path is set
import gvolkeymanager as km


class TestColors:
    """Test color utilities."""
    
    def test_colors_disabled_with_no_color_env(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert not km.Colors.enabled()
    
    def test_color_function_returns_plain_when_disabled(self):
        with patch.object(km.Colors, "enabled", return_value=False):
            result = km.c("test", km.Colors.RED)
            assert result == "test"
    
    def test_color_function_applies_codes_when_enabled(self):
        with patch.object(km.Colors, "enabled", return_value=True):
            result = km.c("test", km.Colors.RED)
            assert km.Colors.RED in result
            assert km.Colors.RESET in result
            assert "test" in result


class TestValidation:
    """Test validation functions."""
    
    def test_valid_key_names(self):
        valid_names = ["personal", "work", "my-key", "key_1", "A1", "myKey123"]
        for name in valid_names:
            km.validate_key_name(name)  # Should not raise
    
    def test_invalid_key_names(self):
        invalid_names = [
            "1key",        # starts with number
            "-key",        # starts with dash
            "_key",        # starts with underscore
            "key name",    # contains space
            "key@name",    # contains special char
            "",            # empty
            "a" * 65,      # too long
        ]
        for name in invalid_names:
            with pytest.raises(SystemExit):
                km.validate_key_name(name)
    
    def test_valid_ssh_key_content(self):
        valid_keys = [
            "ssh-ed25519 AAAAC3Nz... user@host",
            "ssh-rsa AAAAB3NzaC1yc2E... user@host",
            "ecdsa-sha2-nistp256 AAAAE2VjZHNh... user@host",
            "sk-ssh-ed25519@openssh.com AAAAG... user@host",
            "sk-ecdsa-sha2-nistp256@openssh.com AAAA... user@host",
        ]
        for key in valid_keys:
            km.validate_pubkey_content(key, Path("/test"))  # Should not raise
    
    def test_invalid_ssh_key_content(self):
        invalid_keys = [
            "not-a-key",
            "-----BEGIN PRIVATE KEY-----",
            "random text",
        ]
        for key in invalid_keys:
            with pytest.raises(SystemExit):
                km.validate_pubkey_content(key, Path("/test"))


class TestTarget:
    """Test SSH target parsing."""
    
    def test_parse_simple_target(self):
        target = km.Target.parse("user@host")
        assert target.user == "user"
        assert target.host == "host"
        assert target.port == 22
    
    def test_parse_target_with_port(self):
        target = km.Target.parse("admin@server:2222")
        assert target.user == "admin"
        assert target.host == "server"
        assert target.port == 2222
    
    def test_parse_target_with_fqdn(self):
        target = km.Target.parse("deploy@prod.example.com:22")
        assert target.user == "deploy"
        assert target.host == "prod.example.com"
        assert target.port == 22
    
    def test_parse_target_without_at_fails(self):
        with pytest.raises(SystemExit):
            km.Target.parse("hostonly")
    
    def test_parse_target_empty_user_fails(self):
        with pytest.raises(SystemExit):
            km.Target.parse("@host")
    
    def test_parse_target_empty_host_fails(self):
        with pytest.raises(SystemExit):
            km.Target.parse("user@")
    
    def test_target_string_representation(self):
        target = km.Target(user="u", host="h", port=22)
        assert str(target) == "u@h"
        
        target = km.Target(user="u", host="h", port=2222)
        assert str(target) == "u@h:2222"


class TestConfig:
    """Test configuration loading and saving."""
    
    def test_load_nonexistent_config_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(km, "LEGACY_CONFIG", Path(tmpdir) / "legacy" / "keys.json"):
                with patch.object(km, "DEFAULT_CONFIG", Path(tmpdir) / "new" / "keys.json"):
                    cfg = km.Config.load()
                    assert cfg.keys == {}
    
    def test_load_existing_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "keys.json"
            config_path.write_text('{"keys": {"test": "/path/to/key.pub"}}')
            
            with patch.object(km, "LEGACY_CONFIG", Path(tmpdir) / "nonexistent"):
                with patch.object(km, "DEFAULT_CONFIG", config_path):
                    cfg = km.Config.load()
                    assert cfg.keys == {"test": "/path/to/key.pub"}
    
    def test_save_config_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "subdir" / "keys.json"
            
            cfg = km.Config(keys={"mykey": "/path"}, path=config_path)
            cfg.save()
            
            assert config_path.exists()
            data = json.loads(config_path.read_text())
            assert data["keys"]["mykey"] == "/path"
    
    def test_prefers_legacy_config_if_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy = Path(tmpdir) / "legacy" / "keys.json"
            new = Path(tmpdir) / "new" / "keys.json"
            
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"keys": {"legacy": "1"}}')
            
            new.parent.mkdir(parents=True)
            new.write_text('{"keys": {"new": "2"}}')
            
            with patch.object(km, "LEGACY_CONFIG", legacy):
                with patch.object(km, "DEFAULT_CONFIG", new):
                    cfg = km.Config.load()
                    assert "legacy" in cfg.keys


class TestKeyconfCommands:
    """Test keyconf command functions."""
    
    def test_keyconf_add_creates_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "keys.json"
            pubkey_path = Path(tmpdir) / "test.pub"
            pubkey_path.write_text("ssh-ed25519 AAAA... test@test")
            
            with patch.object(km, "LEGACY_CONFIG", Path(tmpdir) / "nonexistent"):
                with patch.object(km, "DEFAULT_CONFIG", config_path):
                    km.cmd_keyconf_add("testkey", str(pubkey_path))
                    
                    cfg = km.Config.load()
                    assert "testkey" in cfg.keys
    
    def test_keyconf_add_rejects_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(km, "LEGACY_CONFIG", Path(tmpdir) / "nonexistent"):
                with patch.object(km, "DEFAULT_CONFIG", Path(tmpdir) / "keys.json"):
                    with pytest.raises(SystemExit):
                        km.cmd_keyconf_add("testkey", "/nonexistent/path.pub")
    
    def test_keyconf_del_removes_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "keys.json"
            config_path.write_text('{"keys": {"mykey": "/path"}}')
            
            with patch.object(km, "LEGACY_CONFIG", Path(tmpdir) / "nonexistent"):
                with patch.object(km, "DEFAULT_CONFIG", config_path):
                    km.cmd_keyconf_del("mykey")
                    
                    cfg = km.Config.load()
                    assert "mykey" not in cfg.keys
    
    def test_keyconf_del_nonexistent_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "keys.json"
            config_path.write_text('{"keys": {}}')
            
            with patch.object(km, "LEGACY_CONFIG", Path(tmpdir) / "nonexistent"):
                with patch.object(km, "DEFAULT_CONFIG", config_path):
                    with pytest.raises(SystemExit):
                        km.cmd_keyconf_del("nonexistent")


class TestRemoteScripts:
    """Test remote script generation."""
    
    def test_upload_script_contains_key(self):
        script = km.make_upload_script("dGVzdGtleQ==")  # base64 of "testkey"
        assert "dGVzdGtleQ==" in script
        assert "authorized_keys" in script
        assert "chmod 600" in script
    
    def test_create_user_script_contains_username(self):
        script = km.make_create_user_script("dGVzdGtleQ==", "myuser")
        assert "myuser" in script
        assert "useradd" in script
        assert "authorized_keys" in script


class TestCLI:
    """Test CLI argument parsing."""
    
    def test_parser_accepts_keyconf_add(self):
        parser = km.build_parser("gvolkeymanager")
        args = parser.parse_args(["keyconf", "add", "mykey", "/path/to/key.pub"])
        assert args.command == "keyconf"
        assert args.keyconf_action == "add"
        assert args.name == "mykey"
        assert args.path == "/path/to/key.pub"
    
    def test_parser_accepts_keyconf_list(self):
        parser = km.build_parser("gvolkeymanager")
        args = parser.parse_args(["keyconf", "list"])
        assert args.command == "keyconf"
        assert args.keyconf_action == "list"
    
    def test_parser_accepts_keyup(self):
        parser = km.build_parser("gvolkeymanager")
        args = parser.parse_args(["keyup", "user@host", "mykey"])
        assert args.command == "keyup"
        assert args.target == "user@host"
        assert args.keyname == "mykey"
    
    def test_parser_accepts_keyup_options(self):
        parser = km.build_parser("gvolkeymanager")
        args = parser.parse_args([
            "keyup", "--strict-hostkey", "--dry-run",
            "--create-user", "admin",
            "user@host", "mykey"
        ])
        assert args.strict_hostkey is True
        assert args.dry_run is True
        assert args.create_user == "admin"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
