# cursfig

**cursfig** is a terminal-friendly configuration backup and restore tool with an optional GUI.

## Features

- **Profile management** — create named profiles per machine/OS
- **Default collections** — ships with known paths for NeoVim, WezTerm, Keypirinha, Minecraft, Super Meat Boy, and more
- **Scan** — check which config files and folders actually exist on disk
- **Backup** — push configs to local storage, GitHub, or Google Drive
- **Restore** — pull configs back with conflict detection and overwrite warnings
- **TUI** (Textual) — full terminal UI with keyboard shortcuts
- **GUI** (tkinter) — dark-themed desktop interface
- **CLI** — scriptable command-line interface (Click + Rich)

---

## Installation

```bash
pip install .
# With GitHub support:
pip install ".[github]"
# With Google Drive support:
pip install ".[gdrive]"
# All optional deps:
pip install ".[all]"
```

---

## Quick Start

### CLI

```bash
# Create a profile
cursfig profile new mypc --os linux

# See what default collections are available
cursfig defaults

# Add programs and games
cursfig add program NeoVim
cursfig add program WezTerm
cursfig add game Minecraft

# Scan: see what files exist on disk
cursfig scan

# Set up a backup provider (interactive)
cursfig provider setup local
cursfig provider setup github
cursfig provider setup google_drive

# Backup
cursfig backup

# Restore (warns on conflicts)
cursfig restore
```

### TUI (interactive terminal UI)

```bash
cursfig tui
```

**TUI key bindings:**
| Key | Action |
|-----|--------|
| `N` | New profile |
| `S` | Scan |
| `B` | Backup |
| `R` | Restore |
| `?` | Help |
| `Q` | Quit |

### GUI

```bash
cursfig --gui
# or
python -m cursfig --gui
```

---

## Profile YAML format

Profiles are stored in `~/.cursfig/profiles/<name>.yaml`.

```yaml
profile:
  name: "mypc"
  description: "Work laptop"
  os: "linux"
  providers:
    - github
    - local
  backup_policy:
    programs:
      providers: [github]
    games:
      providers: [google_drive, local]
  collections:
    programs:
      - name: NeoVim
      - name: WezTerm
        additional_resources:
          - name: "extra themes"
            files: ["colors.lua"]
            path:
              linux: "~/.config/wezterm"
    games:
      - name: Minecraft
        exclude_providers: [github]
      - name: Supermeatboy
```

---

## Default Collections

`default_collections.yaml` ships with the tool and can be overridden by placing your own at `~/.cursfig/default_collections.yaml`.

Each entry defines:
- **name** — matched case-insensitively against profile collections
- **kind** — `program` or `game`
- **resources** — list of named resource groups, each with per-OS paths and file/folder lists

---

## Providers

### Local
Copies files to a directory on disk (USB drive, NAS, etc.).

```bash
cursfig provider setup local
# Prompts for a directory path
```

### GitHub
Uploads files to a GitHub repository using the API.

```bash
pip install ".[github]"
cursfig provider setup github
# Prompts for token and repo (user/repo)
```

### Google Drive
Uploads files to a Google Drive folder.

```bash
pip install ".[gdrive]"
cursfig provider setup google_drive
# Prompts for credentials JSON and optional folder ID
```

---

## App data location

| Item | Path |
|------|------|
| App config | `~/.cursfig/config.json` |
| Profiles | `~/.cursfig/profiles/` |
| Default collections override | `~/.cursfig/default_collections.yaml` |
