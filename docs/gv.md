# gv - GVTools Help Command

Central help and navigation for all GVTools commands.

## Aliases

- `gv`
- `gvtools`
- `gvhelp`

## Usage

```bash
gv                    # Show all available tools
gv list               # List tools by category
gv help <tool>        # Show help for specific tool
gv search <keyword>   # Search for tools
gv version            # Show version info
```

## Commands

### list

List all available tools organized by category.

```bash
gv list
gv list --json
```

### help

Show detailed help for a specific tool.

```bash
gv help fleet
gv help gvfleet
gv help hb
```

### search

Search for tools by keyword.

```bash
gv search ssh
gv search backup
gv search security
```

### version

Show GVTools version information.

```bash
gv version
```

## Examples

```bash
# See all available tools
gv

# Get help for the fleet tool
gv help fleet

# Search for networking tools
gv search network

# List all tools in JSON format
gv list --json
```
