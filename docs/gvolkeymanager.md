# gvolkeymanager

SSH key upload and allowed-key registry utility.

## Overview

`gvolkeymanager` combines two functionalities:

- **keyup**: Upload SSH public keys to remote servers via password authentication
- **keyconf**: Manage a local registry of allowed key names and their paths

## Installation

```bash
cd gvoltools
./installgvtools.sh install gvolkeymanager --deps
```

This installs:

- `gvolkeymanager` → `~/.local/bin/gvolkeymanager`
- `keyup` → symlink to gvolkeymanager
- `keyconf` → symlink to gvolkeymanager

## Commands

### keyconf — Key Registry Management

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

### keyup — Upload Keys to Remote Servers

```bash
# Basic usage
keyup user@host keyname

# With custom port
keyup user@host:2222 keyname

# Strict host key checking (recommended for production)
keyup --strict-hostkey user@host keyname

# Create a custom user on the remote (instead of 'gvol')
keyup --create-user admin user@host keyname

# Dry run - show what would happen
keyup --dry-run user@host keyname

# Verbose output
keyup -v user@host keyname
```

#### Upload Options

When running `keyup`, you'll be prompted:

1. **Create user + upload key**: Creates a new user (default: `gvol`) on the remote system and uploads the key
2. **Upload to existing user**: Uploads the key to the user specified in the target

## Configuration

Keys are stored in:

- `~/.config/gvolkeymanager/keys.json` (default)
- `~/.config/keyup/keys.json` (legacy, used if exists)

### Config Format

```json
{
  "keys": {
    "personal": "/home/user/.ssh/id_ed25519.pub",
    "work": "/home/user/.ssh/work_key.pub"
  }
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
- `ssh-dss`
- `ecdsa-sha2-*`
- `sk-ssh-ed25519@openssh.com`
- `sk-ecdsa-sha2-*@openssh.com`

## Security Notes

- **Host key verification**: By default, unknown host keys are auto-accepted. Use `--strict-hostkey` in production environments.
- **Password handling**: Passwords are used only for the SSH connection and sudo, never stored.
- **Key validation**: Only valid SSH public keys are accepted.

## Examples

```bash
# Set up a new server with your key
keyconf add mykey ~/.ssh/id_ed25519.pub
keyup root@newserver.example.com mykey

# Upload to an existing user
keyup deploy@prod.example.com:22 mykey

# Strict mode for production
keyup --strict-hostkey admin@secure.example.com mykey
```

## Troubleshooting

### "key 'X' not allowed"

Register the key first: `keyconf add X /path/to/key.pub`

### "SSH connection failed"

- Check host/port are correct
- Verify password authentication is enabled on the server
- Check network connectivity

### "file does not look like an SSH public key"

Ensure the file is a `.pub` file and starts with a valid key type prefix.
