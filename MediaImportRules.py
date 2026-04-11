#!/usr/bin/env python3
"""
MediaImportRules.py
DaVinci Resolve Workflow Integration Plugin

Defines metadata-based rules that apply bulk actions to matching clips.
Place in the Workflow Integration Plugins folder; launch via
Workspace > Workflow Integrations > MediaImportRules.

On launch, Resolve automatically provides `resolve` and `project` globals.
"""

import json
import os
import sys

# ── UI manager (Resolve / Fusion built-in) ────────────────────────────────────

ui         = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

WIN_ID = "com.blackmagicdesign.resolve.MediaImportRules"

# Single-instance guard
_existing = ui.FindWindow(WIN_ID)
if _existing:
    _existing.Show()
    _existing.Raise()
    exit()

# ── Settings file (next to this script in the plugins folder) ─────────────────

if sys.platform == "darwin":
    _PLUGINS_DIR = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins"
elif sys.platform == "win32":
    _PLUGINS_DIR = os.path.join(
        os.environ.get("PROGRAMDATA", ""),
        r"Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins",
    )
else:
    _PLUGINS_DIR = os.path.expanduser("~/.local/share/DaVinciResolve/Workflow Integration Plugins")

SETTINGS_FILE = os.path.join(_PLUGINS_DIR, "MediaImportRules.json")

# ── Domain constants ──────────────────────────────────────────────────────────

CONDITIONS = ["Resolution", "Shot Frame Rate", "Video Codec", "Camera #", "Camera Type"]

CONDITION_PROPS = {
    "Resolution":      "Resolution",
    "Shot Frame Rate": "FPS",
    "Video Codec":     "Video Codec",
    "Camera #":        "Camera #",
    "Camera Type":     "Camera Type",
}

ACTIONS = ["Add to group", "Clip color", "Flags", "Input sizing preset", "ACES Gamut Compress"]

CLIP_COLORS = [
    "Orange", "Apricot", "Yellow", "Lime", "Olive", "Green",
    "Teal", "Navy", "Blue", "Purple", "Violet", "Pink",
    "Tan", "Beige", "Brown", "Chocolate",
]
FLAG_COLORS  = ["Red", "Blue", "Green", "Yellow", "Cyan", "Magenta"]
ACES_OPTIONS = ["None", "Standard - LMT"]

KEY_ESCAPE = 16777216
KEY_RETURN = 16777220
KEY_ENTER  = 16777221

# ── Resolve context ───────────────────────────────────────────────────────────
# `resolve` and `project` are injected by Resolve at startup.

media_pool = project.GetMediaPool() if project else None

# ── Media pool helpers ────────────────────────────────────────────────────────

def _all_clips(folder):
    clips = list(folder.GetClipList() or [])
    for sub in folder.GetSubFolderList() or []:
        clips.extend(_all_clips(sub))
    return clips

def get_unique_values(condition):
    prop = CONDITION_PROPS.get(condition)
    if not prop or not media_pool:
        return []
    clips  = _all_clips(media_pool.GetRootFolder())
    values = {str(c.GetClipProperty(prop)).strip() for c in clips if c.GetClipProperty(prop)}
    return sorted(values)

def _folder_paths(folder, prefix=""):
    paths = []
    for sub in folder.GetSubFolderList() or []:
        name = sub.GetName()
        path = f"{prefix}/{name}" if prefix else name
        paths.append(path)
        paths.extend(_folder_paths(sub, path))
    return paths

def get_action_values(action):
    if action == "Add to group":
        if not media_pool:
            return []
        return _folder_paths(media_pool.GetRootFolder())
    if action == "Clip color":
        return CLIP_COLORS
    if action == "Flags":
        return FLAG_COLORS
    if action == "Input sizing preset":
        try:
            presets = project.GetInputSizingPresetList()
            if presets:
                return list(presets)
        except Exception:
            pass
        return ["Project", "Custom", "None"]
    if action == "ACES Gamut Compress":
        return ACES_OPTIONS
    return []

def _find_folder(root, path):
    cur = root
    for part in (p for p in path.split("/") if p):
        cur = next(
            (s for s in (cur.GetSubFolderList() or []) if s.GetName() == part),
            None,
        )
        if not cur:
            return None
    return cur

def _apply_action(clip, action, value):
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

def execute_rules(rules):
    active = [r for r in rules if r.get("active", True)]
    if not active or not media_pool:
        return
    all_clips = _all_clips(media_pool.GetRootFolder())
    for rule in active:
        prop     = CONDITION_PROPS.get(rule.get("condition", ""))
        cond_val = rule.get("condition_value", "").strip()
        action   = rule.get("action", "")
        act_val  = rule.get("action_value", "").strip()
        if not all([prop, cond_val, action, act_val]):
            continue
        for clip in all_clips:
            if str(clip.GetClipProperty(prop) or "").strip() == cond_val:
                _apply_action(clip, action, act_val)

# ── Settings I/O ──────────────────────────────────────────────────────────────

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return []
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("rules", [])
    except Exception:
        return []

def save_settings(rules):
    data = [
        {k: v for k, v in r.items() if k != "_id"}
        for r in rules
    ]
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"rules": data}, f, indent=2, ensure_ascii=False)

# ── UI helpers ────────────────────────────────────────────────────────────────

_id_counter = 0

def _next_id():
    global _id_counter
    _id_counter += 1
    return _id_counter


def _build_window(rules):
    """Create a fresh window for the current rules list."""
    rule_rows = []
    for r in rules:
        rid = r["_id"]
        rule_rows.append(
            ui.HGroup({"Weight": 0, "Spacing": 6}, [
                ui.ComboBox({"ID": f"cond_{rid}",    "Weight": 1}),
                ui.ComboBox({"ID": f"condval_{rid}", "Weight": 1}),
                ui.Label(  {"Text": "→", "Weight": 0}),
                ui.ComboBox({"ID": f"act_{rid}",     "Weight": 1}),
                ui.ComboBox({"ID": f"actval_{rid}",  "Weight": 1}),
                ui.CheckBox({"ID": f"active_{rid}", "Text": "Active",
                             "Checked": r.get("active", True), "Weight": 0}),
                ui.Button(  {"ID": f"remove_{rid}", "Text": "✕", "Weight": 0}),
            ])
        )

    if not rule_rows:
        rule_rows = [
            ui.Label({"Text": 'No rules defined. Click "+ Add Rule" to begin.',
                      "Alignment": {"AlignHCenter": True}, "Weight": 0}),
        ]

    return dispatcher.AddWindow(
        {
            "ID":          WIN_ID,
            "WindowTitle": "Media Import Rules",
            "Geometry":    [100, 100, 960, max(148, 108 + len(rules) * 46)],
            "Events":      {"KeyPress": True},
        },
        [
            ui.VGroup({"Spacing": 8, "Margin": 10}, [
                # ── Toolbar ────────────────────────────────────────────────
                ui.HGroup({"Weight": 0, "Spacing": 6}, [
                    ui.Button({"ID": "btn_add", "Text": "+ Add Rule", "Weight": 0}),
                    ui.HGap(),
                ]),
                # ── Rule rows ──────────────────────────────────────────────
                ui.VGroup({"Spacing": 4}, rule_rows),
                ui.VGap(),
                # ── Bottom bar ─────────────────────────────────────────────
                ui.HGroup({"Weight": 0, "Spacing": 6}, [
                    ui.Button({"ID": "btn_exit",    "Text": "Save and Exit",    "Weight": 0}),
                    ui.Button({"ID": "btn_execute", "Text": "Save and Execute", "Weight": 0}),
                    ui.HGap(),
                ]),
            ]),
        ],
    )


def _populate_combos(win, rules):
    items = win.GetItems()
    for r in rules:
        rid = r["_id"]

        # Condition
        cb = items[f"cond_{rid}"]
        cb.Clear()
        for c in CONDITIONS:
            cb.AddItem(c)
        cb.CurrentIndex = CONDITIONS.index(r["condition"]) if r["condition"] in CONDITIONS else 0

        # Condition value
        cond_vals = get_unique_values(r["condition"])
        cb = items[f"condval_{rid}"]
        cb.Clear()
        for v in cond_vals:
            cb.AddItem(v)
        if r["condition_value"] in cond_vals:
            cb.CurrentIndex = cond_vals.index(r["condition_value"])

        # Action
        cb = items[f"act_{rid}"]
        cb.Clear()
        for a in ACTIONS:
            cb.AddItem(a)
        cb.CurrentIndex = ACTIONS.index(r["action"]) if r["action"] in ACTIONS else 0

        # Action value
        act_vals = get_action_values(r["action"])
        cb = items[f"actval_{rid}"]
        cb.Clear()
        for v in act_vals:
            cb.AddItem(v)
        if r["action_value"] in act_vals:
            cb.CurrentIndex = act_vals.index(r["action_value"])


def _collect_rules(win, rules):
    """Read current widget state back into the rules list."""
    items = win.GetItems()
    for r in rules:
        rid = r["_id"]
        r["condition"]       = items[f"cond_{rid}"].CurrentText
        r["condition_value"] = items[f"condval_{rid}"].CurrentText
        r["action"]          = items[f"act_{rid}"].CurrentText
        r["action_value"]    = items[f"actval_{rid}"].CurrentText
        r["active"]          = items[f"active_{rid}"].Checked


def _setup_handlers(win, rules):
    items = win.GetItems()

    def signal(act):
        _collect_rules(win, rules)
        global _pending_action
        _pending_action = act
        dispatcher.ExitLoop()

    win.On[WIN_ID].Close          = lambda ev: signal("close")
    win.On["btn_add"].Clicked     = lambda ev: signal("add")
    win.On["btn_exit"].Clicked    = lambda ev: signal("exit")
    win.On["btn_execute"].Clicked = lambda ev: signal("execute")

    def on_key(ev):
        k = ev.get("Key", 0)
        if k == KEY_ESCAPE:
            signal("exit")
        elif k in (KEY_RETURN, KEY_ENTER):
            signal("execute")

    win.On[WIN_ID].KeyPress = on_key

    for r in rules:
        rid = r["_id"]

        # Remove button
        def _make_remove(r_id):
            return lambda ev: signal(f"remove_{r_id}")

        # Condition changed → repopulate condition-value combo in place
        def _make_cond_changed(r_id):
            def handler(ev):
                new_cond = items[f"cond_{r_id}"].CurrentText
                cb = items[f"condval_{r_id}"]
                cb.Clear()
                vals = get_unique_values(new_cond)
                for v in vals:
                    cb.AddItem(v)
                for rule in rules:
                    if rule["_id"] == r_id:
                        rule["condition"]       = new_cond
                        rule["condition_value"] = vals[0] if vals else ""
                        break
            return handler

        # Action changed → repopulate action-value combo in place
        def _make_act_changed(r_id):
            def handler(ev):
                new_act = items[f"act_{r_id}"].CurrentText
                cb = items[f"actval_{r_id}"]
                cb.Clear()
                vals = get_action_values(new_act)
                for v in vals:
                    cb.AddItem(v)
                for rule in rules:
                    if rule["_id"] == r_id:
                        rule["action"]       = new_act
                        rule["action_value"] = vals[0] if vals else ""
                        break
            return handler

        win.On[f"remove_{rid}"].Clicked              = _make_remove(rid)
        win.On[f"cond_{rid}"].CurrentIndexChanged    = _make_cond_changed(rid)
        win.On[f"act_{rid}"].CurrentIndexChanged     = _make_act_changed(rid)


# ── Main loop ─────────────────────────────────────────────────────────────────

_pending_action = None
_win            = None

def _run_window(rules):
    """Build, show, and run the window; return the pending action string."""
    global _win, _pending_action
    _pending_action = None
    if _win:
        _win.Hide()
    _win = _build_window(rules)
    _populate_combos(_win, rules)
    _setup_handlers(_win, rules)
    _win.Show()
    dispatcher.RunLoop()
    return _pending_action


# Seed rules from saved JSON, assigning internal _id to each
rules = []
for _rd in load_settings():
    _rd["_id"] = _next_id()
    rules.append(_rd)

while True:
    action = _run_window(rules)

    if action in ("exit", "close", None):
        if action == "exit":
            save_settings(rules)
        break

    elif action == "execute":
        save_settings(rules)
        execute_rules(rules)
        break

    elif action == "add":
        cond      = CONDITIONS[0]
        act       = ACTIONS[0]
        cond_vals = get_unique_values(cond)
        act_vals  = get_action_values(act)
        rules.append({
            "_id":             _next_id(),
            "condition":       cond,
            "condition_value": cond_vals[0] if cond_vals else "",
            "action":          act,
            "action_value":    act_vals[0]  if act_vals  else "",
            "active":          True,
        })

    elif action and action.startswith("remove_"):
        r_id  = int(action[len("remove_"):])
        rules = [r for r in rules if r["_id"] != r_id]
