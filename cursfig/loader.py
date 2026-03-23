"""YAML parsing for cursfig profiles and default collections."""
from __future__ import annotations
import yaml
from pathlib import Path
from .models import (
    OS, ProviderType, CollectionKind,
    PathSpec, Resource, DefaultCollection,
    UserCollectionItem, BackupPolicy, Profile,
)


def _parse_path_spec(raw: dict | None) -> PathSpec:
    if not raw:
        return PathSpec()
    return PathSpec(
        windows=raw.get("windows", "~"),
        linux=raw.get("linux", "~"),
        macos=raw.get("macos", "~"),
    )


def _parse_resource(raw: dict) -> Resource:
    return Resource(
        name=raw["name"],
        path=_parse_path_spec(raw.get("path")),
        files=raw.get("files", []),
        folders=raw.get("folders", []),
    )


def load_default_collections(path: Path) -> dict[str, DefaultCollection]:
    with open(path) as f:
        data = yaml.safe_load(f)
    result: dict[str, DefaultCollection] = {}
    for item in data.get("default_collections", []):
        col = DefaultCollection(
            name=item["name"],
            kind=CollectionKind(item.get("kind", "program")),
            resources=[_parse_resource(r) for r in item.get("resources", [])],
        )
        result[col.name.lower()] = col
    return result


def _parse_user_collection_item(raw: dict) -> UserCollectionItem:
    additional = []
    for r in raw.get("additional_resources", []):
        # path in user yaml can be a plain string
        path_raw = r.get("path")
        if isinstance(path_raw, str):
            path_spec = PathSpec(windows=path_raw, linux=path_raw, macos=path_raw)
        else:
            path_spec = _parse_path_spec(path_raw)
        additional.append(Resource(
            name=r["name"],
            path=path_spec,
            files=r.get("files", []),
            folders=r.get("folders", []),
        ))
    excl = [ProviderType(p) for p in raw.get("exclude_providers", [])]
    return UserCollectionItem(
        name=raw["name"],
        additional_resources=additional,
        exclude_providers=excl,
    )


def load_profile(path: Path) -> Profile:
    with open(path) as f:
        data = yaml.safe_load(f)
    p = data["profile"]
    policy_raw = p.get("backup_policy", {})
    policy = BackupPolicy(
        programs=[ProviderType(x) for x in policy_raw.get("programs", {}).get("providers", [])],
        games=[ProviderType(x) for x in policy_raw.get("games", {}).get("providers", [])],
    )
    programs = [_parse_user_collection_item(x) for x in p.get("collections", {}).get("programs", [])]
    games = [_parse_user_collection_item(x) for x in p.get("collections", {}).get("games", [])]
    return Profile(
        name=p["name"],
        description=p.get("description", ""),
        os=OS(p.get("os", "linux")),
        providers=[ProviderType(x) for x in p.get("providers", [])],
        backup_policy=policy,
        programs=programs,
        games=games,
    )


def save_profile(profile: Profile, path: Path) -> None:
    def _resource_to_dict(r: Resource) -> dict:
        d: dict = {"name": r.name, "path": {
            "windows": r.path.windows,
            "linux": r.path.linux,
            "macos": r.path.macos,
        }}
        if r.files:
            d["files"] = r.files
        if r.folders:
            d["folders"] = r.folders
        return d

    def _item_to_dict(item: UserCollectionItem) -> dict:
        d: dict = {"name": item.name}
        if item.additional_resources:
            d["additional_resources"] = [_resource_to_dict(r) for r in item.additional_resources]
        if item.exclude_providers:
            d["exclude_providers"] = [p.value for p in item.exclude_providers]
        return d

    data = {
        "profile": {
            "name": profile.name,
            "description": profile.description,
            "os": profile.os.value,
            "providers": [p.value for p in profile.providers],
            "backup_policy": {
                "programs": {"providers": [p.value for p in profile.backup_policy.programs]},
                "games": {"providers": [p.value for p in profile.backup_policy.games]},
            },
            "collections": {
                "programs": [_item_to_dict(i) for i in profile.programs],
                "games": [_item_to_dict(i) for i in profile.games],
            },
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def new_profile(name: str, os_name: str) -> Profile:
    return Profile(
        name=name,
        description="",
        os=OS(os_name),
        providers=[],
        backup_policy=BackupPolicy(),
        programs=[],
        games=[],
    )
