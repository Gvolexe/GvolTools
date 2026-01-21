# gvpermcheck - Permission Auditing

Audit SSH, sudo, and general file permissions.

## Aliases

- `pc`
- `perm`
- `gvpc`

## Usage

```bash
pc <command> [options]
```

## Commands

### ssh

Audit SSH permissions.

```bash
pc ssh server1
pc ssh server1 --json
```

**Checks:**

- ~/.ssh directory (700)
- authorized_keys (600)
- Private keys (600)
- /etc/ssh/sshd_config (600)
- Host keys (600)

### sudoers

Audit sudoers permissions.

```bash
pc sudoers server1
```

**Checks:**

- /etc/sudoers (440)
- /etc/sudoers.d/ (755)
- sudoers.d files (440)
- Syntax validation

### paths

Audit critical path permissions.

```bash
pc paths server1
```

**Checks:**

- /etc/passwd, /etc/shadow, /etc/group
- /tmp, /var/tmp permissions
- World-writable files in /etc
- SUID binaries

### report

Full permission report.

```bash
pc report --targets server1
pc report --env prod --json
```

## Permission Standards

| Path                      | Expected | Owner       |
| ------------------------- | -------- | ----------- |
| ~/.ssh/                   | 700      | user        |
| ~/.ssh/authorized_keys    | 600      | user        |
| ~/.ssh/id\_\* (private)   | 600      | user        |
| /etc/ssh/sshd_config      | 600      | root        |
| /etc/ssh/ssh*host*\*\_key | 600      | root        |
| /etc/sudoers              | 440      | root:root   |
| /etc/sudoers.d/\*         | 440      | root:root   |
| /etc/passwd               | 644      | root        |
| /etc/shadow               | 640      | root:shadow |

## Examples

```bash
# Audit SSH permissions
pc ssh server1

# Audit sudoers
pc sudoers server1

# Full path audit
pc paths server1

# Fleet report
pc report --env prod

# JSON for automation
pc report --env prod --json > perms.json
```

## Output

```
=== SSH PERMISSIONS AUDIT ===
--- User SSH ---
OK: /home/admin/.ssh (700, admin)
OK: /home/admin/.ssh/authorized_keys (600, admin)
FAIL: /home/admin/.ssh/id_rsa is 644, should be 600

--- System SSH ---
OK: /etc/ssh (755, root)
OK: /etc/ssh/sshd_config (600, root)

Problems: 1
```

## Remediation

For failed checks, fix permissions with:

```bash
# Fix private key
chmod 600 ~/.ssh/id_rsa

# Fix .ssh directory
chmod 700 ~/.ssh

# Fix authorized_keys
chmod 600 ~/.ssh/authorized_keys

# Fix sudoers
chmod 440 /etc/sudoers
```
