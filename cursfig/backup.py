"""Backup and restore engine."""
from __future__ import annotations
import shutil
import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Protocol, Iterator
from .models import Profile, ProviderType
from .scanner import collect_backup_files, ScanResult


# ──────────────────────────────────────────────
# Provider Protocol
# ──────────────────────────────────────────────

class Provider(Protocol):
    name: str

    def upload(self, local_path: Path, remote_name: str) -> str:
        """Upload file; return remote identifier/URL."""
        ...

    def download(self, remote_name: str, local_path: Path) -> None:
        """Download remote_name to local_path."""
        ...

    def list_backups(self) -> list[dict]:
        """Return list of backup metadata dicts."""
        ...

    def test_connection(self) -> bool:
        ...


# ──────────────────────────────────────────────
# Local Provider
# ──────────────────────────────────────────────

class LocalProvider:
    name = "local"

    def __init__(self, backup_dir: str):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: Path, remote_name: str) -> str:
        dest = self.backup_dir / remote_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if local_path.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(local_path, dest)
        else:
            shutil.copy2(local_path, dest)
        return str(dest)

    def download(self, remote_name: str, local_path: Path) -> None:
        src = self.backup_dir / remote_name
        if not src.exists():
            raise FileNotFoundError(f"Backup not found: {remote_name}")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if local_path.exists():
                shutil.rmtree(local_path)
            shutil.copytree(src, local_path)
        else:
            shutil.copy2(src, local_path)

    def list_backups(self) -> list[dict]:
        meta_file = self.backup_dir / "manifest.json"
        if meta_file.exists():
            with open(meta_file) as f:
                return json.load(f)
        return []

    def save_manifest(self, manifest: dict) -> None:
        meta_file = self.backup_dir / "manifest.json"
        existing = self.list_backups()
        existing.append(manifest)
        with open(meta_file, "w") as f:
            json.dump(existing, f, indent=2, default=str)

    def test_connection(self) -> bool:
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False


# ──────────────────────────────────────────────
# GitHub Provider (stub - requires PyGithub)
# ──────────────────────────────────────────────

class GitHubProvider:
    name = "github"

    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo_name = repo
        self._repo = None

    def _get_repo(self):
        if self._repo is None:
            try:
                from github import Github
                g = Github(self.token)
                self._repo = g.get_repo(self.repo_name)
            except ImportError:
                raise RuntimeError("PyGithub not installed. Run: pip install PyGithub")
        return self._repo

    def upload(self, local_path: Path, remote_name: str) -> str:
        repo = self._get_repo()
        if local_path.is_dir():
            # zip it first
            zip_path = local_path.with_suffix(".zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fp in local_path.rglob("*"):
                    zf.write(fp, fp.relative_to(local_path.parent))
            content = zip_path.read_bytes()
            rname = remote_name + ".zip"
            zip_path.unlink()
        else:
            content = local_path.read_bytes()
            rname = remote_name

        try:
            existing = repo.get_contents(rname)
            repo.update_file(rname, f"cursfig backup {datetime.now().isoformat()}", content, existing.sha)
        except Exception:
            repo.create_file(rname, f"cursfig backup {datetime.now().isoformat()}", content)
        return f"github://{self.repo_name}/{rname}"

    def download(self, remote_name: str, local_path: Path) -> None:
        repo = self._get_repo()
        content = repo.get_contents(remote_name)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content.decoded_content)

    def list_backups(self) -> list[dict]:
        try:
            repo = self._get_repo()
            commits = list(repo.get_commits())[:20]
            return [{"sha": c.sha[:7], "message": c.commit.message, "date": str(c.commit.author.date)} for c in commits]
        except Exception:
            return []

    def test_connection(self) -> bool:
        try:
            self._get_repo()
            return True
        except Exception:
            return False


# ──────────────────────────────────────────────
# Google Drive Provider (stub)
# ──────────────────────────────────────────────

class GoogleDriveProvider:
    name = "google_drive"

    def __init__(self, credentials_path: str, folder_id: str = ""):
        self.credentials_path = credentials_path
        self.folder_id = folder_id
        self._service = None

    def _get_service(self):
        if self._service is None:
            try:
                from googleapiclient.discovery import build
                from google.oauth2.credentials import Credentials
                creds = Credentials.from_authorized_user_file(self.credentials_path)
                self._service = build("drive", "v3", credentials=creds)
            except ImportError:
                raise RuntimeError("google-api-python-client not installed.")
        return self._service

    def upload(self, local_path: Path, remote_name: str) -> str:
        from googleapiclient.http import MediaFileUpload
        service = self._get_service()
        meta = {"name": remote_name.replace("/", "_")}
        if self.folder_id:
            meta["parents"] = [self.folder_id]
        media = MediaFileUpload(str(local_path))
        f = service.files().create(body=meta, media_body=media, fields="id").execute()
        return f"gdrive://{f['id']}"

    def download(self, remote_name: str, local_path: Path) -> None:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        service = self._get_service()
        results = service.files().list(q=f"name='{remote_name}'", fields="files(id,name)").execute()
        files = results.get("files", [])
        if not files:
            raise FileNotFoundError(f"Not found on Drive: {remote_name}")
        fid = files[0]["id"]
        req = service.files().get_media(fileId=fid)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(buf.getvalue())

    def list_backups(self) -> list[dict]:
        try:
            service = self._get_service()
            q = f"'{self.folder_id}' in parents" if self.folder_id else ""
            results = service.files().list(q=q, fields="files(id,name,modifiedTime)").execute()
            return results.get("files", [])
        except Exception:
            return []

    def test_connection(self) -> bool:
        try:
            self._get_service()
            return True
        except Exception:
            return False


# ──────────────────────────────────────────────
# Backup / Restore Engine
# ──────────────────────────────────────────────

def build_provider(provider_type: ProviderType, config: dict) -> Provider:
    if provider_type == ProviderType.LOCAL:
        return LocalProvider(config.get("path", "./cursfig_backup"))
    elif provider_type == ProviderType.GITHUB:
        return GitHubProvider(config["token"], config["repo"])
    elif provider_type == ProviderType.GOOGLE_DRIVE:
        return GoogleDriveProvider(config["credentials"], config.get("folder_id", ""))
    raise ValueError(f"Unknown provider: {provider_type}")


def backup_profile(
    profile: Profile,
    defaults: dict,
    providers: dict[ProviderType, Provider],
    progress_cb=None,
) -> dict[str, list[str]]:
    """
    Backup all files in the profile using configured providers.
    Returns {provider_name: [remote_ids]} and calls progress_cb(msg) if provided.
    """
    files = collect_backup_files(profile, defaults)
    results: dict[str, list[str]] = {}

    def _log(msg: str):
        if progress_cb:
            progress_cb(msg)

    for item_name, rel_name, abs_path in files:
        remote_name = f"{profile.name}/{item_name}/{rel_name}"

        # Determine which providers apply
        for ptype, provider in providers.items():
            # Determine kind
            from .models import CollectionKind
            kind = CollectionKind.PROGRAM
            for g in profile.games:
                if g.name == item_name:
                    kind = CollectionKind.GAME
                    break

            policy_providers = (
                profile.backup_policy.games if kind == CollectionKind.GAME
                else profile.backup_policy.programs
            )

            # Skip if not in policy
            if ptype not in policy_providers:
                continue

            # Check exclusions
            item_obj = next((x for x in (profile.programs + profile.games) if x.name == item_name), None)
            if item_obj and ptype in item_obj.exclude_providers:
                _log(f"  Skipping {item_name} on {ptype.value} (excluded)")
                continue

            try:
                _log(f"  Uploading {rel_name} → {ptype.value}...")
                rid = provider.upload(abs_path, remote_name)
                results.setdefault(ptype.value, []).append(rid)
                _log(f"  ✓ {rel_name} → {rid}")
            except Exception as e:
                _log(f"  ✗ Failed {rel_name} on {ptype.value}: {e}")

    return results


def check_restore_conflicts(
    profile: Profile,
    defaults: dict,
) -> list[tuple[str, Path]]:
    """Return list of (name, path) that already exist and would be overwritten."""
    conflicts = []
    files = collect_backup_files(profile, defaults)
    for item_name, rel_name, abs_path in files:
        if abs_path.exists():
            conflicts.append((rel_name, abs_path))
    return conflicts


def restore_profile(
    profile: Profile,
    defaults: dict,
    provider: Provider,
    force: bool = False,
    progress_cb=None,
) -> None:
    """Restore all files from a provider."""
    files = collect_backup_files(profile, defaults)

    def _log(msg: str):
        if progress_cb:
            progress_cb(msg)

    for item_name, rel_name, abs_path in files:
        remote_name = f"{profile.name}/{item_name}/{rel_name}"
        if abs_path.exists() and not force:
            _log(f"  Skipping {rel_name} (exists, use force to override)")
            continue
        try:
            _log(f"  Restoring {rel_name}...")
            provider.download(remote_name, abs_path)
            _log(f"  ✓ Restored → {abs_path}")
        except FileNotFoundError:
            _log(f"  ✗ Not found in backup: {remote_name}")
        except Exception as e:
            _log(f"  ✗ Error restoring {rel_name}: {e}")
