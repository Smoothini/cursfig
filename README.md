# cursfig 🏗🏗🏗in progress🏗

Configuration backup/restore manager. Pure Python 3.10+, stdlib only.

## Usage

```
python cursfig.py <command> [options]
```

### Commands

```bash
# Scan PC for all known configs (linux | macos | windows)
python cursfig.py scan linux
python cursfig.py scan linux --create-profile my-machine

# Check which files from a profile exist on disk (✓/✗)
python cursfig.py check my-machine

# Compare current files against a previous BOM (MD5 hash diff)
python cursfig.py diff /backups/cursfig-my-machine-20250101T120000Z_BOM.json

# Create a backup zip + BOM
python cursfig.py backup my-machine /backups
```

Output files from `backup`:
- `cursfig-PROFILE-ISODATETIME.zip` — outer zip, one inner zip per `kind`
- `cursfig-PROFILE-ISODATETIME_BOM.json` — full file manifest with MD5, mtime, size

---

## File Structure

```
cursfig/
├── cursfig.py          # the script
├── collections.json    # all collection definitions
└── profiles/
    ├── dev-workstation.json
    └── gaming.json
```

---

## JSON Schemas

### `collections.json` — array of collection objects

```json
[
  {
    "name": "vim",
    "kind": "program",
    "paths": {
      "linux":   "~",
      "macos":   "~",
      "windows": "%USERPROFILE%"
    },
    "resources": [
      {
        "name":    "config",
        "files":   [".vimrc"],
        "folders": [".vim"]
      }
    ]
  }
]
```

- **`kind`**: free string — `program`, `game`, `script`, etc.
- **`paths`**: OS → base path. Keys: `linux`, `macos`, `windows`.
  Supports `~` and env vars (`%APPDATA%`, `%USERPROFILE%`, `%LOCALAPPDATA%`).
  Omit an OS key if the program doesn't exist there.
- **`resources`**: named sets of files/folders relative to the base path.
  Folders are included recursively.

### `profiles/<n>.json`

```json
{
  "name": "my-machine",
  "os": "linux",
  "collections": [
    {
      "name": "vim",
      "kind": "program",
      "path": "~",
      "additional_resources": [
        {
          "name":    "work extras",
          "paths":   { "linux": "~/work/vim", "windows": "D:/work/vim" },
          "files":   ["work.vim"],
          "folders": []
        }
      ]
    }
  ]
}
```

- **`os`**: `linux`, `macos`, or `windows`.
- **`collections`**: each entry references a collection by name.
  - **`path`**: the pre-resolved base path for this machine/OS. Written
    automatically by `scan --create-profile`; edit manually if needed.
    Resources from `collections.json` are resolved relative to this path.
  - **`additional_resources`**: zero or more extras with their own `paths`
    dict (same OS-keyed format). Resolved at runtime using the profile `os`.

### BOM (`*_BOM.json`)

```json
{
  "profile": "my-machine",
  "os": "linux",
  "created_at": "2025-01-01T12:00:00+00:00",
  "total_files": 42,
  "kinds": {
    "program": {
      "collections": {
        "vim": {
          "resources": {
            "config": [
              {
                "path":     "/home/user/.vimrc",
                "arc_name": "vim/.vimrc",
                "md5":      "abc123...",
                "mtime":    "2024-11-01T10:00:00+00:00",
                "size":     1024
              }
            ]
          }
        }
      }
    }
  }
}
```

---

## Adding Collections

Append an entry to `collections.json`. Reference it by `name` in a profile.

## Typical Workflow

1. `scan linux --create-profile my-machine` — discover what's on this machine
2. Edit `profiles/my-machine.json` — trim collections, add `additional_resources`
3. `check my-machine` — verify everything looks right
4. `backup my-machine ~/backups` — take a snapshot
5. Later: `diff ~/backups/cursfig-my-machine-…_BOM.json` — see what changed
