# gvsudoauth - Sudo Authentication Configuration

Configure sudo authentication with SSH agent support.

## Aliases

- `su`
- `sudoauth`
- `gvsu`

## Usage

```bash
su <command> [options]
```

## Commands

### status

Check sudo authentication status.

```bash
su status server1
su status --targets server1,server2 --json
```

### enable-agent

Enable SSH agent authentication for sudo.

```bash
su enable-agent --targets server1
su enable-agent --env prod
```

**This configures:**

- pam_ssh_agent_auth PAM module
- SSH authorized keys for sudo
- Passwordless sudo via SSH key

### disable-agent

Disable SSH agent authentication.

```bash
su disable-agent --targets server1
```

### enable-nopasswd

Enable NOPASSWD sudo for a user.

```bash
su enable-nopasswd admin --targets server1
su enable-nopasswd deploy --env prod
```

### disable-nopasswd

Disable NOPASSWD sudo.

```bash
su disable-nopasswd admin --targets server1
```

## How SSH Agent Auth Works

1. User's SSH key is used for sudo authentication
2. When you sudo, your SSH agent proves your identity
3. No password needed - verified by same key used for SSH

## Prerequisites

- `pam_ssh_agent_auth` package installed
- SSH agent forwarding enabled
- User's public key on target

## Examples

```bash
# Check current status
su status server1

# Enable SSH agent sudo on production
su enable-agent --env prod --dry-run
su enable-agent --env prod

# Set up NOPASSWD for deploy user
su enable-nopasswd deploy --role web

# Check status across fleet
su status --env prod --json
```

## Security Considerations

1. **Agent forwarding**: Be cautious with agent forwarding to untrusted hosts
2. **Key protection**: Your SSH key becomes your sudo credential
3. **Logging**: Sudo actions are still logged as normal
4. **Fallback**: Password authentication remains as fallback

## PAM Configuration

When enabled, adds to `/etc/pam.d/sudo`:

```
auth sufficient pam_ssh_agent_auth.so file=/etc/security/authorized_keys
```
