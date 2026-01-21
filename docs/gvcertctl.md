# gvcertctl - TLS Certificate Management

Issue, renew, and deploy TLS certificates using ACME (Let's Encrypt).

## Aliases

- `cert`
- `cc`
- `gvcert`

## Usage

```bash
cert <command> [options]
```

## Commands

### provider add

Configure a DNS provider for DNS-01 challenges.

```bash
cert provider add cloudflare --token CF_API_TOKEN
cert provider add cloudflair --token CF_API_TOKEN  # Alternative spelling accepted
cert provider add route53 --access-key KEY --secret SECRET
```

**Supported providers:**

- cloudflare (also accepts "cloudflair")
- route53
- digitalocean

### issue

Issue a new certificate.

```bash
cert issue example.com --provider cloudflare
cert issue "*.example.com" --provider cloudflare --email admin@example.com
```

**Options:**

- `--provider`, `-p`: DNS provider to use
- `--email`, `-e`: Email for ACME registration

### renew

Renew an existing certificate.

```bash
cert renew example.com
cert renew example.com --dry-run
```

### deploy

Deploy certificate to remote hosts.

```bash
cert deploy example.com --targets web-servers
cert deploy example.com --dest /etc/nginx/ssl --env prod
```

**Options:**

- `--dest`, `-d`: Destination directory
- All target selection options

### status

Show certificate status.

```bash
cert status
cert status example.com --json
```

### revoke

Revoke a certificate.

```bash
cert revoke example.com
cert revoke example.com --reason keycompromise
```

## Configuration

- Providers: `~/.config/gvtools/certs/providers.json`
- Certificates: `~/.config/gvtools/certs/certs.json`

## Prerequisites

- certbot installed
- DNS provider API credentials
- python3-certbot-dns-cloudflare (for Cloudflare)

## Examples

```bash
# Set up Cloudflare provider
cert provider add cloudflare --token "your-api-token"

# Issue wildcard certificate
cert issue "*.example.com" --provider cloudflare --email admin@example.com

# Deploy to web servers
cert deploy example.com --dest /etc/nginx/ssl --role web

# Check all certificates
cert status
```

## Let's Encrypt Rate Limits

- 50 certificates per registered domain per week
- 5 duplicate certificates per week
- Use staging environment for testing:
  ```bash
  certbot certonly --dry-run ...
  ```
