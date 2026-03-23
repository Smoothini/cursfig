"""Tests for cursfig — runs without network or pip extras."""
from __future__ import annotations
import sys
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Make sure the package is importable from repo root
sys.path.insert(0, str(Path(__file__).parent))

from cursfig.models import (
    OS, ProviderType, CollectionKind,
    PathSpec, Resource, DefaultCollection,
    UserCollectionItem, BackupPolicy, Profile, ScanResult,
)
from cursfig.loader import (
    load_default_collections, load_profile, save_profile, new_profile,
)
from cursfig.scanner import scan_profile, collect_backup_files
from cursfig.backup import LocalProvider, check_restore_conflicts


DEFAULTS_YAML = Path(__file__).parent / "data" / "default_collections.yaml"
EXAMPLE_USER_YAML = Path(__file__).parent / "data" / "user.example.yaml"


# ─────────────────────────────────────────────────────
# Model tests
# ─────────────────────────────────────────────────────

class TestModels(unittest.TestCase):

    def test_pathspec_for_os(self):
        ps = PathSpec(windows="C:\\win", linux="/lin", macos="/mac")
        self.assertEqual(ps.for_os(OS.WINDOWS), "C:\\win")
        self.assertEqual(ps.for_os(OS.LINUX), "/lin")
        self.assertEqual(ps.for_os(OS.MACOS), "/mac")

    def test_scan_result_counts(self):
        r = ScanResult(
            collection_name="NeoVim",
            kind=CollectionKind.PROGRAM,
            resource_name="Main config",
            path="/home/x/.config/nvim",
            files=[("init.vim", True), ("missing.lua", False)],
            folders=[("pack", True)],
        )
        self.assertEqual(r.found_count, 2)
        self.assertEqual(r.missing_count, 1)
        self.assertTrue(r.has_any)

    def test_scan_result_all_missing(self):
        r = ScanResult("X", CollectionKind.GAME, "save", "/tmp",
                       files=[("a", False)], folders=[])
        self.assertFalse(r.has_any)


# ─────────────────────────────────────────────────────
# Loader tests
# ─────────────────────────────────────────────────────

class TestLoader(unittest.TestCase):

    def test_load_defaults(self):
        defaults = load_default_collections(DEFAULTS_YAML)
        self.assertIn("neovim", defaults)
        self.assertIn("wezterm", defaults)
        self.assertIn("minecraft", defaults)
        self.assertIn("supermeatboy", defaults)

    def test_defaults_kind(self):
        defaults = load_default_collections(DEFAULTS_YAML)
        self.assertEqual(defaults["minecraft"].kind, CollectionKind.GAME)
        self.assertEqual(defaults["neovim"].kind, CollectionKind.PROGRAM)

    def test_defaults_resources(self):
        defaults = load_default_collections(DEFAULTS_YAML)
        nvim = defaults["neovim"]
        self.assertTrue(len(nvim.resources) > 0)
        main = nvim.resources[0]
        self.assertIn("init.vim", main.files)

    def test_load_example_user(self):
        p = load_profile(EXAMPLE_USER_YAML)
        self.assertEqual(p.name, "Default")
        self.assertEqual(p.os, OS.WINDOWS)
        self.assertIn(ProviderType.GITHUB, p.providers)
        self.assertIn(ProviderType.GOOGLE_DRIVE, p.providers)
        program_names = [x.name for x in p.programs]
        self.assertIn("WezTerm", program_names)
        self.assertIn("NeoVim", program_names)
        game_names = [x.name for x in p.games]
        self.assertIn("Minecraft", game_names)
        self.assertIn("Supermeatboy", game_names)

    def test_backup_policy(self):
        p = load_profile(EXAMPLE_USER_YAML)
        self.assertIn(ProviderType.GITHUB, p.backup_policy.programs)
        self.assertIn(ProviderType.GOOGLE_DRIVE, p.backup_policy.games)

    def test_exclude_providers(self):
        p = load_profile(EXAMPLE_USER_YAML)
        mc = next(x for x in p.games if x.name == "Minecraft")
        self.assertIn(ProviderType.GITHUB, mc.exclude_providers)

    def test_additional_resources(self):
        p = load_profile(EXAMPLE_USER_YAML)
        nvim = next(x for x in p.programs if x.name == "NeoVim")
        self.assertEqual(len(nvim.additional_resources), 1)
        self.assertIn("randomfile.lua", nvim.additional_resources[0].files)

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as td:
            p = new_profile("testprofile", "linux")
            p.description = "test desc"
            p.providers = [ProviderType.LOCAL]
            p.backup_policy.programs = [ProviderType.LOCAL]
            p.programs.append(UserCollectionItem(name="NeoVim"))
            p.games.append(UserCollectionItem(name="Minecraft"))
            path = Path(td) / "test.yaml"
            save_profile(p, path)
            p2 = load_profile(path)
            self.assertEqual(p2.name, "testprofile")
            self.assertEqual(p2.os, OS.LINUX)
            self.assertEqual(p2.description, "test desc")
            self.assertEqual([x.name for x in p2.programs], ["NeoVim"])
            self.assertEqual([x.name for x in p2.games], ["Minecraft"])
            self.assertIn(ProviderType.LOCAL, p2.providers)
            self.assertIn(ProviderType.LOCAL, p2.backup_policy.programs)

    def test_new_profile_defaults(self):
        p = new_profile("empty", "macos")
        self.assertEqual(p.name, "empty")
        self.assertEqual(p.os, OS.MACOS)
        self.assertEqual(p.programs, [])
        self.assertEqual(p.games, [])
        self.assertEqual(p.providers, [])


# ─────────────────────────────────────────────────────
# Scanner tests
# ─────────────────────────────────────────────────────

class TestScanner(unittest.TestCase):

    def setUp(self):
        self.defaults = load_default_collections(DEFAULTS_YAML)
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _profile_with_local_files(self) -> tuple[Profile, Path, Path]:
        """Create a profile pointing at tmpdir with a real file."""
        config_dir = Path(self.tmpdir) / "nvim"
        config_dir.mkdir()
        init_file = config_dir / "init.vim"
        init_file.write_text("; test config")

        p = new_profile("scan_test", "linux")
        # Override NeoVim path to our tmpdir
        item = UserCollectionItem(
            name="NeoVim",
            additional_resources=[
                Resource(
                    name="test resource",
                    path=PathSpec(linux=str(config_dir), windows=str(config_dir), macos=str(config_dir)),
                    files=["init.vim", "missing.lua"],
                )
            ],
        )
        # Remove from defaults to avoid path confusion — use fresh item only
        p.programs.append(item)
        return p, config_dir, init_file

    def test_scan_finds_existing_file(self):
        p, config_dir, init_file = self._profile_with_local_files()
        # Use empty defaults so only additional_resources apply
        results = scan_profile(p, {})
        self.assertTrue(len(results) > 0)
        # Find the result for our resource
        r = next((x for x in results if x.resource_name == "test resource"), None)
        self.assertIsNotNone(r)
        found_files = dict(r.files)
        self.assertTrue(found_files.get("init.vim"), "init.vim should be found")
        self.assertFalse(found_files.get("missing.lua"), "missing.lua should not be found")

    def test_scan_collects_folders(self):
        folder = Path(self.tmpdir) / "pack"
        folder.mkdir()
        p = new_profile("folder_test", "linux")
        item = UserCollectionItem(
            name="NeoVim",
            additional_resources=[
                Resource(
                    name="folders",
                    path=PathSpec(linux=self.tmpdir, windows=self.tmpdir, macos=self.tmpdir),
                    files=[],
                    folders=["pack", "missing_folder"],
                )
            ],
        )
        p.programs.append(item)
        results = scan_profile(p, {})
        r = next(x for x in results if x.resource_name == "folders")
        folder_map = dict(r.folders)
        self.assertTrue(folder_map["pack"])
        self.assertFalse(folder_map["missing_folder"])

    def test_scan_uses_defaults(self):
        """If item only has a name, scanner should pick up default collection resources."""
        p = new_profile("defaults_test", "linux")
        p.programs.append(UserCollectionItem(name="NeoVim"))
        results = scan_profile(p, self.defaults)
        names = [r.resource_name for r in results]
        self.assertIn("Main config", names)

    def test_collect_backup_files_only_existing(self):
        p, config_dir, init_file = self._profile_with_local_files()
        files = collect_backup_files(p, {})
        paths = [abs_p for _, _, abs_p in files]
        self.assertIn(init_file, paths)
        # missing.lua should NOT be in the list
        missing = config_dir / "missing.lua"
        self.assertNotIn(missing, paths)

    def test_windows_env_var_expansion(self):
        """Verify %VAR% placeholders are expanded via os.environ."""
        os.environ["CURSFIG_TEST_DIR"] = self.tmpdir
        p = new_profile("wintest", "windows")
        item = UserCollectionItem(
            name="TestApp",
            additional_resources=[
                Resource(
                    name="cfg",
                    path=PathSpec(
                        windows="%CURSFIG_TEST_DIR%",
                        linux=self.tmpdir,
                        macos=self.tmpdir,
                    ),
                    files=["myfile.txt"],
                )
            ],
        )
        p.programs.append(item)
        (Path(self.tmpdir) / "myfile.txt").write_text("hello")
        results = scan_profile(p, {})
        r = next(x for x in results if x.resource_name == "cfg")
        found = dict(r.files)
        self.assertTrue(found["myfile.txt"])


# ─────────────────────────────────────────────────────
# Backup / LocalProvider tests
# ─────────────────────────────────────────────────────

class TestLocalProvider(unittest.TestCase):

    def setUp(self):
        self.src = tempfile.mkdtemp()
        self.dst = tempfile.mkdtemp()
        self.provider = LocalProvider(self.dst)

    def tearDown(self):
        shutil.rmtree(self.src)
        shutil.rmtree(self.dst)

    def test_upload_file(self):
        f = Path(self.src) / "config.lua"
        f.write_text("return {}")
        rid = self.provider.upload(f, "NeoVim/config.lua")
        self.assertTrue(Path(rid).exists())
        self.assertEqual(Path(rid).read_text(), "return {}")

    def test_download_file(self):
        f = Path(self.src) / "init.vim"
        f.write_text("; original")
        self.provider.upload(f, "NeoVim/init.vim")
        dest = Path(self.src) / "restored.vim"
        self.provider.download("NeoVim/init.vim", dest)
        self.assertEqual(dest.read_text(), "; original")

    def test_upload_missing_raises(self):
        with self.assertRaises(Exception):
            self.provider.download("does/not/exist", Path(self.src) / "x")

    def test_upload_folder(self):
        folder = Path(self.src) / "pack"
        folder.mkdir()
        (folder / "plugin.lua").write_text("-- plugin")
        self.provider.upload(folder, "NeoVim/pack")
        restored = Path(self.dst) / "NeoVim" / "pack"
        self.assertTrue(restored.is_dir())
        self.assertTrue((restored / "plugin.lua").exists())

    def test_test_connection(self):
        self.assertTrue(self.provider.test_connection())

    def test_save_and_list_manifest(self):
        self.provider.save_manifest({"profile": "test", "date": "2026-01-01", "files": 3})
        backups = self.provider.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0]["profile"], "test")


class TestBackupRestore(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.backup_dir = tempfile.mkdtemp()
        self.defaults = load_default_collections(DEFAULTS_YAML)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        shutil.rmtree(self.backup_dir)

    def _make_profile_with_files(self):
        config_dir = Path(self.tmpdir) / "wezterm"
        config_dir.mkdir()
        wezfile = config_dir / ".wezterm.lua"
        wezfile.write_text("-- wezterm config")

        p = new_profile("bktest", "linux")
        p.providers = [ProviderType.LOCAL]
        p.backup_policy.programs = [ProviderType.LOCAL]
        item = UserCollectionItem(
            name="WezTerm",
            additional_resources=[
                Resource(
                    name="main config",
                    path=PathSpec(linux=str(config_dir), windows=str(config_dir), macos=str(config_dir)),
                    files=[".wezterm.lua"],
                )
            ],
        )
        p.programs.append(item)
        return p, wezfile

    def test_full_backup_and_restore(self):
        from cursfig.backup import backup_profile, restore_profile
        p, wezfile = self._make_profile_with_files()
        provider = LocalProvider(self.backup_dir)
        logs = []

        backup_profile(p, {}, {ProviderType.LOCAL: provider}, progress_cb=logs.append)

        # Verify file was uploaded
        remote = Path(self.backup_dir) / "bktest" / "WezTerm" / ".wezterm.lua"
        self.assertTrue(remote.exists(), f"Remote file not found at {remote}")
        self.assertEqual(remote.read_text(), "-- wezterm config")

        # Modify local file
        wezfile.write_text("-- CHANGED")

        # Restore with force
        restore_profile(p, {}, provider, force=True, progress_cb=logs.append)
        self.assertEqual(wezfile.read_text(), "-- wezterm config")

    def test_conflict_detection(self):
        p, wezfile = self._make_profile_with_files()
        conflicts = check_restore_conflicts(p, {})
        conflict_names = [n for n, _ in conflicts]
        self.assertIn(".wezterm.lua", conflict_names)

    def test_conflict_detection_missing_file(self):
        p = new_profile("empty_bk", "linux")
        item = UserCollectionItem(
            name="X",
            additional_resources=[
                Resource(
                    name="cfg",
                    path=PathSpec(linux="/nonexistent/path", windows="/nonexistent/path", macos="/nonexistent/path"),
                    files=["x.cfg"],
                )
            ],
        )
        p.programs.append(item)
        conflicts = check_restore_conflicts(p, {})
        self.assertEqual(conflicts, [])

    def test_backup_respects_exclude_providers(self):
        from cursfig.backup import backup_profile
        p, wezfile = self._make_profile_with_files()
        # Exclude local from the item
        p.programs[0].exclude_providers = [ProviderType.LOCAL]
        provider = LocalProvider(self.backup_dir)
        logs = []
        backup_profile(p, {}, {ProviderType.LOCAL: provider}, progress_cb=logs.append)
        remote = Path(self.backup_dir) / "bktest" / "WezTerm" / ".wezterm.lua"
        self.assertFalse(remote.exists(), "Should not have backed up excluded item")

    def test_backup_skips_missing_files(self):
        from cursfig.backup import backup_profile
        p = new_profile("nomatch", "linux")
        p.providers = [ProviderType.LOCAL]
        p.backup_policy.programs = [ProviderType.LOCAL]
        item = UserCollectionItem(
            name="Ghost",
            additional_resources=[
                Resource(
                    name="cfg",
                    path=PathSpec(linux="/does/not/exist", windows="/does/not/exist", macos="/does/not/exist"),
                    files=["ghost.cfg"],
                )
            ],
        )
        p.programs.append(item)
        provider = LocalProvider(self.backup_dir)
        logs = []
        backup_profile(p, {}, {ProviderType.LOCAL: provider}, progress_cb=logs.append)
        # Should complete without errors, just nothing uploaded
        remote = Path(self.backup_dir) / "nomatch" / "Ghost" / "ghost.cfg"
        self.assertFalse(remote.exists())


# ─────────────────────────────────────────────────────
# Config / profile registry tests
# ─────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):

    def setUp(self):
        self._orig_home = os.environ.get("HOME")
        self._tmpdir = tempfile.mkdtemp()
        os.environ["HOME"] = self._tmpdir
        # Reset module-level paths
        import cursfig.config as cfg_mod
        cfg_mod.APP_DIR = Path(self._tmpdir) / ".cursfig"
        cfg_mod.CONFIG_FILE = cfg_mod.APP_DIR / "config.json"
        cfg_mod.PROFILES_DIR = cfg_mod.APP_DIR / "profiles"

    def tearDown(self):
        shutil.rmtree(self._tmpdir)
        if self._orig_home:
            os.environ["HOME"] = self._orig_home

    def test_list_profiles_empty(self):
        import cursfig.config as cfg_mod
        self.assertEqual(cfg_mod.list_profiles(), [])

    def test_save_and_list_profile(self):
        import cursfig.config as cfg_mod
        p = new_profile("myprofile", "linux")
        save_profile(p, cfg_mod.profile_path("myprofile"))
        profiles = cfg_mod.list_profiles()
        self.assertIn("myprofile", profiles)

    def test_active_profile(self):
        import cursfig.config as cfg_mod
        p = new_profile("active_test", "linux")
        save_profile(p, cfg_mod.profile_path("active_test"))
        cfg_mod.set_active_profile("active_test")
        self.assertEqual(cfg_mod.get_active_profile_name(), "active_test")

    def test_provider_config(self):
        import cursfig.config as cfg_mod
        cfg_mod.set_provider_config("local", {"path": "/tmp/backup"})
        cfg = cfg_mod.get_provider_config("local")
        self.assertEqual(cfg["path"], "/tmp/backup")

    def test_provider_config_missing_returns_empty(self):
        import cursfig.config as cfg_mod
        cfg = cfg_mod.get_provider_config("nonexistent")
        self.assertEqual(cfg, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
