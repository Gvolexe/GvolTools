# gvoltools

[![CI](https://github.com/Gvolexe/GvolTools/actions/workflows/ci.yml/badge.svg)](https://github.com/Gvolexe/GvolTools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.0-green.svg)](https://github.com/Gvolexe/GvolTools/releases)

A collection of small, focused utilities with a consistent structure and JSON-driven installer.

**Author:** Gvol ([gvol@nexusystems.org](mailto:gvol@nexusystems.org))

## Features

- 🔐 **Secure server setup** — Disable root login, password auth, configure sudo via SSH key
- 🔑 **SSH key management** — Registry system for managing multiple keys
- ⚙️ **Preferences** — Save defaults so you don't have to repeat arguments
- 🎨 **Beautiful CLI** — Colorful, informative output with clear status messages
- 📦 **JSON-driven installer** — Easy to extend with new tools

---

## Quick Start

```bash
git clone https://github.com/Gvolexe/GvolTools.git
cd GvolTools
./installgvtools.sh list
./installgvtools.sh install gvolkeymanager --deps
```

### PATH Setup

Tools are installed to `~/.local/bin`. Add this directory to your PATH:

**Bash** (`~/.bashrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

**Zsh** (`~/.zshrc`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

**Fish** (`~/.config/fish/config.fish`):

```fish
fish_add_path ~/.local/bin
```

After editing, restart your shell or run `source ~/.bashrc` (or equivalent).

## Available Tools

| Tool                                     | Version | Description                                           |
| ---------------------------------------- | ------- | ----------------------------------------------------- |
| [gvolkeymanager](docs/gvolkeymanager.md) | 0.3.0   | SSH key upload, registry & secure server setup        |

### gvolkeymanager Highlights

- **`keyup`** — Upload SSH keys to servers with optional security hardening
- **`keyconf`** — Manage local registry of SSH keys and preferences
- **Secure setup** — Creates users, disables root login, enables sudo via SSH key
- **Preferences** — Save default username, key, and security settings

## Installer Usage

```bash
./installgvtools.sh <command> [options]

Commands:
  list                    List available tools
  install <tool> [--deps] Install a tool (--deps installs system packages)
  uninstall <tool>        Remove an installed tool
  status <tool>           Check if a tool is installed
  --help, -h              Show help message
  --version               Show version
```

## Adding Your Own Tools

1. Create the structure:

   ```bash
   mkdir -p mytool/files
   ```

2. Add `mytool/setup.json`:

   ```json
   {
     "tool": "mytool",
     "version": "0.1.0",
     "description": "What it does",
     "deps": {
       "arch": [],
       "debian": []
     },
     "install": {
       "targets": [
         {
           "type": "copy",
           "src": "files/mytool",
           "dst": "~/.local/bin/mytool",
           "chmod": "755"
         }
       ]
     }
   }
   ```

3. Add your files to `mytool/files/`

4. Install and test:
   ```bash
   ./installgvtools.sh install mytool
   ```

## Documentation

- [gvolkeymanager](docs/gvolkeymanager.md) — Full usage guide with security features

## Development

### Running Tests

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run with coverage
python3 -m pytest tests/ -v --cov=gvolkeymanager
```

### Code Style

This project follows standard Python conventions. Use meaningful variable names, add docstrings to functions, and keep functions focused.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

---

Made with care by [Gvol](mailto:gvol@nexusystems.org)
