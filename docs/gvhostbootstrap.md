# gvhostbootstrap - Host Security Bootstrap

Bootstrap new hosts to a secure baseline configuration.

## Aliases

- `hb`
- `gvhb`

## Usage

```bash
hb <command> [options]
```

## Commands

### init

Create admin user and deploy SSH key.

```bash
hb init root@newserver --user admin --key ~/.ssh/id_ed25519.pub
hb init root@newserver --user deploy --groups "sudo,docker"
```

**Options:**

- `--user`, `-u`: New admin username
- `--key`, `-k`: SSH public key to deploy
- `--groups`, `-g`: Additional groups for user

### harden

Apply security hardening.

```bash
hb harden admin@server
hb harden admin@server --dry-run
```

**Hardening includes:**

- Disable root SSH login
- Disable password authentication
- Configure SSH key-only auth
- Enable UFW firewall
- Allow only SSH through firewall
- Install and configure fail2ban
- Configure SSH idle timeout

### full

Run both init and harden in one step.

```bash
hb full root@newserver --user admin --key ~/.ssh/id_ed25519.pub
```

### status

Check security status of a host.

```bash
hb status admin@server
hb status admin@server --json
```

## Examples

```bash
# Bootstrap a new server completely
hb full root@192.168.1.100 --user admin --key ~/.ssh/admin_key.pub

# Just create an admin user
hb init root@server --user deploy

# Apply hardening to existing server
hb harden admin@server

# Check security status
hb status admin@server
```

## Security Baseline

After running `hb full`, your server will have:

1. **SSH Security**
   - Root login disabled
   - Password authentication disabled
   - Key-based auth only
   - Idle timeout configured

2. **Firewall**
   - UFW enabled
   - Only SSH port allowed
   - Default deny incoming

3. **Intrusion Prevention**
   - fail2ban installed
   - SSH brute-force protection

## Warning

Running `hb harden` will disable password authentication. Ensure you have SSH key access configured before running.
