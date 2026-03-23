"""CLI interface for cursfig."""
from __future__ import annotations
import sys
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

from .config import (
    list_profiles, profile_path, get_active_profile_name, set_active_profile,
    set_provider_config, get_provider_config, find_default_collections,
)
from .loader import load_default_collections, load_profile, save_profile, new_profile
from .scanner import scan_profile
from .models import OS, ProviderType, CollectionKind, UserCollectionItem, BackupPolicy
from .backup import build_provider, backup_profile, check_restore_conflicts, restore_profile

console = Console()


def _get_defaults():
    try:
        return load_default_collections(find_default_collections())
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load default collections: {e}[/yellow]")
        return {}


def _active_profile():
    name = get_active_profile_name()
    if not name:
        console.print("[red]No active profile. Run: cursfig profile use <name>[/red]")
        sys.exit(1)
    try:
        return load_profile(profile_path(name))
    except Exception as e:
        console.print(f"[red]Could not load profile '{name}': {e}[/red]")
        sys.exit(1)


# ─────────────────────────────────────────────────────
# CLI Root
# ─────────────────────────────────────────────────────

@click.group()
@click.version_option("0.1.0", prog_name="cursfig")
def cli():
    """cursfig — configuration backup & restore tool."""


# ─────────────────────────────────────────────────────
# Profile commands
# ─────────────────────────────────────────────────────

@cli.group()
def profile():
    """Manage profiles."""


@profile.command("list")
def profile_list():
    """List all profiles."""
    profiles = list_profiles()
    active = get_active_profile_name()
    if not profiles:
        console.print("[dim]No profiles found. Create one with: cursfig profile new <name>[/dim]")
        return
    table = Table(title="Profiles")
    table.add_column("Active")
    table.add_column("Name")
    table.add_column("OS")
    table.add_column("Programs")
    table.add_column("Games")
    table.add_column("Providers")
    for pname in profiles:
        try:
            p = load_profile(profile_path(pname))
            marker = "[green]✓[/green]" if pname == active else ""
            table.add_row(
                marker, pname, p.os.value,
                str(len(p.programs)), str(len(p.games)),
                ", ".join(x.value for x in p.providers),
            )
        except Exception:
            table.add_row("", pname, "?", "?", "?", "?")
    console.print(table)


@profile.command("new")
@click.argument("name")
@click.option("--os", "os_name", default="linux",
              type=click.Choice(["windows", "linux", "macos"]), help="Target OS")
@click.option("--description", "-d", default="", help="Profile description")
def profile_new(name: str, os_name: str, description: str):
    """Create a new profile."""
    path = profile_path(name)
    if path.exists():
        console.print(f"[red]Profile '{name}' already exists.[/red]")
        sys.exit(1)
    p = new_profile(name, os_name)
    p.description = description
    save_profile(p, path)
    set_active_profile(name)
    console.print(f"[green]Created profile '{name}' (OS: {os_name}). Set as active.[/green]")


@profile.command("use")
@click.argument("name")
def profile_use(name: str):
    """Set active profile."""
    if not profile_path(name).exists():
        console.print(f"[red]Profile '{name}' not found.[/red]")
        sys.exit(1)
    set_active_profile(name)
    console.print(f"[green]Active profile: {name}[/green]")


@profile.command("show")
@click.argument("name", required=False)
def profile_show(name: str | None):
    """Show profile details."""
    name = name or get_active_profile_name()
    if not name:
        console.print("[red]No profile specified or active.[/red]")
        sys.exit(1)
    p = load_profile(profile_path(name))
    console.print(Panel(
        f"[bold]{p.name}[/bold]  {p.description}\n"
        f"OS: [yellow]{p.os.value}[/yellow]   "
        f"Providers: {', '.join(x.value for x in p.providers) or 'none'}\n\n"
        f"[bold]Backup Policy[/bold]\n"
        f"  Programs → {', '.join(x.value for x in p.backup_policy.programs) or 'none'}\n"
        f"  Games    → {', '.join(x.value for x in p.backup_policy.games) or 'none'}\n\n"
        f"[bold]Programs[/bold]: {', '.join(x.name for x in p.programs) or 'none'}\n"
        f"[bold]Games[/bold]: {', '.join(x.name for x in p.games) or 'none'}",
        title="Profile",
    ))


@profile.command("delete")
@click.argument("name")
@click.confirmation_option(prompt="Are you sure?")
def profile_delete(name: str):
    """Delete a profile."""
    path = profile_path(name)
    if not path.exists():
        console.print(f"[red]Profile '{name}' not found.[/red]")
        sys.exit(1)
    path.unlink()
    console.print(f"[green]Deleted profile '{name}'.[/green]")


# ─────────────────────────────────────────────────────
# Add / Remove collections
# ─────────────────────────────────────────────────────

@cli.command("add")
@click.argument("kind", type=click.Choice(["program", "game"]))
@click.argument("name")
@click.option("--profile", "-p", "profile_name", default=None)
def add_collection(kind: str, name: str, profile_name: str | None):
    """Add a program or game to the active profile."""
    pname = profile_name or get_active_profile_name()
    if not pname:
        console.print("[red]No active profile.[/red]")
        sys.exit(1)
    p = load_profile(profile_path(pname))
    item = UserCollectionItem(name=name)
    if kind == "program":
        if any(x.name.lower() == name.lower() for x in p.programs):
            console.print(f"[yellow]Program '{name}' already in profile.[/yellow]")
            return
        p.programs.append(item)
    else:
        if any(x.name.lower() == name.lower() for x in p.games):
            console.print(f"[yellow]Game '{name}' already in profile.[/yellow]")
            return
        p.games.append(item)
    save_profile(p, profile_path(pname))
    console.print(f"[green]Added {kind} '{name}' to profile '{pname}'.[/green]")


@cli.command("remove")
@click.argument("kind", type=click.Choice(["program", "game"]))
@click.argument("name")
@click.option("--profile", "-p", "profile_name", default=None)
def remove_collection(kind: str, name: str, profile_name: str | None):
    """Remove a program or game from the active profile."""
    pname = profile_name or get_active_profile_name()
    if not pname:
        console.print("[red]No active profile.[/red]")
        sys.exit(1)
    p = load_profile(profile_path(pname))
    if kind == "program":
        before = len(p.programs)
        p.programs = [x for x in p.programs if x.name.lower() != name.lower()]
        removed = before - len(p.programs)
    else:
        before = len(p.games)
        p.games = [x for x in p.games if x.name.lower() != name.lower()]
        removed = before - len(p.games)
    if removed == 0:
        console.print(f"[yellow]'{name}' not found in {kind}s.[/yellow]")
        return
    save_profile(p, profile_path(pname))
    console.print(f"[green]Removed {kind} '{name}'.[/green]")


# ─────────────────────────────────────────────────────
# Scan
# ─────────────────────────────────────────────────────

@cli.command("scan")
@click.option("--profile", "-p", "profile_name", default=None)
@click.option("--show-missing/--no-show-missing", default=True)
def scan(profile_name: str | None, show_missing: bool):
    """Scan profile to check which config files exist."""
    pname = profile_name or get_active_profile_name()
    if not pname:
        console.print("[red]No active profile.[/red]")
        sys.exit(1)
    p = load_profile(profile_path(pname))
    defaults = _get_defaults()

    with console.status("[bold green]Scanning..."):
        results = scan_profile(p, defaults)

    if not results:
        console.print("[yellow]No collections to scan.[/yellow]")
        return

    table = Table(title=f"Scan: {pname}", show_header=True)
    table.add_column("Collection", style="cyan")
    table.add_column("Resource")
    table.add_column("Path", style="dim")
    table.add_column("Found", style="green", justify="right")
    table.add_column("Missing", style="red", justify="right")
    table.add_column("Files/Folders")

    total_found = total_missing = 0
    for r in results:
        details = []
        for fname, exists in r.files:
            mark = "[green]✓[/green]" if exists else "[red]✗[/red]"
            details.append(f"{mark} {fname}")
        for fname, exists in r.folders:
            mark = "[green]✓[/green]" if exists else "[red]✗[/red]"
            details.append(f"{mark} 📁{fname}")
        total_found += r.found_count
        total_missing += r.missing_count

        path_display = r.path
        if len(path_display) > 45:
            path_display = "…" + path_display[-44:]

        table.add_row(
            r.collection_name,
            r.resource_name,
            path_display,
            str(r.found_count) if r.found_count else "[dim]0[/dim]",
            str(r.missing_count) if r.missing_count else "[dim]0[/dim]",
            "  ".join(details),
        )

    console.print(table)
    console.print(
        f"\nTotal: [green]{total_found} found[/green], "
        f"[red]{total_missing} missing[/red]"
    )


# ─────────────────────────────────────────────────────
# Provider setup
# ─────────────────────────────────────────────────────

@cli.group()
def provider():
    """Configure backup providers."""


@provider.command("setup")
@click.argument("kind", type=click.Choice(["local", "github", "google_drive"]))
def provider_setup(kind: str):
    """Interactively configure a provider."""
    console.print(f"[bold]Configure {kind} provider[/bold]")
    if kind == "local":
        path = click.prompt("Backup directory path", default=str(Path.home() / "cursfig_backup"))
        cfg = {"path": path}
    elif kind == "github":
        token = click.prompt("GitHub personal access token", hide_input=True)
        repo = click.prompt("Repository (user/repo)")
        cfg = {"token": token, "repo": repo}
    elif kind == "google_drive":
        creds = click.prompt("Path to credentials JSON")
        folder = click.prompt("Google Drive folder ID (optional)", default="")
        cfg = {"credentials": creds, "folder_id": folder}
    else:
        return

    # Test connection
    try:
        ptype = ProviderType(kind)
        prov = build_provider(ptype, cfg)
        if prov.test_connection():
            console.print(f"[green]✓ Connection to {kind} successful.[/green]")
        else:
            console.print(f"[yellow]⚠ Could not verify connection to {kind}.[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Could not test connection: {e}[/yellow]")

    set_provider_config(kind, cfg)
    console.print(f"[green]Provider '{kind}' configured.[/green]")


@provider.command("list")
def provider_list():
    """Show configured providers."""
    table = Table(title="Configured Providers")
    table.add_column("Provider")
    table.add_column("Status")
    table.add_column("Config")
    for pt in ProviderType:
        cfg = get_provider_config(pt.value)
        if cfg:
            # Redact secrets
            display = {k: ("***" if "token" in k or "cred" in k else v) for k, v in cfg.items()}
            table.add_row(pt.value, "[green]configured[/green]", str(display))
        else:
            table.add_row(pt.value, "[dim]not configured[/dim]", "")
    console.print(table)


# ─────────────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────────────

@cli.command("backup")
@click.option("--profile", "-p", "profile_name", default=None)
@click.option("--dry-run", is_flag=True, help="Show what would be backed up without doing it")
def backup(profile_name: str | None, dry_run: bool):
    """Backup configs for the active profile."""
    pname = profile_name or get_active_profile_name()
    if not pname:
        console.print("[red]No active profile.[/red]")
        sys.exit(1)
    p = load_profile(profile_path(pname))
    defaults = _get_defaults()

    if dry_run:
        from .scanner import collect_backup_files
        files = collect_backup_files(p, defaults)
        console.print(f"[bold]Dry run — would back up {len(files)} item(s):[/bold]")
        for item_name, rel_name, abs_path in files:
            console.print(f"  {item_name}/{rel_name}  →  {abs_path}")
        return

    providers = {}
    for ptype in p.providers:
        cfg = get_provider_config(ptype.value)
        if not cfg:
            console.print(f"[yellow]Provider {ptype.value} not configured. Skipping.[/yellow]")
            continue
        try:
            providers[ptype] = build_provider(ptype, cfg)
        except Exception as e:
            console.print(f"[red]Failed to init {ptype.value}: {e}[/red]")

    if not providers:
        console.print("[red]No providers configured. Run: cursfig provider setup <kind>[/red]")
        sys.exit(1)

    with console.status("[bold green]Backing up..."):
        results = backup_profile(p, defaults, providers, progress_cb=lambda m: console.print(m))
    console.print(f"\n[green]Backup complete.[/green]")
    for pname_r, ids in results.items():
        console.print(f"  {pname_r}: {len(ids)} item(s) uploaded")


# ─────────────────────────────────────────────────────
# Restore
# ─────────────────────────────────────────────────────

@cli.command("restore")
@click.option("--profile", "-p", "profile_name", default=None)
@click.option("--provider", "provider_name", default=None,
              type=click.Choice(["local", "github", "google_drive"]))
@click.option("--force", is_flag=True, help="Overwrite existing files without prompting")
def restore(profile_name: str | None, provider_name: str | None, force: bool):
    """Restore configs from a backup provider."""
    pname = profile_name or get_active_profile_name()
    if not pname:
        console.print("[red]No active profile.[/red]")
        sys.exit(1)
    p = load_profile(profile_path(pname))
    defaults = _get_defaults()

    # Find provider
    if provider_name:
        ptypes = [ProviderType(provider_name)]
    else:
        ptypes = p.providers

    provider_obj = None
    for ptype in ptypes:
        cfg = get_provider_config(ptype.value)
        if cfg:
            try:
                provider_obj = build_provider(ptype, cfg)
                console.print(f"Using provider: [cyan]{ptype.value}[/cyan]")
                break
            except Exception as e:
                console.print(f"[yellow]Could not init {ptype.value}: {e}[/yellow]")

    if not provider_obj:
        console.print("[red]No usable provider. Configure one with: cursfig provider setup[/red]")
        sys.exit(1)

    # Check conflicts
    conflicts = check_restore_conflicts(p, defaults)
    if conflicts and not force:
        console.print(f"[yellow]⚠ {len(conflicts)} file(s) already exist and will be overwritten:[/yellow]")
        for name_c, path_c in conflicts[:10]:
            console.print(f"  • {name_c}  ({path_c})")
        if len(conflicts) > 10:
            console.print(f"  … and {len(conflicts)-10} more")
        if not click.confirm("Proceed with restore?"):
            console.print("Restore cancelled.")
            return

    restore_profile(p, defaults, provider_obj, force=force or bool(conflicts),
                    progress_cb=lambda m: console.print(m))
    console.print(f"\n[green]Restore complete.[/green]")


# ─────────────────────────────────────────────────────
# defaults  command
# ─────────────────────────────────────────────────────

@cli.command("defaults")
def show_defaults():
    """Show available default collections."""
    defaults = _get_defaults()
    if not defaults:
        console.print("[yellow]No default collections loaded.[/yellow]")
        return
    table = Table(title="Default Collections")
    table.add_column("Name")
    table.add_column("Kind")
    table.add_column("Resources")
    for name, col in defaults.items():
        res_names = ", ".join(r.name for r in col.resources)
        table.add_row(col.name, col.kind.value, res_names)
    console.print(table)


# ─────────────────────────────────────────────────────
# TUI launcher
# ─────────────────────────────────────────────────────

@cli.command("tui")
def launch_tui():
    """Launch the interactive TUI."""
    from .tui import run_tui
    run_tui()


def main():
    cli()
