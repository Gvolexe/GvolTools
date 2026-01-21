# gvgitopsinit - GitOps Repository Scaffolding

Create GitOps-ready infrastructure repositories.

## Aliases

- `gi`
- `gitops`
- `gvgi`

## Usage

```bash
gi <command> [options]
```

## Commands

### new

Create a new GitOps repository.

```bash
gi new my-infra
gi new my-infra --path ~/projects --git
```

**Options:**

- `--path`, `-p`: Parent directory
- `--git`, `-g`: Initialize git repository

### add-role

Add a new role.

```bash
gi add-role webserver
gi add-role database
```

### add-env

Add a new environment.

```bash
gi add-env staging
gi add-env development
```

### validate

Validate repository structure.

```bash
gi validate
gi validate --json
```

## Repository Structure

```
my-infra/
├── inventory/
│   └── hosts.json        # Host inventory
├── roles/
│   └── common/
│       ├── tasks.sh      # Role tasks
│       └── vars.json     # Role variables
├── envs/
│   ├── production/
│   │   └── vars.json
│   └── staging/
│       └── vars.json
├── secrets/              # Encrypted secrets
│   └── .gitignore
├── scripts/
│   └── deploy.sh         # Deployment script
├── .github/
│   └── workflows/
│       └── validate.yml  # CI validation
├── README.md
└── .gitignore
```

## Examples

```bash
# Create new infrastructure repo
gi new company-infra --git
cd company-infra

# Add environments
gi add-env development
gi add-env staging

# Add roles
gi add-role webserver
gi add-role database
gi add-role monitoring

# Validate structure
gi validate
```

## Integration with GVTools

The generated repository works with other gvtools:

```bash
# Import hosts to gvfleet
gvfleet import --file inventory/hosts.json

# Bootstrap hosts
gvhb full root@newserver --user admin

# Apply roles
./scripts/deploy.sh production webserver
```

## GitHub Actions

Includes validation workflow:

- JSON syntax validation
- Shellcheck for scripts
- Runs on push and PR

## Best Practices

1. **Environment isolation**: Separate vars per environment
2. **Secret management**: Use gvsecretsync for secrets
3. **Role reuse**: Keep roles generic and reusable
4. **Version control**: Commit all changes with clear messages
5. **Review process**: Use PRs for infrastructure changes
