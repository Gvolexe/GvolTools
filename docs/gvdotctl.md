# gvdotctl - Dotfile Management

Distribute and manage dotfiles across hosts.

## Aliases

- `dt`
- `dot`
- `gvdt`

## Usage

```bash
dt <command> [options]
```

## Commands

### list

List available dotfile sets.

```bash
dt list
dt list --json
```

### apply

Apply a dotfile set.

```bash
dt apply ssh --targets server1
dt apply zsh --env prod
dt apply git --role dev
```

**Available sets:**

- `ssh` - SSH client config
- `zsh` - Zsh shell config
- `git` - Git global config
- `vim` - Vim editor config
- `tmux` - Tmux config

### status

Check dotfile status on host.

```bash
dt status server1
```

### rollback

Rollback to backup.

```bash
dt rollback server1 --file ~/.zshrc
```

## Dotfile Sets

### ssh

```
~/.ssh/config
- ServerAliveInterval
- ServerAliveCountMax
- AddKeysToAgent
```

### zsh

```
~/.zshrc
- History settings
- Aliases
- Prompt configuration
```

### git

```
~/.gitconfig
- Core settings
- Useful aliases
- Default branch
```

### vim

```
~/.vimrc
- Syntax highlighting
- Line numbers
- Tab settings
- Search settings
```

### tmux

```
~/.tmux.conf
- Prefix key (Ctrl-a)
- Pane splitting
- Mouse support
- History limit
```

## Examples

```bash
# See available sets
dt list

# Apply Zsh config to all dev servers
dt apply zsh --role dev

# Apply multiple sets
dt apply ssh --targets server1
dt apply vim --targets server1
dt apply git --targets server1

# Check what's deployed
dt status server1

# Rollback if needed
dt rollback server1 --file ~/.zshrc
```

## Backup

When applying dotfiles, existing files are backed up with timestamp:

```
~/.zshrc.bak.20240115143022
```

## Custom Templates

Templates are embedded in the tool. To customize, fork the repository and modify `DOTFILE_TEMPLATES` in `gvdotctl.py`.
