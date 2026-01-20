# gvoltools

Collection of small utilities maintained under a single repository, with a consistent tool layout and a JSON-driven installer.

## Repository structure

```
gvoltools/
  installgvtools.sh
  README.md
  <toolname>/
    setup.json
    files/
      ...tool files...
```

- Each tool lives in its own directory: `gvoltools/<toolname>/`
- Each tool must provide:
  - `setup.json` (installation metadata and targets)
  - `files/` (the files that will be installed/copied)

## Installer

`installgvtools.sh` reads `setup.json` and performs install actions into user locations (typically `~/.local/bin`).

### Usage

```bash
./installgvtools.sh list
./installgvtools.sh install <toolname> [--deps]
./installgvtools.sh uninstall <toolname>
./installgvtools.sh status <toolname>
```

- `list`: shows all tools that contain a `setup.json`
- `install`: applies the install targets from that tool's `setup.json`
- `--deps`: installs OS-specific dependencies if defined in `setup.json`
- `uninstall`: removes installed files/symlinks listed in the tool's `setup.json`
- `status`: check installation status of a tool

## Tool: gvolkeymanager

`gvolkeymanager` is the refactor of the earlier `keyup` + `keyconf` functionality:

- `keyup user@host[:port] <keyname>`:
  - prompts for password
  - prompts option:
    1. create user `gvol` (or custom user) + upload key
    2. upload key to the provided user

- `keyconf add|del|list|show`:
  - maintains allowed key names and their `.pub` paths

Installed commands:

- `gvolkeymanager`
- `keyup` (symlink to `gvolkeymanager`)
- `keyconf` (symlink to `gvolkeymanager`)

Config location:

- Uses XDG config (prefers legacy `~/.config/keyup/keys.json` if it exists, otherwise `~/.config/gvolkeymanager/keys.json`)

## setup.json format

Minimum required keys:

```json
{
  "tool": "toolname",
  "version": "0.1.0",
  "description": "what it does",
  "deps": {
    "arch": ["pkg1", "pkg2"],
    "debian": ["pkg1", "pkg2"]
  },
  "install": {
    "targets": [
      {
        "type": "copy",
        "src": "files/foo",
        "dst": "~/.local/bin/foo",
        "chmod": "755"
      },
      {
        "type": "symlink",
        "link": "~/.local/bin/bar",
        "target": "~/.local/bin/foo"
      }
    ]
  }
}
```

### Target types

- `copy`
  - `src`: path relative to the tool directory
  - `dst`: absolute path or `~`-expanded path
  - `chmod`: optional mode string (e.g. `"755"`)

- `symlink`
  - `link`: the symlink path to create
  - `target`: the path the symlink should point to

Rules:

- Do not create self-symlinks (installer refuses them).
- `dst` should never point into the repository; install into user locations such as `~/.local/bin`.

## Adding a new tool

1. Create the directory structure:

```bash
mkdir -p <toolname>/files
```

2. Add `setup.json` to `<toolname>/setup.json`.

3. Put installable artifacts in `<toolname>/files/`.

4. Ensure installed entrypoints are executable (e.g. Python scripts have shebangs and `chmod +x`).

5. Test:

```bash
./installgvtools.sh install <toolname>
hash -r
which <installed_command>
```

6. Commit changes.

## Maintenance guidelines

- Keep tools independent: no shared global state inside the repo.
- Store runtime/config state under XDG config (`~/.config/<toolname>/...`) and do not commit it.
- Avoid secrets in the repository (keys, tokens, hostnames tied to private infrastructure).
- Prefer idempotent behavior: re-running an install or command should not duplicate entries or break state.
- Keep OS dependency lists accurate in `setup.json` (`deps.arch`, `deps.debian`) to support `--deps`.

## Contributing / Git workflow

Typical flow:

```bash
git add .
git commit -m "Describe change"
git push
```

Recommended: add tags when releasing versions:

```bash
git tag -a v0.1.0 -m "v0.1.0"
git push --tags
```
