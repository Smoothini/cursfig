"""TUI for cursfig using Textual."""
from __future__ import annotations
from pathlib import Path
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, Button, Input, Label,
    ListView, ListItem, Select, Checkbox, TabbedContent, TabPane,
    DataTable, Log, MarkdownViewer,
)
from textual.screen import Screen, ModalScreen
from textual.reactive import reactive
from textual import work
from rich.text import Text
from rich.table import Table

from .config import (
    load_app_config, save_app_config, list_profiles, profile_path,
    set_active_profile, get_active_profile_name, set_provider_config,
    get_provider_config, find_default_collections,
)
from .loader import load_default_collections, load_profile, save_profile, new_profile
from .scanner import scan_profile
from .models import (
    OS, ProviderType, CollectionKind, Profile,
    UserCollectionItem, BackupPolicy,
)
from .backup import build_provider, backup_profile, check_restore_conflicts, restore_profile


# ─────────────────────────────────────────────────────
# Dialogs
# ─────────────────────────────────────────────────────

class NewProfileDialog(ModalScreen[tuple[str, str] | None]):
    CSS = """
    NewProfileDialog {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #dialog Label { margin-bottom: 1; }
    #dialog Input { margin-bottom: 1; }
    #dialog Select { margin-bottom: 1; }
    #btns { margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("Create New Profile", classes="title")
            yield Label("Profile name:")
            yield Input(placeholder="my-profile", id="pname")
            yield Label("Operating System:")
            yield Select(
                [(o.value, o.value) for o in OS],
                value=OS.LINUX.value,
                id="pos",
            )
            with Horizontal(id="btns"):
                yield Button("Create", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            name = self.query_one("#pname", Input).value.strip()
            os_val = self.query_one("#pos", Select).value
            if name:
                self.dismiss((name, os_val))
            else:
                self.query_one("#pname", Input).border_title = "Required!"
        else:
            self.dismiss(None)


class AddCollectionDialog(ModalScreen[tuple[str, str] | None]):
    CSS = """
    AddCollectionDialog {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #dialog Label { margin-bottom: 1; }
    #dialog Input { margin-bottom: 1; }
    #btns { margin-top: 1; }
    """

    def __init__(self, known: list[str], kind: str):
        super().__init__()
        self.known = known
        self.kind = kind

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(f"Add {self.kind.capitalize()}")
            yield Label("Name (matches default collections if available):")
            yield Input(placeholder="e.g. NeoVim", id="cname")
            if self.known:
                yield Label(f"Known {self.kind}s: " + ", ".join(self.known))
            with Horizontal(id="btns"):
                yield Button("Add", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            name = self.query_one("#cname", Input).value.strip()
            if name:
                self.dismiss((name, self.kind))
            else:
                self.query_one("#cname", Input).add_class("error")
        else:
            self.dismiss(None)


class ProviderSetupDialog(ModalScreen[dict | None]):
    CSS = """
    ProviderSetupDialog { align: center middle; }
    #dialog {
        width: 70;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #dialog Label { margin-bottom: 1; }
    #dialog Input { margin-bottom: 1; }
    #btns { margin-top: 1; }
    """

    def __init__(self, provider: ProviderType):
        super().__init__()
        self.provider = provider

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(f"Configure {self.provider.value}")
            if self.provider == ProviderType.LOCAL:
                yield Label("Backup directory path:")
                yield Input(placeholder="/path/to/backup", id="field1")
            elif self.provider == ProviderType.GITHUB:
                yield Label("GitHub token:")
                yield Input(placeholder="ghp_...", password=True, id="field1")
                yield Label("Repository (user/repo):")
                yield Input(placeholder="username/my-configs", id="field2")
            elif self.provider == ProviderType.GOOGLE_DRIVE:
                yield Label("Credentials JSON path:")
                yield Input(placeholder="~/.config/gdrive_creds.json", id="field1")
                yield Label("Folder ID (optional):")
                yield Input(placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs", id="field2")
            with Horizontal(id="btns"):
                yield Button("Save", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        f1 = self.query_one("#field1", Input).value.strip() if self.query("#field1") else ""
        f2_widgets = self.query("#field2")
        f2 = f2_widgets.first(Input).value.strip() if f2_widgets else ""

        if self.provider == ProviderType.LOCAL:
            self.dismiss({"path": f1})
        elif self.provider == ProviderType.GITHUB:
            self.dismiss({"token": f1, "repo": f2})
        elif self.provider == ProviderType.GOOGLE_DRIVE:
            self.dismiss({"credentials": f1, "folder_id": f2})


class ConfirmDialog(ModalScreen[bool]):
    CSS = """
    ConfirmDialog { align: center middle; }
    #dialog {
        width: 60;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #btns { margin-top: 1; }
    """

    def __init__(self, message: str, title: str = "Confirm"):
        super().__init__()
        self.message = message
        self.title_text = title

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(f"[bold]{self.title_text}[/bold]")
            yield Static(self.message)
            with Horizontal(id="btns"):
                yield Button("Yes", variant="warning", id="yes")
                yield Button("No", variant="primary", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


# ─────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────

class CursfigApp(App):
    CSS = """
    Screen { background: $background; }

    Header { background: $primary-darken-2; }

    .sidebar {
        width: 24;
        border-right: solid $primary-darken-2;
        background: $surface;
    }

    .sidebar-title {
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        text-align: center;
        text-style: bold;
    }

    .main-area { width: 1fr; }

    #profile-list { height: 1fr; }

    .section-title {
        background: $accent-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
        margin-top: 1;
    }

    #log-output {
        height: 1fr;
        border: solid $primary-darken-2;
        margin: 1;
    }

    .action-bar {
        height: 3;
        padding: 0 1;
        background: $surface-darken-1;
    }

    .action-bar Button {
        margin-right: 1;
    }

    DataTable {
        height: 1fr;
        margin: 1;
    }

    .stat-ok { color: $success; }
    .stat-miss { color: $error; }
    .stat-warn { color: $warning; }

    TabbedContent { height: 1fr; }

    TabPane { padding: 1; }

    .collection-item {
        height: 3;
        padding: 0 1;
        border-bottom: solid $primary-darken-2;
    }

    .no-profile {
        align: center middle;
        color: $text-muted;
        text-style: italic;
    }

    .provider-badge {
        margin-right: 1;
        padding: 0 1;
        background: $primary-darken-2;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_profile", "New Profile"),
        Binding("s", "scan", "Scan"),
        Binding("b", "backup", "Backup"),
        Binding("r", "restore", "Restore"),
        Binding("?", "help", "Help"),
    ]

    active_profile_name: reactive[str | None] = reactive(None)

    def __init__(self):
        super().__init__()
        self.defaults: dict = {}
        self.current_profile: Profile | None = None
        self._load_defaults()

    def _load_defaults(self):
        try:
            p = find_default_collections()
            self.defaults = load_default_collections(p)
        except Exception as e:
            self.defaults = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            # Sidebar
            with Vertical(classes="sidebar"):
                yield Static("cursfig", classes="sidebar-title")
                yield Static("Profiles", classes="section-title")
                yield ListView(id="profile-list")
                with Horizontal(classes="action-bar"):
                    yield Button("+ New", id="btn-new-profile", variant="primary")
                yield Static("Actions", classes="section-title")
                yield Button("Scan",    id="btn-scan",    classes="sidebar-btn")
                yield Button("Backup",  id="btn-backup",  classes="sidebar-btn")
                yield Button("Restore", id="btn-restore", classes="sidebar-btn")
                yield Button("Providers", id="btn-providers", classes="sidebar-btn")

            # Main area
            with Vertical(classes="main-area"):
                with TabbedContent(id="main-tabs"):
                    with TabPane("Profile", id="tab-profile"):
                        with ScrollableContainer():
                            yield Static("[dim]No profile selected[/dim]", id="profile-info")
                    with TabPane("Scan Results", id="tab-scan"):
                        yield DataTable(id="scan-table", cursor_type="row")
                    with TabPane("Log", id="tab-log"):
                        yield Log(id="log-output", auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_profile_list()
        # Init scan table columns
        table = self.query_one("#scan-table", DataTable)
        table.add_columns("Collection", "Resource", "Path", "Found", "Missing")
        # Load active profile
        name = get_active_profile_name()
        if name:
            self._load_profile(name)

    def _refresh_profile_list(self) -> None:
        lv = self.query_one("#profile-list", ListView)
        lv.clear()
        profiles = list_profiles()
        for p in profiles:
            item = ListItem(Label(p), id=f"profile-{p}")
            lv.append(item)

    def _load_profile(self, name: str) -> None:
        try:
            p = load_profile(profile_path(name))
            self.current_profile = p
            self.active_profile_name = name
            set_active_profile(name)
            self._refresh_profile_view()
            self._log(f"Loaded profile: {name}")
        except Exception as e:
            self._log(f"[red]Error loading profile {name}: {e}[/red]")

    def _refresh_profile_view(self) -> None:
        if not self.current_profile:
            return
        p = self.current_profile
        lines = [
            f"[bold cyan]{p.name}[/bold cyan]  [dim]{p.description}[/dim]",
            f"OS: [yellow]{p.os.value}[/yellow]   Providers: " +
            " ".join(f"[blue]{pr.value}[/blue]" for pr in p.providers),
            "",
            f"[bold]Backup Policy[/bold]",
            f"  Programs → {', '.join(x.value for x in p.backup_policy.programs) or 'none'}",
            f"  Games    → {', '.join(x.value for x in p.backup_policy.games) or 'none'}",
            "",
            f"[bold]Programs ({len(p.programs)})[/bold]",
        ]
        for prog in p.programs:
            excl = f"  [dim](excl: {', '.join(x.value for x in prog.exclude_providers)})[/dim]" if prog.exclude_providers else ""
            lines.append(f"  • {prog.name}{excl}")
        lines += ["", f"[bold]Games ({len(p.games)})[/bold]"]
        for game in p.games:
            excl = f"  [dim](excl: {', '.join(x.value for x in game.exclude_providers)})[/dim]" if game.exclude_providers else ""
            lines.append(f"  • {game.name}{excl}")
        lines += [
            "",
            "[dim]Press [bold]A[/bold] to add program, [bold]G[/bold] to add game[/dim]",
        ]
        self.query_one("#profile-info", Static).update("\n".join(lines))

    def _log(self, msg: str) -> None:
        log = self.query_one("#log-output", Log)
        log.write_line(msg)

    # ── Profile list click ──────────────────────
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id and event.item.id.startswith("profile-"):
            name = event.item.id[len("profile-"):]
            self._load_profile(name)

    # ── Button handlers ─────────────────────────
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-new-profile":
            self.action_new_profile()
        elif bid == "btn-scan":
            self.action_scan()
        elif bid == "btn-backup":
            self.action_backup()
        elif bid == "btn-restore":
            self.action_restore()
        elif bid == "btn-providers":
            self._open_providers()

    # ── Actions ─────────────────────────────────
    def action_new_profile(self) -> None:
        def _handle(result):
            if result:
                name, os_val = result
                p = new_profile(name, os_val)
                save_profile(p, profile_path(name))
                self._refresh_profile_list()
                self._load_profile(name)
                self._log(f"Created profile: {name}")
        self.push_screen(NewProfileDialog(), _handle)

    def action_scan(self) -> None:
        if not self.current_profile:
            self._log("[yellow]No profile loaded.[/yellow]")
            return
        self._do_scan()

    @work(thread=True)
    def _do_scan(self) -> None:
        self._log("Scanning...")
        results = scan_profile(self.current_profile, self.defaults)
        table = self.query_one("#scan-table", DataTable)
        self.call_from_thread(table.clear)

        for r in results:
            found = r.found_count
            missing = r.missing_count
            found_str = Text(str(found), style="green") if found else Text("0", style="dim")
            miss_str = Text(str(missing), style="red bold") if missing else Text("0", style="dim")
            self.call_from_thread(
                table.add_row,
                r.collection_name, r.resource_name,
                r.path[:40] + "…" if len(r.path) > 40 else r.path,
                found_str, miss_str,
            )

        total_found = sum(r.found_count for r in results)
        total_miss = sum(r.missing_count for r in results)
        self._log(f"Scan complete. Found: {total_found}, Missing: {total_miss}")
        # Switch to scan tab
        self.call_from_thread(
            self.query_one("#main-tabs", TabbedContent).active.__set__,
            self.query_one("#main-tabs", TabbedContent),
        )

    def action_backup(self) -> None:
        if not self.current_profile:
            self._log("[yellow]No profile loaded.[/yellow]")
            return
        self._do_backup()

    @work(thread=True)
    def _do_backup(self) -> None:
        self._log("Starting backup...")
        app_cfg = load_app_config()
        providers_cfg = app_cfg.get("providers", {})
        providers = {}
        for ptype in self.current_profile.providers:
            cfg = providers_cfg.get(ptype.value, {})
            if not cfg:
                self._log(f"[yellow]Provider {ptype.value} not configured. Skipping.[/yellow]")
                continue
            try:
                providers[ptype] = build_provider(ptype, cfg)
            except Exception as e:
                self._log(f"[red]Failed to init {ptype.value}: {e}[/red]")

        if not providers:
            self._log("[red]No providers configured. Set them up first.[/red]")
            return

        backup_profile(
            self.current_profile, self.defaults, providers,
            progress_cb=self._log,
        )
        self._log("[green]Backup complete.[/green]")

    def action_restore(self) -> None:
        if not self.current_profile:
            self._log("[yellow]No profile loaded.[/yellow]")
            return
        conflicts = check_restore_conflicts(self.current_profile, self.defaults)
        if conflicts:
            msg = f"[yellow]{len(conflicts)} file(s) will be overwritten:[/yellow]\n"
            msg += "\n".join(f"  • {n}" for n, _ in conflicts[:10])
            if len(conflicts) > 10:
                msg += f"\n  … and {len(conflicts)-10} more"
            def _confirmed(yes: bool):
                if yes:
                    self._do_restore(force=True)
            self.push_screen(ConfirmDialog(msg, "Restore will overwrite files"), _confirmed)
        else:
            self._do_restore(force=False)

    @work(thread=True)
    def _do_restore(self, force: bool = False) -> None:
        self._log("Starting restore...")
        app_cfg = load_app_config()
        providers_cfg = app_cfg.get("providers", {})
        # Use first available provider for restore
        for ptype in self.current_profile.providers:
            cfg = providers_cfg.get(ptype.value, {})
            if cfg:
                try:
                    provider = build_provider(ptype, cfg)
                    restore_profile(
                        self.current_profile, self.defaults, provider,
                        force=force, progress_cb=self._log,
                    )
                    self._log("[green]Restore complete.[/green]")
                    return
                except Exception as e:
                    self._log(f"[red]Restore failed on {ptype.value}: {e}[/red]")
        self._log("[red]No usable provider found.[/red]")

    def _open_providers(self) -> None:
        if not self.current_profile:
            self._log("[yellow]Load a profile first.[/yellow]")
            return
        # Show provider selection
        options = [(p.value, p) for p in ProviderType]
        self.push_screen(
            ProviderSelectScreen(self.current_profile),
            self._after_provider_setup,
        )

    def _after_provider_setup(self, result) -> None:
        if result:
            self._log(f"Provider configured.")
            if self.current_profile:
                save_profile(self.current_profile, profile_path(self.active_profile_name))

    def action_help(self) -> None:
        self._log("""
Keys: N=New profile  S=Scan  B=Backup  R=Restore  ?=Help
TUI Navigation: Arrow keys to move, Enter to select, Q to quit
        """.strip())


# ─────────────────────────────────────────────────────
# Provider Setup Screen
# ─────────────────────────────────────────────────────

class ProviderSelectScreen(Screen):
    CSS = """
    ProviderSelectScreen {
        background: $background;
    }
    .prov-btn {
        margin: 1;
        width: 30;
    }
    #title {
        padding: 1;
        text-style: bold;
        background: $primary-darken-2;
    }
    """

    def __init__(self, profile: Profile):
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        yield Static("Configure Providers", id="title")
        yield Static("Select a provider to configure:")
        with Horizontal():
            for pt in ProviderType:
                configured = bool(get_provider_config(pt.value))
                label = f"{'✓ ' if configured else ''}{pt.value}"
                yield Button(label, id=f"prov-{pt.value}", classes="prov-btn",
                             variant="success" if configured else "default")
        yield Button("← Back", id="back", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.dismiss(None)
            return
        if event.button.id and event.button.id.startswith("prov-"):
            ptype_val = event.button.id[5:]
            ptype = ProviderType(ptype_val)

            def _save(cfg: dict | None):
                if cfg:
                    set_provider_config(ptype_val, cfg)
                    # Add to profile providers if not there
                    if ptype not in self.profile.providers:
                        self.profile.providers.append(ptype)
                    self.dismiss(cfg)
            self.app.push_screen(ProviderSetupDialog(ptype), _save)


def run_tui():
    app = CursfigApp()
    app.run()
