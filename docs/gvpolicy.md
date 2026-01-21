# gvpolicy - Security Policy Enforcement

Define policy rules for your fleet (security/hardening/ops baselines) and evaluate compliance.

## Aliases

- `pol`

## Usage

```bash
gvpolicy <command> [options]
```

## Commands

### rule

Manage policy rules.

```bash
# List all rules
gvpolicy rule list

# Add a rule
gvpolicy rule add ssh-hardened \
  --check ssh.password_disabled \
  --severity high \
  --description "SSH password auth must be disabled"

# Show rule details
gvpolicy rule show ssh-hardened

# Delete a rule
gvpolicy rule del ssh-hardened
```

**Rule Options:**

- `--check`, `-c`: Check to use (see built-in checks)
- `--severity`, `-s`: critical, high, medium, low
- `--description`, `-d`: Human-readable description
- `--remediation`: How to fix violations
- `--custom-script`: Custom check script

### eval

Evaluate policies against hosts.

```bash
# Evaluate all rules
gvpolicy eval --role web

# Evaluate specific rule
gvpolicy eval --role web --rule ssh-hardened

# Evaluate with JSON output
gvpolicy eval --env prod --json

# Evaluate single host
gvpolicy eval web1.example.com
```

**Options:**

- `--host`, `-H`: Single host to evaluate
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--rule`: Specific rule to evaluate
- `--severity`, `-s`: Minimum severity to check
- `--json`, `-j`: Output as JSON

### waive

Add a policy waiver for a host.

```bash
# Temporary waiver
gvpolicy waive ssh-hardened web1.example.com \
  --until "2024-12-31" \
  --reason "Legacy app requires password auth"

# Permanent waiver
gvpolicy waive ssh-hardened web1.example.com \
  --permanent \
  --reason "Air-gapped network"

# List waivers
gvpolicy waive --list
```

### checks

List available built-in checks.

```bash
gvpolicy checks
gvpolicy checks --verbose
```

## Built-in Checks

| Check                      | Description                         |
| -------------------------- | ----------------------------------- |
| `ssh.password_disabled`    | SSH password auth is disabled       |
| `ssh.root_disabled`        | SSH root login is disabled          |
| `ssh.port_22`              | SSH is on port 22                   |
| `firewall.enabled`         | Firewall is active                  |
| `updates.security`         | No pending security updates         |
| `users.no_empty_passwords` | No users with empty passwords       |
| `files.etc_shadow_perms`   | /etc/shadow has correct permissions |
| `selinux.enforcing`        | SELinux is enforcing (RHEL)         |
| `apparmor.enabled`         | AppArmor is enabled (Debian)        |

## Custom Checks

Create custom checks with shell scripts:

```bash
gvpolicy rule add my-check \
  --severity medium \
  --description "Custom compliance check" \
  --custom-script '#!/bin/bash
    # Exit 0 = compliant, exit 1 = non-compliant
    grep -q "^restrict" /etc/ntp.conf
  '
```

## Examples

```bash
# List all available checks
pol checks

# Create security baseline
pol rule add ssh-hardened --check ssh.password_disabled --severity high
pol rule add ssh-no-root --check ssh.root_disabled --severity critical
pol rule add firewall-on --check firewall.enabled --severity high

# Evaluate production environment
pol eval --env prod

# Generate compliance report
pol eval --env prod --json > compliance-report.json

# Add waiver for known exception
pol waive ssh-hardened legacy-server \
  --until "2024-06-30" \
  --reason "Migration in progress"
```

## Exit Codes

- `0`: All hosts compliant
- `1`: Some hosts non-compliant
- `2`: Critical violations found
- `3`: Error running checks
