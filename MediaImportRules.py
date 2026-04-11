#!/usr/bin/env python3
"""
MediaImportRules.py
DaVinci Resolve Workflow Integration Plugin

Rules-based media automation: match clips by metadata conditions
and apply bulk actions (clip colour, flags, group, sizing preset, ACES GC).

Install location (macOS):
  ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/
  Fusion/Scripts/Workflow Integration/MediaImportRules.py

Usage:
  Workspace > Scripts > Workflow Integration > MediaImportRules
"""

import os
import sys
import json
import platform

# ─── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "MediaImportRules.json")

CONDITIONS = [
    "Resolution",
    "Shot Frame Rate",
    "Video Codec",
    "Camera #",
    "Camera Type",
]

# Maps user-facing condition names → DaVinci clip property keys
CONDITION_PROPS = {
    "Resolution":      "Resolution",
    "Shot Frame Rate": "FPS",
    "Video Codec":     "Video Codec",
    "Camera #":        "Camera #",
    "Camera Type":     "Camera Type",
}

ACTIONS = [
    "Add to group",
    "Clip color",
    "Flags",
    "Input sizing preset",
    "ACES Gamut Compress",
]

# All named colours supported by SetClipColor()
CLIP_COLORS = [
    "Orange", "Apricot", "Yellow", "Lime", "Olive", "Green",
    "Teal", "Navy", "Blue", "Purple", "Violet", "Pink",
    "Tan", "Beige", "Brown", "Chocolate",
]

# Named colours supported by AddFlag()
FLAG_COLORS = [
    "Red", "Blue", "Green", "Yellow", "Cyan", "Magenta",
]

ACES_OPTIONS = ["None", "Standard - LMT"]

# ─── Dark-theme palette ───────────────────────────────────────────────────────

BG         = "#1e1e1e"
BG_ROW     = "#272727"
FG         = "#e0e0e0"
FG_DIM     = "#757575"
ACCENT     = "#4a90d9"
ACCENT_HOV = "#357abd"
ON_COL     = "#43a047"
OFF_COL    = "#616161"
REMOVE_COL = "#c62828"
BTN_BG     = "#333333"
BTN_FG     = "#e0e0e0"
SEP_COL    = "#3a3a3a"

# ─── DaVinci Resolve API helpers ──────────────────────────────────────────────

def _get_resolve():
    """Return the Resolve application object, however the env exposes it."""
    try:
        return bmd.scriptapp("Resolve")          # inside Resolve env
    except NameError:
        pass
    try:
        import DaVinciResolveScript as dvr       # external / standalone
        return dvr.scriptapp("Resolve")
    except Exception:
        return None


def get_resolve_context():
    """Return (resolve, project, media_pool) – any may be None on failure."""
    resolve = _get_resolve()
    if not resolve:
        return None, None, None
    pm          = resolve.GetProjectManager()
    project     = pm.GetCurrentProject()     if pm      else None
    media_pool  = project.GetMediaPool()     if project else None
    return resolve, project, media_pool


def _all_clips(folder):
    """Recursively collect every MediaPoolItem under *folder*."""
    clips = list(folder.GetClipList() or [])
    for sub in folder.GetSubFolderList() or []:
        clips.extend(_all_clips(sub))
    return clips


def get_unique_values(condition, media_pool):
    """Return sorted, de-duplicated metadata values for *condition* across all clips."""
    prop = CONDITION_PROPS.get(condition)
    if not prop or not media_pool:
        return []
    clips  = _all_clips(media_pool.GetRootFolder())
    values = set()
    for clip in clips:
        v = clip.GetClipProperty(prop)
        if v:
            values.add(str(v).strip())
    return sorted(values)


def _folder_paths(folder, prefix=""):
    """Flat list of all bin paths under *folder* (e.g. 'Dailies/Day 01')."""
    paths = []
    for sub in folder.GetSubFolderList() or []:
        name = sub.GetName()
        path = f"{prefix}/{name}" if prefix else name
        paths.append(path)
        paths.extend(_folder_paths(sub, path))
    return paths


def get_action_values(action, project, media_pool):
    """Return available option strings for *action*."""
    if action == "Add to group":
        if not media_pool:
            return ["(no project open)"]
        paths = _folder_paths(media_pool.GetRootFolder())
        return paths or ["(no bins found)"]

    if action == "Clip color":
        return CLIP_COLORS

    if action == "Flags":
        return FLAG_COLORS

    if action == "Input sizing preset":
        # Attempt API call first (available in newer Resolve versions)
        try:
            presets = project.GetInputSizingPresetList()
            if presets:
                return list(presets)
        except Exception:
            pass
        return ["Project", "Custom", "None"]

    if action == "ACES Gamut Compress":
        return ACES_OPTIONS

    return ["(select an action first)"]


def _find_folder(root, path):
    """Navigate to a MediaPool folder by slash-separated path string."""
    parts = [p for p in path.split("/") if p]
    cur   = root
    for part in parts:
        found = None
        for sub in cur.GetSubFolderList() or []:
            if sub.GetName() == part:
                found = sub
                break
        if not found:
            return None
        cur = found
    return cur


def _apply_action(clip, action, value, project, media_pool):
    """Apply a single *action* / *value* pair to *clip*."""
    try:
        if action == "Clip color":
            clip.SetClipColor(value)

        elif action == "Flags":
            clip.AddFlag(value)

        elif action == "Add to group":
            target = _find_folder(media_pool.GetRootFolder(), value)
            if target:
                media_pool.MoveClips([clip], target)

        elif action == "Input sizing preset":
            clip.SetClipProperty("Input Sizing Preset", value)

        elif action == "ACES Gamut Compress":
            clip.SetClipProperty("ACES GC Preset", value)
    except Exception as exc:
        print(f"[MediaImportRules] Warning: could not apply '{action}' → {exc}")


def execute_rules(rules, project, media_pool):
    """Run every active rule against all clips in the current project."""
    active = [r for r in rules if r.get("active", True)]
    if not active or not media_pool:
        return

    all_clips = _all_clips(media_pool.GetRootFolder())

    for rule in active:
        cond      = rule.get("condition", "")
        cond_val  = rule.get("condition_value", "").strip()
        action    = rule.get("action", "")
        act_val   = rule.get("action_value", "").strip()

        if not all([cond, cond_val, action, act_val]):
            continue

        prop = CONDITION_PROPS.get(cond)
        if not prop:
            continue

        for clip in all_clips:
            clip_val = str(clip.GetClipProperty(prop) or "").strip()
            if clip_val == cond_val:
                _apply_action(clip, action, act_val, project, media_pool)


# ─── Settings I/O ─────────────────────────────────────────────────────────────

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return []
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh).get("rules", [])
    except Exception:
        return []


def save_settings(rules):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump({"rules": rules}, fh, indent=2, ensure_ascii=False)


# ─── Tkinter UI ───────────────────────────────────────────────────────────────

try:
    import tkinter as tk
    from tkinter import ttk
    HAS_TK = True
except ImportError:
    HAS_TK = False


class ToggleSwitch(tk.Canvas):
    """Pill-shaped toggle switch (ON = green, OFF = grey)."""

    W = 52
    H = 26

    def __init__(self, parent, active=True, **kwargs):
        super().__init__(
            parent,
            width=self.W, height=self.H,
            bg=BG_ROW, highlightthickness=0,
            **kwargs,
        )
        self._active = bool(active)
        self._redraw()
        self.bind("<Button-1>", self._on_click)
        self.configure(cursor="hand2")

    def _redraw(self):
        self.delete("all")
        colour = ON_COL if self._active else OFF_COL
        r   = self.H // 2
        pad = 3
        # Track
        self.create_oval(0, 0, self.H, self.H, fill=colour, outline="")
        self.create_oval(self.W - self.H, 0, self.W, self.H, fill=colour, outline="")
        self.create_rectangle(r, 0, self.W - r, self.H, fill=colour, outline="")
        # Thumb
        cx = (self.W - r) if self._active else r
        self.create_oval(
            cx - r + pad, pad,
            cx + r - pad, self.H - pad,
            fill="white", outline="",
        )

    def _on_click(self, _event=None):
        self._active = not self._active
        self._redraw()

    def get(self):
        return self._active

    def set(self, value):
        self._active = bool(value)
        self._redraw()


class RuleRow:
    """One horizontal rule row: condition → action + toggle + remove."""

    def __init__(self, parent, rule_data, plugin):
        self.plugin = plugin

        self.frame = tk.Frame(parent, bg=BG_ROW, padx=6, pady=5)

        # ── Condition selector ────────────────────────────────────────────────
        self.cond_var   = tk.StringVar()
        self.cond_combo = ttk.Combobox(
            self.frame, textvariable=self.cond_var,
            values=CONDITIONS, state="readonly", width=17,
        )
        self.cond_combo.pack(side="left", padx=(0, 4))

        # ── Condition value selector ──────────────────────────────────────────
        self.cond_val_var   = tk.StringVar()
        self.cond_val_combo = ttk.Combobox(
            self.frame, textvariable=self.cond_val_var,
            state="readonly", width=17,
        )
        self.cond_val_combo.pack(side="left", padx=(0, 8))

        # ── Arrow ─────────────────────────────────────────────────────────────
        tk.Label(
            self.frame, text="→", bg=BG_ROW, fg=FG_DIM,
            font=("", 13),
        ).pack(side="left", padx=4)

        # ── Action selector ───────────────────────────────────────────────────
        self.act_var   = tk.StringVar()
        self.act_combo = ttk.Combobox(
            self.frame, textvariable=self.act_var,
            values=ACTIONS, state="readonly", width=17,
        )
        self.act_combo.pack(side="left", padx=(8, 4))

        # ── Action value selector ─────────────────────────────────────────────
        self.act_val_var   = tk.StringVar()
        self.act_val_combo = ttk.Combobox(
            self.frame, textvariable=self.act_val_var,
            state="readonly", width=17,
        )
        self.act_val_combo.pack(side="left", padx=(0, 12))

        # ── Toggle switch ─────────────────────────────────────────────────────
        self.toggle = ToggleSwitch(
            self.frame, active=rule_data.get("active", True),
        )
        self.toggle.pack(side="left", padx=4)

        # ── Remove button ─────────────────────────────────────────────────────
        remove_btn = tk.Button(
            self.frame, text="🗑",
            command=lambda: self.plugin.remove_rule(self),
            bg=REMOVE_COL, fg="white", activebackground="#8b0000",
            activeforeground="white",
            relief="flat", bd=0, padx=7, pady=3,
            font=("", 13), cursor="hand2",
        )
        remove_btn.pack(side="left", padx=(8, 0))

        # ── Initialise values (traces added AFTER to avoid double-populate) ───
        cond = rule_data.get("condition", CONDITIONS[0])
        self.cond_var.set(cond if cond in CONDITIONS else CONDITIONS[0])

        act = rule_data.get("action", ACTIONS[0])
        self.act_var.set(act if act in ACTIONS else ACTIONS[0])

        self._populate_cond_vals(rule_data.get("condition_value", ""))
        self._populate_act_vals(rule_data.get("action_value",    ""))

        # Register traces now so user-driven changes update the value dropdowns
        self.cond_var.trace_add("write", self._on_cond_change)
        self.act_var.trace_add( "write", self._on_act_change)

    # ── Dropdown population ───────────────────────────────────────────────────

    def _populate_cond_vals(self, saved=""):
        cond = self.cond_var.get()
        vals = get_unique_values(cond, self.plugin.media_pool)
        self.cond_val_combo["values"] = vals
        if saved and saved in vals:
            self.cond_val_var.set(saved)
        elif vals:
            self.cond_val_var.set(vals[0])
        else:
            self.cond_val_var.set("")

    def _populate_act_vals(self, saved=""):
        act  = self.act_var.get()
        vals = get_action_values(act, self.plugin.project, self.plugin.media_pool)
        self.act_val_combo["values"] = vals
        if saved and saved in vals:
            self.act_val_var.set(saved)
        elif vals:
            self.act_val_var.set(vals[0])
        else:
            self.act_val_var.set("")

    # ── Trace callbacks ───────────────────────────────────────────────────────

    def _on_cond_change(self, *_):
        self._populate_cond_vals()

    def _on_act_change(self, *_):
        self._populate_act_vals()

    # ── Data accessor ─────────────────────────────────────────────────────────

    def get_data(self):
        return {
            "condition":       self.cond_var.get(),
            "condition_value": self.cond_val_var.get(),
            "action":          self.act_var.get(),
            "action_value":    self.act_val_var.get(),
            "active":          self.toggle.get(),
        }


class MediaImportRulesApp:
    """Main application window."""

    def __init__(self, project, media_pool):
        self.project    = project
        self.media_pool = media_pool
        self.rows: list = []

        self.root = tk.Tk()
        self.root.title("Media Import Rules")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(980, 160)

        self._apply_style()
        self._build_ui()

        # Load and render saved rules
        for rule_data in load_settings():
            self._add_row(rule_data)

        self._sync_scroll_region()

        # Keyboard shortcuts: Esc = Save & Exit, Return = Save & Execute
        self.root.bind("<Escape>", lambda _e: self.save_and_exit())
        self.root.bind("<Return>", lambda _e: self.save_and_execute())

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_style(self):
        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure(
            "TCombobox",
            fieldbackground="#2e2e2e",
            background="#2e2e2e",
            foreground=FG,
            selectbackground=ACCENT,
            selectforeground="white",
            arrowcolor=FG,
            relief="flat",
            borderwidth=1,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#2e2e2e")],
            foreground=[("readonly", FG)],
            background=[("readonly", "#2e2e2e")],
        )
        # Style the drop-down list
        self.root.option_add("*TCombobox*Listbox.background",   "#2e2e2e")
        self.root.option_add("*TCombobox*Listbox.foreground",   FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top toolbar ───────────────────────────────────────────────────────
        toolbar = tk.Frame(self.root, bg=BG, pady=8)
        toolbar.pack(fill="x", padx=12, side="top")

        tk.Button(
            toolbar, text="＋  Add Rule",
            command=self.add_rule,
            bg=ACCENT, fg="white",
            activebackground=ACCENT_HOV, activeforeground="white",
            relief="flat", bd=0, padx=14, pady=6,
            font=("", 11, "bold"), cursor="hand2",
        ).pack(side="left")

        # ── Scrollable rules container ─────────────────────────────────────────
        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        self.canvas = tk.Canvas(mid, bg=BG, highlightthickness=0)
        vscroll     = tk.Scrollbar(mid, orient="vertical",
                                   command=self.canvas.yview,
                                   bg=BTN_BG, troughcolor=BG)

        self.rules_frame  = tk.Frame(self.canvas, bg=BG)
        self._cw_id       = self.canvas.create_window(
            (0, 0), window=self.rules_frame, anchor="nw",
        )

        self.canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.rules_frame.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind(      "<Configure>", self._on_canvas_configure)

        # Mouse-wheel scrolling (cross-platform)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>",   lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>",   lambda _e: self.canvas.yview_scroll( 1, "units"))

        # ── Placeholder label ─────────────────────────────────────────────────
        self.placeholder = tk.Label(
            self.rules_frame,
            text='No rules defined. Click "＋ Add Rule" to get started.',
            bg=BG, fg=FG_DIM, font=("", 11), pady=18,
        )
        self.placeholder.pack()

        # ── Separator ──────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=SEP_COL, height=1).pack(fill="x", padx=12)

        # ── Bottom action bar ──────────────────────────────────────────────────
        bottom = tk.Frame(self.root, bg=BG, pady=10)
        bottom.pack(fill="x", padx=12, side="bottom")

        tk.Button(
            bottom, text="Save and Exit",
            command=self.save_and_exit,
            bg=BTN_BG, fg=BTN_FG,
            activebackground="#444", activeforeground=FG,
            relief="flat", bd=0, padx=16, pady=7,
            font=("", 10), cursor="hand2",
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            bottom, text="Save and Execute",
            command=self.save_and_execute,
            bg="#2e7d32", fg="white",
            activebackground="#1b5e20", activeforeground="white",
            relief="flat", bd=0, padx=16, pady=7,
            font=("", 10, "bold"), cursor="hand2",
        ).pack(side="left")

    # ── Canvas helpers ────────────────────────────────────────────────────────

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self._cw_id, width=event.width)

    def _on_mousewheel(self, event):
        if sys.platform == "darwin":
            self.canvas.yview_scroll(-event.delta, "units")
        else:
            self.canvas.yview_scroll(int(-1 * event.delta / 120), "units")

    def _sync_scroll_region(self):
        self.root.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        n = len(self.rows)
        h = min(max(180, 130 + n * 48), 720)
        self.root.geometry(f"980x{h}")

    # ── Rule management ───────────────────────────────────────────────────────

    def add_rule(self):
        self._add_row({
            "condition":       CONDITIONS[0],
            "condition_value": "",
            "action":          ACTIONS[0],
            "action_value":    "",
            "active":          True,
        })

    def _add_row(self, rule_data):
        if self.rows == [] and self.placeholder.winfo_manager():
            self.placeholder.pack_forget()

        row = RuleRow(self.rules_frame, rule_data, self)
        row.frame.pack(fill="x", pady=2)
        self.rows.append(row)
        self._sync_scroll_region()

    def remove_rule(self, row):
        row.frame.destroy()
        self.rows.remove(row)
        if not self.rows:
            self.placeholder.pack()
        self._sync_scroll_region()

    # ── Data helpers ──────────────────────────────────────────────────────────

    def _collect(self):
        return [row.get_data() for row in self.rows]

    # ── Button actions ────────────────────────────────────────────────────────

    def save_and_exit(self):
        save_settings(self._collect())
        self.root.destroy()

    def save_and_execute(self):
        rules = self._collect()
        save_settings(rules)
        if self.project and self.media_pool:
            execute_rules(rules, self.project, self.media_pool)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    if not HAS_TK:
        print(
            "[MediaImportRules] Error: tkinter is not available.\n"
            "Make sure DaVinci Resolve is using a Python build that includes Tk/Tcl."
        )
        return

    _resolve, project, media_pool = get_resolve_context()

    MediaImportRulesApp(project, media_pool).run()


main()
