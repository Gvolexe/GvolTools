# gvoltools

[![CI](https://github.com/Gvolexe/GvolTools/actions/workflows/ci.yml/badge.svg)](https://github.com/Gvolexe/GvolTools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A collection of small, focused utilities with a consistent structure and JSON-driven installer.

**Author:** Gvol ([gvol@nexusystems.org](mailto:gvol@nexusystems.org))

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

| Tool                                     | Description                               |
| ---------------------------------------- | ----------------------------------------- |
| [gvolkeymanager](docs/gvolkeymanager.md) | SSH key upload & registry (keyup/keyconf) |

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

- [Overview & Architecture](docs/OVERVIEW.md)
- [gvolkeymanager](docs/gvolkeymanager.md)

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
