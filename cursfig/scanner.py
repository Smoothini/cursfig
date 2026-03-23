"""Scanner: resolves paths and checks which files/folders exist."""
from __future__ import annotations
import os
import re
from pathlib import Path
from .models import (
    OS, Profile, DefaultCollection, UserCollectionItem,
    CollectionKind, Resource, ScanResult,
)


def _expand_path(raw: str, os_type: OS) -> Path:
    """Expand environment variables and ~ for the target OS."""
    if os_type == OS.WINDOWS:
        # Expand Windows-style %VAR% using os.environ on the running system,
        # falling back to the literal string for vars not set (cross-platform scan)
        def _win_expand(m: re.Match) -> str:
            return os.environ.get(m.group(1), m.group(0))
        expanded = re.sub(r"%([^%]+)%", _win_expand, raw)
    else:
        expanded = raw
    return Path(os.path.expanduser(expanded))


def _resolve_resources(
    item: UserCollectionItem,
    default_col: DefaultCollection | None,
    os_type: OS,
) -> list[tuple[Resource, Path]]:
    """Return list of (resource, resolved_path) pairs for a collection item."""
    base_resources: list[Resource] = []
    if default_col:
        base_resources = list(default_col.resources)

    # Merge: start with defaults, then append additional_resources
    all_resources = list(base_resources) + list(item.additional_resources)
    result = []
    for res in all_resources:
        resolved = _expand_path(res.path.for_os(os_type), os_type)
        result.append((res, resolved))
    return result


def scan_profile(
    profile: Profile,
    defaults: dict[str, DefaultCollection],
) -> list[ScanResult]:
    results: list[ScanResult] = []

    def _scan_items(items: list[UserCollectionItem], kind: CollectionKind):
        for item in items:
            default_col = defaults.get(item.name.lower())
            resource_pairs = _resolve_resources(item, default_col, profile.os)
            for res, base_path in resource_pairs:
                file_checks = [(f, (base_path / f).exists()) for f in res.files]
                folder_checks = [(f, (base_path / f).exists()) for f in res.folders]
                results.append(ScanResult(
                    collection_name=item.name,
                    kind=kind,
                    resource_name=res.name,
                    path=str(base_path),
                    files=file_checks,
                    folders=folder_checks,
                ))

    _scan_items(profile.programs, CollectionKind.PROGRAM)
    _scan_items(profile.games, CollectionKind.GAME)
    return results


def collect_backup_files(
    profile: Profile,
    defaults: dict[str, DefaultCollection],
) -> list[tuple[str, str, Path]]:
    """Return list of (collection_name, relative_name, absolute_path) for all found files/folders."""
    found = []

    def _collect(items: list[UserCollectionItem], kind: CollectionKind):
        for item in items:
            default_col = defaults.get(item.name.lower())
            resource_pairs = _resolve_resources(item, default_col, profile.os)
            for res, base_path in resource_pairs:
                for fname in res.files:
                    p = base_path / fname
                    if p.exists():
                        found.append((item.name, fname, p))
                for folder in res.folders:
                    p = base_path / folder
                    if p.exists():
                        found.append((item.name, folder, p))

    _collect(profile.programs, CollectionKind.PROGRAM)
    _collect(profile.games, CollectionKind.GAME)
    return found
