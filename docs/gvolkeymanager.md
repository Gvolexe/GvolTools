# gvolkeymanager

SSH key upload and registry utility with secure server setup.

## Overview

`gvolkeymanager` provides three main functionalities:

- **keyup**: Upload SSH public keys to remote servers with optional security hardening
- **keyconf**: Manage a local registry of SSH keys
- **prefs**: Configure defaults and security settings

## Installation

```bash
cd GvolTools
./installgvtools.sh install gvolkeymanager --deps
```

This installs:

- `gvolkeymanager` → `~/.local/bin/gvolkeymanager`
- `keyup` → symlink to gvolkeymanager
- `keyconf` → symlink to gvolkeymanager

## Quick Start

```bash
# 1. Register your key
keyconf add personal ~/.ssh/id_ed25519.pub

# 2. Set your default username
keyconf prefs set default_user myname

# 3. Upload to a server with secure setup
keyup root@newserver.example.com personal
```

## Commands

### keyconf — Key Registry

```bash
# Add a key to the registry
keyconf add personal ~/.ssh/id_ed25519.pub

# List all registered keys
keyconf list

# Show details for a specific key
keyconf show personal

# Remove a key from the registry
keyconf del personal
```

### keyconf prefs — Preferences

```bash
# Show current preferences
keyconf prefs

# Set default username for new user creation
keyconf prefs set default_user gvol

# Set default key (allows omitting keyname in keyup)
keyconf prefs set default_key personal

# Enable strict host key checking by default
keyconf prefs set strict_hostkey yes

# Configure security defaults
keyconf prefs set disable_root_login yes
keyconf prefs set disable_password_auth yes
keyconf prefs set sudo_with_key yes
```

#### Available Preferences

| Key                     | Type    | Default | Description                                     |
| ----------------------- | ------- | ------- | ----------------------------------------------- |
| `default_user`          | string  | `""`    | Default username when creating users            |
| `default_key`           | string  | `""`    | Default key name (allows `keyup host` shortcut) |
| `strict_hostkey`        | boolean | `false` | Reject unknown SSH host keys                    |
| `sudo_with_key`         | boolean | `true`  | Set up sudo authentication via SSH key          |
| `disable_root_login`    | boolean | `true`  | Disable SSH login as root                       |
| `disable_password_auth` | boolean | `true`  | Disable password login for created users        |

### keyup — Upload Keys to Remote Servers

```bash
# Basic usage
keyup user@host keyname

# Using default key (if configured)
keyup user@host

# With custom port
keyup user@host:2222 keyname

# Strict host key checking
keyup --strict-hostkey user@host keyname

# Create a custom user on the remote
keyup --create-user admin root@host keyname

# Dry run - show what would happen
keyup --dry-run user@host keyname

# Verbose output
keyup -v user@host keyname
```

#### Upload Options

When running `keyup`, you'll be prompted to choose:

1. **Secure setup** (recommended): Creates user, uploads key, and applies security hardening
2. **Simple setup**: Creates user and uploads key only
3. **Upload only**: Adds key to existing user's authorized_keys

## Security Features

### Secure Setup (Option 1)

When you choose "Secure setup", the following happens:

1. **User creation**: Creates the user if not exists
2. **SSH key installation**: Adds your public key to `~/.ssh/authorized_keys`
3. **Password disable**: Locks password login for the user (`passwd -l`)
4. **Root login disable**: Sets `PermitRootLogin no` in sshd_config
5. **Sudo with SSH key**: Configures `pam_ssh_agent_auth` for passwordless sudo

### Sudo with SSH Key

After secure setup, you can use sudo without a password by using SSH agent forwarding:

```bash
# Connect with agent forwarding
ssh -A user@server

# Sudo works without password
sudo apt update
```

**Requirements on client:**

- SSH agent running with your key loaded (`ssh-add ~/.ssh/id_ed25519`)
- Use `-A` flag when connecting

**What gets configured on server:**

- `libpam-ssh-agent-auth` package installed
- PAM configured for sudo
- Your public key added to `/etc/security/sudo_authorized_keys/<username>`
- `SSH_AUTH_SOCK` preserved in sudo environment

## Configuration Files

### Key Registry

Location: `~/.config/gvolkeymanager/keys.json`

```json
{
  "keys": {
    "personal": "/home/user/.ssh/id_ed25519.pub",
    "work": "/home/user/.ssh/work_key.pub"
  }
}
```

### Preferences

Location: `~/.config/gvolkeymanager/prefs.json`

```json
{
  "default_key": "personal",
  "default_user": "gvol",
  "disable_password_auth": true,
  "disable_root_login": true,
  "strict_hostkey": false,
  "sudo_with_key": true
}
```

## Key Name Rules

Key names must:

- Start with a letter
- Contain only letters, numbers, dashes, and underscores
- Be between 1-64 characters

## Supported Key Types

- `ssh-rsa`
- `ssh-ed25519`
- `ecdsa-sha2-*`
- `sk-ssh-ed25519@openssh.com`
- `sk-ecdsa-sha2-*@openssh.com`

## Examples

### Initial Server Setup

```bash
# Register your key
keyconf add personal ~/.ssh/id_ed25519.pub

# Set your preferred username
keyconf prefs set default_user myname

# Secure setup on a new VPS
keyup root@newvps.example.com personal
# Choose option 1 (Secure setup)

# Now connect as your user (root is disabled)
ssh -A myname@newvps.example.com
```

### Multiple Servers

```bash
# Set default key
keyconf prefs set default_key personal

# Now you can omit the keyname
keyup root@server1.example.com
keyup root@server2.example.com
keyup root@server3.example.com
```

## Troubleshooting

### "key 'X' not in registry"

Register the key first: `keyconf add X /path/to/key.pub`

### SSH connection failed

- Check host/port are correct
- Verify password authentication is enabled on the server
- Check network connectivity

### Sudo still asks for password

- Make sure you connected with `-A` (agent forwarding): `ssh -A user@host`
- Verify your key is loaded: `ssh-add -l`
- Check server logs: `tail /var/log/auth.log`

### "file does not look like an SSH public key"

Ensure the file is a `.pub` file and starts with a valid key type prefix.
