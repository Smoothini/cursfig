#!/usr/bin/env python3
"""
cursfig - Configuration Backup/Restore Manager
stdlib only: no external dependencies required.

Profile collection entry schema
--------------------------------
{
  "name": "vim",              # must match a name in collections.json
  "kind": "program",          # free string: program | game | script | ...
  "path": "~",                # resolved base path for this OS (written by scan, or set manually)
  "additional_resources": [   # zero or more extras on top of the collection defaults
    {
      "name":    "my extras",
      "paths":   { "linux": "~/scripts", "windows": "D:/scripts" },
      "files":   ["extra.vim"],
      "folders": []
    }
  ]
}

The profile's "os" field (linux | macos | windows) is used to resolve
additional_resource paths at runtime.  The collection base "path" is already
resolved and stored as a plain string when the profile is created via scan.
"""

import argparse
import hashlib
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Disk layout
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).parent
COLLECTIONS  = SCRIPT_DIR / "collections.json"
PROFILES_DIR = SCRIPT_DIR / "profiles"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_path(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data, indent: int = 2):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, default=str)

def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def mtime_iso(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_collections() -> dict[str, dict]:
    """Return {name: collection_def} from the single collections.json."""
    if not COLLECTIONS.exists():
        print(f"[error] collections.json not found at {COLLECTIONS}")
        sys.exit(1)
    return {c["name"]: c for c in load_json(COLLECTIONS)}

def load_profile(name: str) -> dict:
    p = PROFILES_DIR / f"{name}.json"
    if not p.exists():
        print(f"[error] profile not found: {p}")
        sys.exit(1)
    return load_json(p)

# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------

def files_from_resource(base: Path, resource: dict) -> list[Path]:
    """Enumerate existing files described by a resource (files + folders relative to base)."""
    found = []
    for fname in resource.get("files", []):
        p = base / fname
        if p.is_file():
            found.append(p)
    for dname in resource.get("folders", []):
        d = base / dname
        if d.is_dir():
            for fp in sorted(d.rglob("*")):
                if fp.is_file():
                    found.append(fp)
    return found

def resolve_additional(res: dict, os_key: str) -> Path | None:
    """Resolve the base path of an additional_resource using its paths dict + profile OS."""
    raw = res.get("paths", {}).get(os_key)
    return resolve_path(raw) if raw else None

def enumerate_entry(entry: dict, col_def: dict, os_key: str) -> dict[str, list[Path]]:
    """
    Return {resource_name: [files]} for a profile collection entry.
    Uses the pre-resolved entry["path"] for standard resources,
    and entry["additional_resources"][*]["paths"][os_key] for extras.
    """
    result: dict[str, list[Path]] = {}

    # Standard resources — base path already resolved and stored in profile
    raw_base = entry.get("path")
    if raw_base:
        base = resolve_path(raw_base)
        for res in col_def.get("resources", []):
            result[res["name"]] = files_from_resource(base, res)

    # Additional resources — resolve their own paths dict at runtime
    for res in entry.get("additional_resources", []):
        add_base = resolve_additional(res, os_key)
        if add_base:
            result[f"[+] {res['name']}"] = files_from_resource(add_base, res)

    return result

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_scan(args):
    """Scan the machine for all known collections and optionally save a profile."""
    all_cols = load_all_collections()
    os_key   = args.os
    found    = []   # list of (col_name, resolved_base_str)

    for col_name, col_def in all_cols.items():
        raw = col_def.get("paths", {}).get(os_key)
        if not raw:
            continue
        base = resolve_path(raw)

        res_summary = []
        for res in col_def.get("resources", []):
            files = files_from_resource(base, res)
            if files:
                res_summary.append((res["name"], files))

        if not res_summary:
            continue

        found.append((col_name, raw))
        print(f"\n  [{col_def.get('kind','?')}] {col_name}  ({base})")
        for res_name, files in res_summary:
            print(f"    resource: {res_name}  ({len(files)} file{'s' if len(files) != 1 else ''})")
            if args.expand_files_tree:
                for f in files:
                    print(f"      {f}")

    if not found:
        print("Nothing found on this system for the given OS.")
        return

    if args.create_profile:
        profile = {
            "name": args.create_profile,
            "os":   os_key,
            "collections": [
                {
                    "name": col_name,
                    "kind": all_cols[col_name].get("kind", "program"),
                    "path": base_str,
                    "additional_resources": []
                }
                for col_name, base_str in found
            ]
        }
        out = PROFILES_DIR / f"{args.create_profile}.json"
        save_json(out, profile)
        print(f"\nProfile saved → {out}  ({len(found)} collections)")


def cmd_check(args):
    """Show which files/folders from a profile exist on disk."""
    all_cols = load_all_collections()
    profile  = load_profile(args.profile)
    os_key   = profile["os"]

    print(f"Profile '{args.profile}'  OS: {os_key}\n")

    for entry in profile.get("collections", []):
        col_name = entry["name"]
        col_def  = all_cols.get(col_name)
        if not col_def:
            print(f"  [warn] '{col_name}' not in collections.json, skipping")
            continue

        kind     = entry.get("kind", col_def.get("kind", "?"))
        raw_base = entry.get("path", "")
        base     = resolve_path(raw_base) if raw_base else None
        print(f"  [{kind}] {col_name}  base: {base or '(no path)'}")

        if base:
            for res in col_def.get("resources", []):
                _print_resource_check(base, res)

        for res in entry.get("additional_resources", []):
            add_base = resolve_additional(res, os_key)
            if add_base:
                _print_resource_check(add_base, res, label=f"[+] {res['name']}")
            else:
                print(f"    [+] {res['name']}  (no path for os={os_key})")


def _print_resource_check(base: Path, res: dict, label: str | None = None):
    print(f"    {label or res['name']}")
    for fname in res.get("files", []):
        p    = base / fname
        mark = "✓" if p.is_file() else "✗"
        print(f"      {mark} {p}")
    for dname in res.get("folders", []):
        d    = base / dname
        mark = "✓" if d.is_dir() else "✗"
        print(f"      {mark} {d}/")


def cmd_diff(args):
    """Compare current files against a BOM using MD5 hashes."""
    bom_path = Path(args.bom)
    if not bom_path.exists():
        print(f"[error] BOM not found: {bom_path}")
        sys.exit(1)

    bom          = load_json(bom_path)
    profile_name = bom.get("profile")
    bom_time     = bom.get("created_at", "?")
    all_cols     = load_all_collections()
    profile      = load_profile(profile_name)
    os_key       = profile["os"]

    print(f"Diff  profile='{profile_name}'  OS={os_key}  BOM from {bom_time}\n")

    # Flat lookup: abs_path_str -> md5
    bom_index: dict[str, str] = {}
    for kind_block in bom.get("kinds", {}).values():
        for col_block in kind_block.get("collections", {}).values():
            for res_list in col_block.get("resources", {}).values():
                for e in res_list:
                    bom_index[e["path"]] = e["md5"]

    changed = missing = new_file = unchanged = 0
    all_current: set[str] = set()

    for entry in profile.get("collections", []):
        col_name = entry["name"]
        col_def  = all_cols.get(col_name)
        if not col_def:
            continue

        per_res = enumerate_entry(entry, col_def, os_key)
        col_header_printed = False

        for res_name, files in per_res.items():
            for f in files:
                key = str(f)
                all_current.add(key)
                if key not in bom_index:
                    tag = "NEW";  new_file += 1
                elif md5(f) != bom_index[key]:
                    tag = "CHANGED"; changed += 1
                else:
                    tag = "OK";  unchanged += 1

                if tag != "OK":
                    if not col_header_printed:
                        kind = entry.get("kind", col_def.get("kind", "?"))
                        print(f"  [{kind}] {col_name}")
                        col_header_printed = True
                    print(f"    [{tag}] {f}")

    for bom_key in bom_index:
        if bom_key not in all_current and not Path(bom_key).exists():
            missing += 1
            print(f"  [MISSING] {bom_key}")

    print(f"\n  unchanged={unchanged}  changed={changed}  new={new_file}  missing={missing}")


def cmd_backup(args):
    """Create a backup zip (nested by kind) and a BOM json."""
    all_cols = load_all_collections()
    profile  = load_profile(args.profile)
    os_key   = profile["os"]

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    now       = datetime.now(tz=timezone.utc)
    iso_stamp = now.strftime("%Y-%m-%d--%H%M%S")
    base_name = f"cursfig-{args.profile}-{iso_stamp}"
    zip_path  = output_dir / f"{base_name}.zip"
    bom_path  = output_dir / f"{base_name}_BOM.json"

    # Group entries by kind
    by_kind: dict[str, list[dict]] = {}
    for entry in profile.get("collections", []):
        by_kind.setdefault(entry.get("kind", "misc"), []).append(entry)

    bom = {
        "profile":    args.profile,
        "os":         os_key,
        "created_at": now.isoformat(),
        "total_files": 0,
        "kinds":      {}
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        for kind, entries in by_kind.items():
            kind_bom: dict = {"collections": {}}
            kind_buf = io.BytesIO()

            with zipfile.ZipFile(kind_buf, "w", compression=zipfile.ZIP_DEFLATED) as inner:
                for entry in entries:
                    col_name = entry["name"]
                    col_def  = all_cols.get(col_name)
                    if not col_def:
                        print(f"  [warn] '{col_name}' not in collections.json, skipping")
                        continue

                    per_res  = enumerate_entry(entry, col_def, os_key)
                    col_bom: dict = {"resources": {}}

                    for res_name, files in per_res.items():
                        entries_bom = []
                        for f in files:
                            arc_name = f"{col_name}/{f.name}"
                            inner.write(f, arcname=arc_name)
                            entries_bom.append({
                                "path":     str(f),
                                "arc_name": arc_name,
                                "md5":      md5(f),
                                "mtime":    mtime_iso(f),
                                "size":     f.stat().st_size
                            })
                            bom["total_files"] += 1
                        if entries_bom:
                            col_bom["resources"][res_name] = entries_bom

                    kind_bom["collections"][col_name] = col_bom

            kind_buf.seek(0)
            outer.writestr(f"{kind}.zip", kind_buf.read())
            bom["kinds"][kind] = kind_bom

    save_json(bom_path, bom)
    print(f"Backup:  {zip_path}")
    print(f"BOM:     {bom_path}")
    print(f"Files:   {bom['total_files']}  |  Kinds: {', '.join(by_kind.keys())}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(
        prog="cursfig",
        description="Configuration backup/restore manager"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan PC using all default collections")
    p_scan.add_argument("os", help="OS key: linux | macos | windows")
    p_scan.add_argument("--create-profile", metavar="NAME",
                        help="Save found collections as a new profile")
    p_scan.add_argument("-e", "--expand-files-tree", action="store_true",
                        help="Expand and list full file tree instead of just root paths")

    p_check = sub.add_parser("check", help="Check which profile files exist on disk")
    p_check.add_argument("profile", help="Profile name")
    p_check.add_argument("--profiles", metavar="PROFILES",
                        help="Save found collections as a new profile")

    p_diff = sub.add_parser("diff", help="Compare current files against a BOM (MD5)")
    p_diff.add_argument("bom", help="Path to BOM JSON file")

    p_backup = sub.add_parser("backup", help="Create a backup zip + BOM")
    p_backup.add_argument("profile", help="Profile name")
    p_backup.add_argument("output",  help="Output directory")

    args = parser.parse_args()
    {"scan": cmd_scan, "check": cmd_check, "diff": cmd_diff, "backup": cmd_backup}[args.command](args)


if __name__ == "__main__":
    main()
