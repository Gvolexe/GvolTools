# gvsshprofile - SSH Connection Profiles

Generate and manage ~/.ssh/config from reusable profiles.

## Aliases

- `sp`
- `gvsp`

## Usage

```bash
sp <command> [options]
```

## Commands

### group add

Add a profile group.

```bash
sp group add prod-web --pattern "web*.example.com" --user deploy
sp group add bastion --pattern "bastion.example.com" --user admin --port 2222
```

**Options:**

- `--pattern`, `-p`: Host pattern for SSH config
- `--user`, `-u`: Default SSH user
- `--port`: SSH port
- `--key`, `-i`: Identity file path
- `--proxy`, `-J`: ProxyJump host
- `--options`, `-o`: Extra SSH options

### group del

Remove a profile group.

```bash
sp group del prod-web
```

### group list

List all profile groups.

```bash
sp group list
sp group list --json
```

### build

Generate ~/.ssh/config from profiles.

```bash
sp build
sp build --dry-run
sp build --backup
```

### test

Test SSH config syntax.

```bash
sp test
```

### lint

Lint profiles for issues.

```bash
sp lint
sp lint --json
```

## Configuration

Profiles stored at `~/.config/gvtools/sshprofiles.json`.

## Examples

```bash
# Create production bastion profile
sp group add bastion --pattern "bastion.prod.example.com" --user admin --port 22

# Create web tier with jump host
sp group add prod-web --pattern "web*.prod.example.com" --user deploy --proxy bastion

# Generate SSH config
sp build --backup

# Test the configuration
sp test
```

## Generated Config Example

```
# Managed by gvtools
# Group: bastion
Host bastion.prod.example.com
    User admin
    Port 22

# Group: prod-web
Host web*.prod.example.com
    User deploy
    ProxyJump bastion.prod.example.com
```
