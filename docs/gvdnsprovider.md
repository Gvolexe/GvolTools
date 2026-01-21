# gvdnsprovider - DNS Provider Configuration

Unified credential and configuration store for DNS providers (Cloudflare, etc.) to be consumed by gvcertctl and other tools.

## Aliases

- `dnsprov`
- `dp`

## Usage

```bash
gvdnsprovider <command> [options]
```

## Commands

### add

Add a DNS provider.

```bash
# Add Cloudflare with token from environment
gvdnsprovider add cloudflare --token env:CF_API_TOKEN --default-zone example.com

# Add with token prompt (secure input)
gvdnsprovider add cloudflare --token prompt

# Add with token file
gvdnsprovider add cloudflare --token file:~/.secrets/cf_token

# Add Route53 with profile
gvdnsprovider add route53 --profile aws-prod --default-zone example.com
```

**Options:**

- `--token`, `-t`: API token (supports env:, file:, prompt)
- `--default-zone`, `-z`: Default zone for this provider
- `--email`, `-e`: Email (for providers that require it)
- `--profile`, `-p`: AWS profile name (Route53)

### list

List configured providers.

```bash
gvdnsprovider list
gvdnsprovider list --json
```

### show

Show provider details.

```bash
gvdnsprovider show cloudflare
gvdnsprovider show cloudflare --show-token
```

### test

Test provider credentials.

```bash
# Basic token validation
gvdnsprovider test cloudflare

# Test with specific zone
gvdnsprovider test cloudflare --zone example.com

# Full DNS-01 challenge test
gvdnsprovider test cloudflare --zone example.com --dns01
```

### del

Delete a provider.

```bash
gvdnsprovider del cloudflare
gvdnsprovider del cloudflare --yes
```

### export

Export provider configuration.

```bash
# Export without secrets
gvdnsprovider export > providers.json

# Export with secrets (encrypted)
gvdnsprovider export --with-secrets --encrypt > providers.enc.json
```

### import

Import provider configuration.

```bash
gvdnsprovider import providers.json
gvdnsprovider import providers.enc.json --decrypt
```

## Supported Providers

| Provider       | Auth Method      | Required Fields                        |
| -------------- | ---------------- | -------------------------------------- |
| `cloudflare`   | API Token        | `token`                                |
| `route53`      | AWS Profile/Keys | `profile` or `access_key`/`secret_key` |
| `digitalocean` | API Token        | `token`                                |
| `linode`       | API Token        | `token`                                |
| `vultr`        | API Key          | `api_key`                              |
| `godaddy`      | API Key + Secret | `api_key`, `api_secret`                |

## Token Sources

Tokens can be specified as:

| Format               | Description                    |
| -------------------- | ------------------------------ |
| `env:VARNAME`        | Read from environment variable |
| `file:/path/to/file` | Read from file                 |
| `prompt`             | Prompt for secure input        |
| `literal-value`      | Direct value (not recommended) |

## Examples

```bash
# Set up Cloudflare
dp add cloudflare --token env:CF_API_TOKEN --default-zone example.com

# Verify it works
dp test cloudflare --zone example.com

# List all providers
dp list

# Use with gvcertctl
cert issue example.com --method dns01 --provider cloudflare

# Export for backup
dp export > ~/backup/dns-providers.json
```

## Integration

gvdnsprovider integrates with:

- **gvcertctl**: Automatic DNS-01 challenge solving
- **gvdnscheck**: DNS record verification

## Exit Codes

- `0`: Success
- `1`: Provider error or invalid credentials
- `2`: Error
