"""Data models for cursfig."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class OS(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"


class ProviderType(str, Enum):
    GITHUB = "github"
    GOOGLE_DRIVE = "google_drive"
    LOCAL = "local"


class CollectionKind(str, Enum):
    PROGRAM = "program"
    GAME = "game"


@dataclass
class PathSpec:
    windows: str = "~"
    linux: str = "~"
    macos: str = "~"

    def for_os(self, os: OS) -> str:
        return getattr(self, os.value, "~")


@dataclass
class Resource:
    name: str
    path: PathSpec
    files: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)


@dataclass
class DefaultCollection:
    name: str
    kind: CollectionKind
    resources: list[Resource] = field(default_factory=list)


@dataclass
class UserCollectionItem:
    name: str
    additional_resources: list[Resource] = field(default_factory=list)
    exclude_providers: list[ProviderType] = field(default_factory=list)


@dataclass
class BackupPolicy:
    programs: list[ProviderType] = field(default_factory=list)
    games: list[ProviderType] = field(default_factory=list)


@dataclass
class Profile:
    name: str
    description: str
    os: OS
    providers: list[ProviderType] = field(default_factory=list)
    backup_policy: BackupPolicy = field(default_factory=BackupPolicy)
    programs: list[UserCollectionItem] = field(default_factory=list)
    games: list[UserCollectionItem] = field(default_factory=list)


@dataclass
class ScanResult:
    collection_name: str
    kind: CollectionKind
    resource_name: str
    path: str
    files: list[tuple[str, bool]]   # (filename, exists)
    folders: list[tuple[str, bool]] # (foldername, exists)

    @property
    def has_any(self) -> bool:
        return any(e for _, e in self.files) or any(e for _, e in self.folders)

    @property
    def missing_count(self) -> int:
        return sum(1 for _, e in self.files if not e) + sum(1 for _, e in self.folders if not e)

    @property
    def found_count(self) -> int:
        return sum(1 for _, e in self.files if e) + sum(1 for _, e in self.folders if e)
