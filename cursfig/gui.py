"""GUI for cursfig using tkinter."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
from pathlib import Path

from .config import (
    list_profiles, profile_path, get_active_profile_name, set_active_profile,
    set_provider_config, get_provider_config, find_default_collections,
)
from .loader import load_default_collections, load_profile, save_profile, new_profile
from .scanner import scan_profile
from .models import OS, ProviderType, CollectionKind, UserCollectionItem, BackupPolicy
from .backup import build_provider, backup_profile, check_restore_conflicts, restore_profile


DARK = {
    "bg": "#1e1e2e",
    "surface": "#313244",
    "overlay": "#45475a",
    "text": "#cdd6f4",
    "subtext": "#a6adc8",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "yellow": "#f9e2af",
    "blue": "#89b4fa",
    "accent": "#cba6f7",
    "border": "#585b70",
}


def _style(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    bg, fg, sel = DARK["bg"], DARK["text"], DARK["accent"]
    surf = DARK["surface"]
    s.configure(".", background=bg, foreground=fg, fieldbackground=surf,
                 bordercolor=DARK["border"], darkcolor=surf, lightcolor=surf,
                 troughcolor=surf, selectbackground=sel, selectforeground=bg,
                 font=("Consolas", 10))
    s.configure("TFrame", background=bg)
    s.configure("TLabel", background=bg, foreground=fg)
    s.configure("TButton", background=surf, foreground=fg, borderwidth=1,
                relief="flat", padding=(8, 4))
    s.map("TButton",
          background=[("active", DARK["overlay"]), ("pressed", DARK["accent"])],
          foreground=[("active", DARK["text"])])
    s.configure("Accent.TButton", background=DARK["accent"], foreground=bg)
    s.map("Accent.TButton", background=[("active", DARK["blue"])])
    s.configure("TEntry", fieldbackground=surf, foreground=fg, borderwidth=1)
    s.configure("TCombobox", fieldbackground=surf, foreground=fg, borderwidth=1)
    s.configure("Treeview", background=surf, foreground=fg,
                fieldbackground=surf, rowheight=24)
    s.configure("Treeview.Heading", background=DARK["overlay"],
                foreground=DARK["accent"], relief="flat")
    s.map("Treeview", background=[("selected", DARK["accent"])],
          foreground=[("selected", bg)])
    s.configure("TNotebook", background=bg, borderwidth=0)
    s.configure("TNotebook.Tab", background=surf, foreground=DARK["subtext"],
                padding=(12, 4), borderwidth=0)
    s.map("TNotebook.Tab",
          background=[("selected", bg)],
          foreground=[("selected", DARK["accent"])])
    s.configure("TScrollbar", background=surf, troughcolor=bg, borderwidth=0)
    s.configure("TSeparator", background=DARK["border"])
    s.configure("TLabelframe", background=bg, foreground=DARK["subtext"])
    s.configure("TLabelframe.Label", background=bg, foreground=DARK["accent"])


class CursfigGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("cursfig")
        self.root.geometry("1100x700")
        self.root.configure(bg=DARK["bg"])
        self.root.minsize(800, 500)

        _style(root)

        self.current_profile = None
        self.defaults = {}
        self._load_defaults()
        self._build_ui()
        self._refresh_profiles()

        # Load last active
        name = get_active_profile_name()
        if name:
            self._load_profile(name)

    def _load_defaults(self):
        try:
            self.defaults = load_default_collections(find_default_collections())
        except Exception:
            self.defaults = {}

    def _build_ui(self):
        # ── Top bar ─────────────────────────────
        topbar = ttk.Frame(self.root)
        topbar.pack(fill="x", padx=0, pady=0)
        tk.Label(topbar, text="  cursfig", bg=DARK["surface"],
                 fg=DARK["accent"], font=("Consolas", 14, "bold"),
                 padx=10, pady=8).pack(side="left")
        for text, cmd in [
            ("New Profile", self._new_profile),
            ("Scan",        self._do_scan),
            ("Backup",      self._do_backup),
            ("Restore",     self._do_restore),
            ("Providers",   self._open_providers),
        ]:
            ttk.Button(topbar, text=text, command=cmd,
                       style="Accent.TButton" if text in ("Backup", "Restore") else "TButton"
                       ).pack(side="left", padx=4, pady=4)

        # ── Main split ──────────────────────────
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=0, pady=0)

        # Sidebar
        sidebar = ttk.Frame(paned, width=220)
        paned.add(sidebar, weight=0)

        ttk.Label(sidebar, text="Profiles", foreground=DARK["accent"],
                  font=("Consolas", 10, "bold")).pack(anchor="w", padx=8, pady=(8,2))

        self.profile_list = tk.Listbox(
            sidebar, bg=DARK["surface"], fg=DARK["text"],
            selectbackground=DARK["accent"], selectforeground=DARK["bg"],
            font=("Consolas", 10), borderwidth=0, activestyle="none",
            highlightthickness=0, relief="flat",
        )
        self.profile_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.profile_list.bind("<<ListboxSelect>>", self._on_profile_select)

        # Collections frame (in sidebar)
        col_frame = ttk.LabelFrame(sidebar, text="Collections")
        col_frame.pack(fill="x", padx=4, pady=4)

        btn_row = ttk.Frame(col_frame)
        btn_row.pack(fill="x", padx=4, pady=4)
        ttk.Button(btn_row, text="+ Program", command=lambda: self._add_collection("program")).pack(side="left", padx=2)
        ttk.Button(btn_row, text="+ Game", command=lambda: self._add_collection("game")).pack(side="left", padx=2)

        # Main content tabs
        self.notebook = ttk.Notebook(paned)
        paned.add(self.notebook, weight=1)

        # Tab 1: Profile overview
        self.tab_profile = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_profile, text="Profile")
        self._build_profile_tab()

        # Tab 2: Scan results
        self.tab_scan = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_scan, text="Scan Results")
        self._build_scan_tab()

        # Tab 3: Log
        self.tab_log = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_log, text="Log")
        self._build_log_tab()

    def _build_profile_tab(self):
        self.profile_text = tk.Text(
            self.tab_profile, bg=DARK["bg"], fg=DARK["text"],
            font=("Consolas", 10), state="disabled", borderwidth=0,
            wrap="word", highlightthickness=0,
        )
        self.profile_text.pack(fill="both", expand=True, padx=8, pady=8)

        # Tag config for colors
        self.profile_text.tag_configure("title", foreground=DARK["accent"], font=("Consolas", 13, "bold"))
        self.profile_text.tag_configure("key", foreground=DARK["blue"])
        self.profile_text.tag_configure("val", foreground=DARK["yellow"])
        self.profile_text.tag_configure("good", foreground=DARK["green"])
        self.profile_text.tag_configure("dim", foreground=DARK["subtext"])
        self.profile_text.tag_configure("section", foreground=DARK["accent"], font=("Consolas", 10, "bold"))

    def _build_scan_tab(self):
        cols = ("Collection", "Resource", "Path", "Found", "Missing")
        self.scan_tree = ttk.Treeview(self.tab_scan, columns=cols, show="headings")
        for col in cols:
            w = 200 if col == "Path" else (120 if col == "Collection" else 80)
            self.scan_tree.heading(col, text=col)
            self.scan_tree.column(col, width=w, minwidth=50)
        sb = ttk.Scrollbar(self.tab_scan, orient="vertical", command=self.scan_tree.yview)
        self.scan_tree.configure(yscrollcommand=sb.set)
        self.scan_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.scan_tree.tag_configure("ok", foreground=DARK["green"])
        self.scan_tree.tag_configure("warn", foreground=DARK["yellow"])
        self.scan_tree.tag_configure("bad", foreground=DARK["red"])

    def _build_log_tab(self):
        self.log_text = tk.Text(
            self.tab_log, bg=DARK["bg"], fg=DARK["text"],
            font=("Consolas", 9), state="disabled", borderwidth=0,
            wrap="word", highlightthickness=0,
        )
        sb = ttk.Scrollbar(self.tab_log, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")
        self.log_text.tag_configure("green", foreground=DARK["green"])
        self.log_text.tag_configure("red", foreground=DARK["red"])
        self.log_text.tag_configure("yellow", foreground=DARK["yellow"])
        self.log_text.tag_configure("dim", foreground=DARK["subtext"])

    # ─────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────

    def _refresh_profiles(self):
        self.profile_list.delete(0, "end")
        active = get_active_profile_name()
        for i, p in enumerate(list_profiles()):
            display = f"▸ {p}" if p == active else f"  {p}"
            self.profile_list.insert("end", display)
            if p == active:
                self.profile_list.itemconfig(i, fg=DARK["accent"])

    def _load_profile(self, name: str):
        try:
            p = load_profile(profile_path(name))
            self.current_profile = p
            set_active_profile(name)
            self._refresh_profile_view()
            self._refresh_profiles()
            self._log(f"Loaded profile: {name}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not load profile: {e}")

    def _on_profile_select(self, event):
        sel = self.profile_list.curselection()
        if not sel:
            return
        raw = self.profile_list.get(sel[0]).strip()
        name = raw.lstrip("▸ ").strip()
        self._load_profile(name)

    def _refresh_profile_view(self):
        p = self.current_profile
        if not p:
            return
        t = self.profile_text
        t.configure(state="normal")
        t.delete("1.0", "end")

        def ins(text, tag=None):
            t.insert("end", text, tag)

        ins(f"{p.name}\n", "title")
        if p.description:
            ins(f"{p.description}\n", "dim")
        ins("\n")
        ins("OS: ", "key"); ins(f"{p.os.value}\n", "val")
        ins("Providers: ", "key")
        ins((", ".join(x.value for x in p.providers) or "none") + "\n", "val")
        ins("\nBackup Policy\n", "section")
        ins("  Programs → ", "key"); ins((", ".join(x.value for x in p.backup_policy.programs) or "none") + "\n", "val")
        ins("  Games    → ", "key"); ins((", ".join(x.value for x in p.backup_policy.games) or "none") + "\n", "val")
        ins(f"\nPrograms ({len(p.programs)})\n", "section")
        for pg in p.programs:
            excl = f"  (excl: {', '.join(x.value for x in pg.exclude_providers)})" if pg.exclude_providers else ""
            ins(f"  • {pg.name}", "good")
            if excl:
                ins(excl, "dim")
            ins("\n")
        ins(f"\nGames ({len(p.games)})\n", "section")
        for gm in p.games:
            excl = f"  (excl: {', '.join(x.value for x in gm.exclude_providers)})" if gm.exclude_providers else ""
            ins(f"  • {gm.name}", "good")
            if excl:
                ins(excl, "dim")
            ins("\n")
        t.configure(state="disabled")

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        # Basic color detection
        if any(w in msg for w in ["✓", "complete", "success", "Created", "Loaded", "Added"]):
            tag = "green"
        elif any(w in msg for w in ["✗", "Error", "Failed", "error"]):
            tag = "red"
        elif any(w in msg for w in ["Warning", "Skipping", "not found", "⚠"]):
            tag = "yellow"
        else:
            tag = None
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        # Auto switch to log tab during operations
        self.notebook.select(self.tab_log)

    # ─────────────────────────────────────
    # Actions
    # ─────────────────────────────────────

    def _new_profile(self):
        dlg = NewProfileDialog(self.root)
        result = dlg.result
        if result:
            name, os_val = result
            p = new_profile(name, os_val)
            save_profile(p, profile_path(name))
            self._refresh_profiles()
            self._load_profile(name)
            self._log(f"Created profile: {name}")

    def _add_collection(self, kind: str):
        if not self.current_profile:
            messagebox.showwarning("No Profile", "Load a profile first.")
            return
        known = [k for k, v in self.defaults.items() if v.kind.value == kind]
        name = simpledialog.askstring(
            f"Add {kind.capitalize()}",
            f"Name (available: {', '.join(known) if known else 'any'}):",
            parent=self.root,
        )
        if not name:
            return
        item = UserCollectionItem(name=name)
        p = self.current_profile
        if kind == "program":
            if any(x.name.lower() == name.lower() for x in p.programs):
                messagebox.showinfo("Already Added", f"'{name}' is already in programs.")
                return
            p.programs.append(item)
        else:
            if any(x.name.lower() == name.lower() for x in p.games):
                messagebox.showinfo("Already Added", f"'{name}' is already in games.")
                return
            p.games.append(item)
        save_profile(p, profile_path(p.name))
        self._refresh_profile_view()
        self._log(f"Added {kind}: {name}")

    def _do_scan(self):
        if not self.current_profile:
            messagebox.showwarning("No Profile", "Load a profile first.")
            return
        self.notebook.select(self.tab_scan)

        def _run():
            self._log("Scanning...")
            results = scan_profile(self.current_profile, self.defaults)
            self.root.after(0, lambda: self._populate_scan(results))

        threading.Thread(target=_run, daemon=True).start()

    def _populate_scan(self, results):
        for row in self.scan_tree.get_children():
            self.scan_tree.delete(row)
        total_found = total_miss = 0
        for r in results:
            total_found += r.found_count
            total_miss += r.missing_count
            tag = "ok" if r.missing_count == 0 else ("bad" if r.found_count == 0 else "warn")
            path = r.path[-45:] if len(r.path) > 45 else r.path
            self.scan_tree.insert("", "end", values=(
                r.collection_name, r.resource_name, path,
                r.found_count, r.missing_count,
            ), tags=(tag,))
        self._log(f"Scan done. Found: {total_found}, Missing: {total_miss}")
        self.notebook.select(self.tab_scan)

    def _do_backup(self):
        if not self.current_profile:
            messagebox.showwarning("No Profile", "Load a profile first.")
            return
        providers = self._build_providers()
        if not providers:
            return

        def _run():
            self._log("Starting backup...")
            backup_profile(
                self.current_profile, self.defaults, providers,
                progress_cb=lambda m: self.root.after(0, lambda: self._log(m)),
            )
            self.root.after(0, lambda: self._log("✓ Backup complete."))

        threading.Thread(target=_run, daemon=True).start()

    def _do_restore(self):
        if not self.current_profile:
            messagebox.showwarning("No Profile", "Load a profile first.")
            return

        conflicts = check_restore_conflicts(self.current_profile, self.defaults)
        if conflicts:
            msg = f"{len(conflicts)} file(s) already exist and will be overwritten:\n\n"
            msg += "\n".join(f"  • {n}" for n, _ in conflicts[:10])
            if len(conflicts) > 10:
                msg += f"\n  … and {len(conflicts)-10} more"
            if not messagebox.askyesno("⚠ Overwrite Warning", msg, icon="warning"):
                return

        # Pick provider
        provider_obj = self._pick_restore_provider()
        if not provider_obj:
            return

        def _run():
            self._log("Starting restore...")
            restore_profile(
                self.current_profile, self.defaults, provider_obj,
                force=True,
                progress_cb=lambda m: self.root.after(0, lambda: self._log(m)),
            )
            self.root.after(0, lambda: self._log("✓ Restore complete."))

        threading.Thread(target=_run, daemon=True).start()

    def _build_providers(self) -> dict:
        from .models import ProviderType
        providers = {}
        for ptype in self.current_profile.providers:
            cfg = get_provider_config(ptype.value)
            if not cfg:
                self._log(f"Provider {ptype.value} not configured. Skipping.")
                continue
            try:
                providers[ptype] = build_provider(ptype, cfg)
            except Exception as e:
                self._log(f"Could not init {ptype.value}: {e}")
        if not providers:
            messagebox.showwarning("No Providers",
                "No providers configured. Set them up via the Providers button.")
        return providers

    def _pick_restore_provider(self):
        for ptype in self.current_profile.providers:
            cfg = get_provider_config(ptype.value)
            if cfg:
                try:
                    return build_provider(ptype, cfg)
                except Exception:
                    pass
        messagebox.showwarning("No Provider", "No usable provider found.")
        return None

    def _open_providers(self):
        if not self.current_profile:
            messagebox.showwarning("No Profile", "Load a profile first.")
            return
        ProviderDialog(self.root, self.current_profile, self._log)


# ─────────────────────────────────────────────────────
# Dialogs
# ─────────────────────────────────────────────────────

class NewProfileDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("New Profile")
        self.configure(bg=DARK["bg"])
        self.grab_set()
        self.result = None
        self._build()
        self.wait_window()

    def _build(self):
        pad = {"padx": 12, "pady": 6}
        ttk.Label(self, text="Create New Profile",
                  font=("Consolas", 12, "bold"),
                  foreground=DARK["accent"]).pack(**pad)
        ttk.Label(self, text="Profile name:").pack(anchor="w", **pad)
        self.name_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.name_var, width=30).pack(**pad)
        ttk.Label(self, text="OS:").pack(anchor="w", **pad)
        self.os_var = tk.StringVar(value="linux")
        cb = ttk.Combobox(self, textvariable=self.os_var,
                          values=["linux", "windows", "macos"], width=28, state="readonly")
        cb.pack(**pad)
        row = ttk.Frame(self)
        row.pack(pady=8)
        ttk.Button(row, text="Create", style="Accent.TButton",
                   command=self._ok).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="left", padx=4)

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Required", "Please enter a profile name.", parent=self)
            return
        self.result = (name, self.os_var.get())
        self.destroy()


class ProviderDialog(tk.Toplevel):
    def __init__(self, parent, profile, log_fn):
        super().__init__(parent)
        self.title("Configure Providers")
        self.configure(bg=DARK["bg"])
        self.grab_set()
        self.profile = profile
        self.log_fn = log_fn
        self._build()

    def _build(self):
        ttk.Label(self, text="Configure Providers",
                  font=("Consolas", 12, "bold"),
                  foreground=DARK["accent"]).pack(padx=12, pady=8)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        for pt in ProviderType:
            frame = ttk.Frame(nb)
            nb.add(frame, text=pt.value)
            self._build_provider_frame(frame, pt)

        ttk.Button(self, text="Close", command=self.destroy).pack(pady=8)

    def _build_provider_frame(self, frame, ptype: ProviderType):
        cfg = get_provider_config(ptype.value)
        pad = {"padx": 12, "pady": 4}
        entries = {}

        if ptype == ProviderType.LOCAL:
            fields = [("Backup directory path:", "path", False)]
        elif ptype == ProviderType.GITHUB:
            fields = [("GitHub token:", "token", True), ("Repository (user/repo):", "repo", False)]
        elif ptype == ProviderType.GOOGLE_DRIVE:
            fields = [("Credentials JSON path:", "credentials", False), ("Folder ID (optional):", "folder_id", False)]

        for label, key, secret in fields:
            ttk.Label(frame, text=label).pack(anchor="w", **pad)
            var = tk.StringVar(value=cfg.get(key, "") if cfg else "")
            ent = ttk.Entry(frame, textvariable=var, width=40,
                            show="*" if secret else "")
            ent.pack(**pad)
            if key == "credentials":
                row = ttk.Frame(frame)
                row.pack(anchor="w", padx=12)
                ttk.Button(row, text="Browse…",
                           command=lambda v=var: v.set(
                               filedialog.askopenfilename(
                                   filetypes=[("JSON", "*.json"), ("All", "*")],
                                   parent=frame,
                               ) or v.get()
                           )).pack(side="left")
            if key == "path":
                row = ttk.Frame(frame)
                row.pack(anchor="w", padx=12)
                ttk.Button(row, text="Browse…",
                           command=lambda v=var: v.set(
                               filedialog.askdirectory(parent=frame) or v.get()
                           )).pack(side="left")
            entries[key] = var

        status_var = tk.StringVar()
        ttk.Label(frame, textvariable=status_var, foreground=DARK["yellow"]).pack(**pad)

        def _save():
            new_cfg = {k: v.get().strip() for k, v in entries.items()}
            try:
                prov = build_provider(ptype, new_cfg)
                ok = prov.test_connection()
                status_var.set("✓ Connected" if ok else "⚠ Could not verify connection")
            except Exception as e:
                status_var.set(f"⚠ {e}")
            set_provider_config(ptype.value, new_cfg)
            if ptype not in self.profile.providers:
                self.profile.providers.append(ptype)
            save_profile(self.profile, profile_path(self.profile.name))
            self.log_fn(f"Provider {ptype.value} configured.")

        ttk.Button(frame, text="Save & Test", style="Accent.TButton",
                   command=_save).pack(**pad)


def run_gui():
    root = tk.Tk()
    app = CursfigGUI(root)
    root.mainloop()
