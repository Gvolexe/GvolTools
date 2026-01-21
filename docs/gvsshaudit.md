# gvsshaudit - SSH Configuration Auditing

Audit SSH configurations for security issues.

## Aliases

- `sa`
- `sshaudit`
- `gvsa`

## Usage

```bash
sa <command> [options]
```

## Commands

### local

Audit local SSH configuration.

```bash
sa local
sa local --json
```

**Checks:**

- ~/.ssh directory permissions (700)
- Private key permissions (600)
- authorized_keys permissions (600)
- SSH config permissions
- SSH agent status

### remote

Audit remote host SSH configuration.

```bash
sa remote admin@server
sa remote admin@server --json
```

**Remote checks:**

- sshd_config security settings
- Root login status
- Password authentication status
- Key-only authentication
- SSH protocol version

### fleet

Audit all hosts in inventory.

```bash
sa fleet
sa fleet --env prod
sa fleet --role web --json
```

### report

Generate comprehensive audit report.

```bash
sa report --env prod
sa report --targets server1,server2 --json
```

## Security Checks

| Check                  | Pass Criteria               |
| ---------------------- | --------------------------- |
| SSH Directory          | 700 permissions             |
| Private Keys           | 600 permissions             |
| authorized_keys        | 600 permissions             |
| PermitRootLogin        | "no" or "prohibit-password" |
| PasswordAuthentication | "no"                        |
| PubkeyAuthentication   | "yes"                       |
| Protocol               | 2 only                      |

## Examples

```bash
# Audit local setup
sa local

# Audit a remote server
sa remote admin@server

# Audit all production servers
sa fleet --env prod

# Generate JSON report
sa report --env prod --json > audit.json
```
