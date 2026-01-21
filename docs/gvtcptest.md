# gvtcptest - TCP Connectivity Testing

Test TCP connectivity to specific targets/ports and explain failures (DNS vs routing vs firewall vs service).

## Aliases

- `tcp`

## Usage

```bash
gvtcptest <command> [options]
```

## Commands

### test

Test TCP connectivity from hosts.

```bash
# Test from local machine
gvtcptest test google.com:443

# Test from remote host
gvtcptest test google.com:443 --from web1.example.com

# Test multiple ports
gvtcptest test db.example.com --ports 3306,5432,6379

# Test from all hosts in a role
gvtcptest test api.example.com:443 --from-role web
```

**Options:**

- `--from`, `-f`: Host to test from (default: local)
- `--from-role`: Test from all hosts with this role
- `--from-env`: Test from all hosts in this environment
- `--ports`, `-p`: Comma-separated list of ports
- `--timeout`, `-t`: Connection timeout in seconds (default: 5)
- `--json`, `-j`: Output as JSON

### diagnose

Diagnose connectivity issues with detailed analysis.

```bash
# Full diagnosis
gvtcptest diagnose db.example.com:5432 --from web1.example.com

# Quick check with classification
gvtcptest diagnose api.internal:443 --from-role web
```

### matrix

Test connectivity matrix between hosts.

```bash
# Test all web servers can reach DB servers
gvtcptest matrix --from-role web --to-role db --port 5432

# Full mesh test
gvtcptest matrix --from-role app --to-role app --port 8080
```

## Failure Classification

| Classification | Description                             |
| -------------- | --------------------------------------- |
| `DNS_FAILURE`  | Unable to resolve hostname              |
| `TIMEOUT`      | Connection timed out (likely firewall)  |
| `REFUSED`      | Connection refused (port not listening) |
| `UNREACHABLE`  | Network unreachable (routing issue)     |
| `SUCCESS`      | Connection successful                   |

## Examples

```bash
# Quick connectivity check
tcp test db.internal:5432

# Check if web servers can reach external API
tcp test api.stripe.com:443 --from-role web

# Generate connectivity matrix
tcp matrix --from-role web --to-role db --port 5432 --json

# Diagnose intermittent issues
tcp diagnose cache.internal:6379 --from web1 --count 10

# Test common ports on a host
tcp test newserver.example.com --ports 22,80,443,3306
```

## Exit Codes

- `0`: All tests passed
- `1`: Some tests failed
- `2`: Error running tests
