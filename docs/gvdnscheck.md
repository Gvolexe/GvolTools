# gvdnscheck - DNS Validation and Consistency

Validate DNS resolution and check SSH fingerprint consistency.

## Aliases

- `dns`
- `dc`
- `gvdns`

## Usage

```bash
dns <command> [options]
```

## Commands

### lookup

Lookup DNS records.

```bash
dns lookup example.com
dns lookup example.com --type MX
dns lookup example.com --type TXT
```

**Options:**

- `--type`, `-t`: Record type (A, AAAA, MX, TXT, NS, CNAME)

### zone

Query all zone records.

```bash
dns zone example.com
dns zone example.com --json
```

### ssh-consistency

Check SSH fingerprint consistency with DNS.

```bash
dns ssh-consistency --targets server1
dns ssh-consistency --env prod
```

**Checks:**

- DNS resolution works
- SSH port is reachable
- Host keys are valid

### report

Generate DNS report for inventory.

```bash
dns report
dns report --json
```

## Examples

```bash
# Lookup A record
dns lookup server.example.com

# Check MX records
dns lookup example.com --type MX

# Get all zone records
dns zone example.com

# Verify SSH/DNS consistency
dns ssh-consistency --env prod

# Full DNS report
dns report --json > dns-report.json
```

## Use Cases

1. **Before provisioning**: Verify DNS is configured
2. **SSH troubleshooting**: Check if DNS matches SSH fingerprints
3. **Audit**: Ensure all inventory hosts resolve
4. **Migration**: Verify DNS propagation
