# gvrebootctl - Reboot Coordination

Detect whether hosts require a reboot, coordinate safe reboots across target sets, and validate that critical services return healthy post-reboot.

## Aliases

- `rb`

## Usage

```bash
gvrebootctl <command> [options]
```

## Commands

### check

Check if hosts need a reboot.

```bash
# Check a single host
gvrebootctl check web1.example.com

# Check all hosts in a role
gvrebootctl check --role web

# Show reasons
gvrebootctl check --role web --reasons

# JSON output
gvrebootctl check --env prod --json
```

**Options:**

- `--host`, `-H`: Single host to check
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--reasons`: Show why reboot is needed
- `--json`, `-j`: Output as JSON

### plan

Generate a reboot plan.

```bash
# Create plan for web tier
gvrebootctl plan --role web --batch-size 2 --interval 120

# Plan with custom validation
gvrebootctl plan --role web \
  --batch-size 1 \
  --services "nginx,sshd"
```

**Options:**

- `--batch-size`, `-b`: Hosts per batch (default: 1)
- `--interval`, `-i`: Seconds between batches (default: 120)
- `--services`, `-s`: Services to validate post-reboot

### run

Execute reboots according to plan.

```bash
# Execute reboot plan
gvrebootctl run --role web --batch-size 1 --yes

# Execute with validation
gvrebootctl run --role web \
  --batch-size 1 \
  --interval 120 \
  --services "nginx,sshd" \
  --yes
```

**Options:**

- `--timeout`, `-t`: Reboot timeout in seconds (default: 300)
- `--yes`, `-y`: Skip confirmation
- All planning options from `plan`

### validate

Validate services are healthy post-reboot.

```bash
# Validate services on hosts
gvrebootctl validate --role web --services "nginx,sshd"

# Custom validation command
gvrebootctl validate --role web --cmd "curl -sf localhost/health"
```

### cancel

Cancel pending reboots (if scheduled).

```bash
gvrebootctl cancel --role web
```

## Reboot Detection

Detects reboot requirements from:

| Source                          | Description                        |
| ------------------------------- | ---------------------------------- |
| `/var/run/reboot-required`      | Debian/Ubuntu package updates      |
| `needs-restarting -r`           | RHEL/CentOS/Fedora                 |
| Kernel version mismatch         | Running kernel != installed kernel |
| `/var/run/reboot-required.pkgs` | Specific packages requiring reboot |

## Examples

```bash
# Check which web servers need reboots
rb check --role web --reasons

# Plan and preview
rb plan --role web --batch-size 2 --interval 60

# Execute rolling reboots
rb run --role web \
  --batch-size 1 \
  --interval 120 \
  --services "nginx,sshd,myapp" \
  --yes

# Validate after manual reboot
rb validate web1.example.com --services "nginx,sshd"
```

## Safety Features

- **Batch size limits**: Default batch size of 1
- **Mandatory intervals**: Minimum 60 seconds between batches
- **Service validation**: Verify services are running post-reboot
- **Timeout handling**: Detect hosts that fail to come back
- **Confirmation prompts**: Require explicit confirmation

## Exit Codes

- `0`: All reboots successful
- `1`: Some reboots or validations failed
- `2`: Hosts failed to come back online
- `3`: Error
