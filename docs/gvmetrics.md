# gvmetrics - Resource Metrics Collection

Collect lightweight resource metrics snapshots and optionally record time series suitable for export (CSV/JSON).

## Aliases

- `metrics`
- `mx`

## Usage

```bash
gvmetrics <command> [options]
```

## Commands

### collect

Collect metrics snapshot from targets.

```bash
# Single host
gvmetrics collect web1.example.com

# All hosts in a role
gvmetrics collect --role web

# Output as JSON
gvmetrics collect --role web --json

# Output as CSV
gvmetrics collect --role web --csv
```

**Options:**

- `--host`, `-H`: Single host to collect from
- `--role`, `-r`: Target hosts by role
- `--env`, `-e`: Target hosts by environment
- `--json`, `-j`: Output as JSON
- `--csv`: Output as CSV
- `--parallel`, `-p`: Number of parallel collections (default: 10)

### watch

Continuously collect metrics at intervals.

```bash
# Watch every 30 seconds
gvmetrics watch --role web --interval 30

# Watch and save to file
gvmetrics watch --role web --interval 60 --output metrics.csv

# Watch for 10 minutes
gvmetrics watch --role web --interval 30 --duration 600
```

**Options:**

- `--interval`, `-i`: Collection interval in seconds (default: 60)
- `--duration`, `-d`: Total duration in seconds (0 = forever)
- `--output`, `-o`: Output file (CSV or JSON based on extension)

### history

Show metrics history.

```bash
# Last 24 hours
gvmetrics history web1.example.com

# Specific time range
gvmetrics history web1.example.com --since "2024-01-01 00:00" --until "2024-01-02 00:00"
```

## Collected Metrics

| Metric            | Description               | Unit  |
| ----------------- | ------------------------- | ----- |
| `cpu_percent`     | CPU utilization           | %     |
| `memory_percent`  | Memory utilization        | %     |
| `memory_used_mb`  | Memory used               | MB    |
| `memory_total_mb` | Total memory              | MB    |
| `disk_percent`    | Root disk utilization     | %     |
| `disk_used_gb`    | Disk used                 | GB    |
| `disk_total_gb`   | Total disk                | GB    |
| `load_1m`         | 1-minute load average     | -     |
| `load_5m`         | 5-minute load average     | -     |
| `load_15m`        | 15-minute load average    | -     |
| `net_rx_bytes`    | Network bytes received    | bytes |
| `net_tx_bytes`    | Network bytes transmitted | bytes |

## Examples

```bash
# Quick snapshot of all web servers
mx collect --role web

# Export metrics for grafana/prometheus
mx collect --env prod --json > /var/lib/node_exporter/gvmetrics.json

# Watch production DB servers
mx watch --role db --interval 30 --output ~/metrics/db_$(date +%Y%m%d).csv

# Check historical CPU usage
mx history web1.example.com --since 1h --json | jq '.[] | .cpu_percent'
```

## Exit Codes

- `0`: Success
- `1`: Some hosts failed to respond
- `2`: Error
