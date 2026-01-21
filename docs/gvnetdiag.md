# gvnetdiag - Network Diagnostics

Ping, traceroute, and port probing from local and remote nodes.

## Aliases

- `nd`
- `netdiag`
- `gvnd`

## Usage

```bash
nd <command> [options]
```

## Commands

### local

Run local network diagnostics.

```bash
nd local
nd local 1.1.1.1
nd local google.com
```

**Checks:**

- Ping connectivity
- DNS resolution
- Default gateway

### remote

Run diagnostics from a remote host.

```bash
nd remote server1 --probe google.com
nd remote server1 --probe 8.8.8.8
```

**Options:**

- `--probe`, `-p`: Target to probe from remote

### ports

Check open ports on target.

```bash
nd ports server1
nd ports server1 --ports 22,80,443,3306
nd ports 192.168.1.1 --ports 22,80
```

**Options:**

- `--ports`: Comma-separated ports to check

**Default ports:** 22, 80, 443

### trace

Run traceroute.

```bash
nd trace 8.8.8.8
nd trace google.com
```

### report

Network report for inventory hosts.

```bash
nd report --targets server1
nd report --env prod --json
```

## Examples

```bash
# Quick local network check
nd local

# Check connectivity from a server
nd remote server1 --probe google.com

# Scan common ports
nd ports webserver

# Scan specific ports
nd ports dbserver --ports 3306,5432,6379

# Traceroute
nd trace 8.8.8.8

# Fleet network report
nd report --env prod --json
```

## Output

### Port check output

```
Port    Status    Service
22      OPEN      SSH
80      OPEN      HTTP
443     OPEN      HTTPS
3306    CLOSED    MySQL
```

### Report output

```
Host    Ping    SSH    HTTP    HTTPS
web1    ✓       ✓      ✓       ✓
web2    ✓       ✓      ✓       ✓
db1     ✓       ✓      -       -
```
