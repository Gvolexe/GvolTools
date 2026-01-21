# gvsecretsync - Encrypted Secrets Distribution

Manage and distribute encrypted secrets across your infrastructure.

## Aliases

- `sec`
- `secrets`
- `gvs`

## Usage

```bash
sec <command> [options]
```

## Commands

### add

Add a new secret interactively.

```bash
sec add db-password --scope database
sec add api-key --scope web --owner gvol
```

**Options:**

- `--scope`, `-s`: Secret scope (limits which hosts can access)
- `--owner`, `-o`: Secret owner

### put

Deploy a secret to hosts.

```bash
sec put db-password --dest /etc/app/db.secret --targets db-servers
sec put api-key --dest /etc/api/key --env prod --mode 600 --owner app
```

**Options:**

- `--dest`, `-d`: Destination path on target
- `--mode`: File permissions (default: 600)
- `--owner`: File owner on target
- All target selection options

### rotate

Rotate a secret with a new value.

```bash
sec rotate db-password
sec rotate api-key --redeploy
```

### status

Show secret status.

```bash
sec status
sec status db-password --json
```

### rm

Remove a secret.

```bash
sec rm old-secret
sec rm old-secret --yes
```

## Configuration

Secrets stored encrypted at `~/.config/gvtools/secrets/`

## Encryption

- Uses Fernet symmetric encryption
- Master key derived from user input
- Secrets encrypted at rest
- Decrypted only during deployment

## Examples

```bash
# Add a database password
sec add db-password --scope database
# (Enter secret value interactively)

# Deploy to database servers
sec put db-password --dest /etc/db.secret --role database --mode 600

# Check deployment status
sec status

# Rotate an API key
sec rotate api-key --redeploy
```

## Security Notes

1. Secrets are encrypted locally before storage
2. Decryption happens only during deployment
3. Transmitted over SSH (encrypted in transit)
4. Deployed with restricted permissions
5. No secrets in logs or command history
