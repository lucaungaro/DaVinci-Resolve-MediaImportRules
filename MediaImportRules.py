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

# ── Settings file ─────────────────────────────────────────────────────────────

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

ACTIONS = [
    "Add to group",
    "Clip color",
    "Flags",
    # "Input sizing preset",   # standby — API investigation pending
    # "ACES Gamut Compress",   # standby — API investigation pending
]

CLIP_COLORS = [
    "Orange", "Apricot", "Yellow", "Lime", "Olive", "Green",
    "Teal", "Navy", "Blue", "Purple", "Violet", "Pink",
    "Tan", "Beige", "Brown", "Chocolate",
]
FLAG_COLORS  = ["Red", "Blue", "Green", "Yellow", "Cyan", "Magenta"]
# ACES_OPTIONS = ["None", "Standard - LMT"]  # standby

KEY_ESCAPE = 16777216
KEY_RETURN = 16777220
KEY_ENTER  = 16777221

# ── Resolve context ───────────────────────────────────────────────────────────
# `resolve` and `project` are injected by Resolve at startup.

media_pool = project.GetMediaPool() if project else None

# ── Lists fetched once at plugin launch ───────────────────────────────────────

def _fetch_color_groups():
    """Return list of ColorGroup objects from the current project."""
    if not project:
        return []
    return list(project.GetColorGroupsList() or [])

# def _fetch_input_sizing_presets():  # standby — API investigation pending
#     ...

# Populated at startup; read-only after that.
_color_groups = _fetch_color_groups()  # [ColorGroup, ...]
# _input_sizing_presets = _fetch_input_sizing_presets()  # standby

# ── Media pool / timeline helpers ─────────────────────────────────────────────

def _all_clips(folder):
    clips = list(folder.GetClipList() or [])
    for sub in folder.GetSubFolderList() or []:
        clips.extend(_all_clips(sub))
    return clips

def _all_timeline_items():
    """All video TimelineItems across every track of the current timeline."""
    timeline = project.GetCurrentTimeline() if project else None
    if not timeline:
        return []
    items = []
    for i in range(1, timeline.GetTrackCount("video") + 1):
        items.extend(timeline.GetItemListInTrack("video", i) or [])
    return items

def get_unique_values(condition):
    prop = CONDITION_PROPS.get(condition)
    if not prop or not media_pool:
        return []
    clips  = _all_clips(media_pool.GetRootFolder())
    values = {str(c.GetClipProperty(prop)).strip() for c in clips if c.GetClipProperty(prop)}
    return sorted(values)

def get_action_values(action):
    if action == "Add to group":
        return [cg.GetName() for cg in _color_groups]
    if action == "Clip color":
        return CLIP_COLORS
    if action == "Flags":
        return FLAG_COLORS
    # if action == "Input sizing preset":  # standby
    #     return _input_sizing_presets
    # if action == "ACES Gamut Compress":  # standby
    #     return ACES_OPTIONS
    return []

# ── Rule execution ────────────────────────────────────────────────────────────

def execute_rules(rules):
    active = [r for r in rules if r.get("active", True)]
    if not active:
        return

    # Collect clips / timeline items once, reuse across all rules.
    mp_clips = _all_clips(media_pool.GetRootFolder()) if media_pool else []
    ti_items = _all_timeline_items()

    for rule in active:
        prop     = CONDITION_PROPS.get(rule.get("condition", ""))
        cond_val = rule.get("condition_value", "").strip()
        action   = rule.get("action", "")
        act_val  = rule.get("action_value", "").strip()

        if not all([prop, cond_val, action, act_val]):
            continue

        if action == "Add to group":
            # ColorGroup.AssignToColorGroup() lives on TimelineItem.
            cg = next((g for g in _color_groups if g.GetName() == act_val), None)
            if not cg:
                continue
            for ti in ti_items:
                mpi = ti.GetMediaPoolItem()
                if mpi and str(mpi.GetClipProperty(prop) or "").strip() == cond_val:
                    ti.AssignToColorGroup(cg)

        elif action == "Clip color":
            for clip in mp_clips:
                if str(clip.GetClipProperty(prop) or "").strip() == cond_val:
                    clip.SetClipColor(act_val)

        elif action == "Flags":
            for clip in mp_clips:
                if str(clip.GetClipProperty(prop) or "").strip() == cond_val:
                    clip.AddFlag(act_val)

        # elif action == "Input sizing preset":  # standby
        #     for clip in mp_clips:
        #         if str(clip.GetClipProperty(prop) or "").strip() == cond_val:
        #             clip.SetClipProperty("Input Sizing Preset", act_val)

        # elif action == "ACES Gamut Compress":  # standby
        #     for clip in mp_clips:
        #         if str(clip.GetClipProperty(prop) or "").strip() == cond_val:
        #             clip.SetClipProperty("ACES GC Preset", act_val)

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
    data = [{k: v for k, v in r.items() if k != "_id"} for r in rules]
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"rules": data}, f, indent=2, ensure_ascii=False)

# ── UI ────────────────────────────────────────────────────────────────────────

_id_counter = 0

def _next_id():
    global _id_counter
    _id_counter += 1
    return _id_counter


def _build_window(rules):
    rule_rows = []
    for r in rules:
        rid = r["_id"]
        rule_rows.append(
            ui.HGroup({"Weight": 0, "Spacing": 6}, [
                ui.ComboBox({"ID": f"cond_{rid}",    "Weight": 1}),
                ui.Label(  {"Text": "is", "Weight": 0}),
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
                ui.HGroup({"Weight": 0, "Spacing": 6}, [
                    ui.Button({"ID": "btn_add", "Text": "+ Add Rule", "Weight": 0}),
                    ui.HGap(),
                ]),
                ui.VGroup({"Spacing": 4}, rule_rows),
                ui.VGap(),
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

        cb = items[f"cond_{rid}"]
        cb.Clear()
        for c in CONDITIONS:
            cb.AddItem(c)
        cb.CurrentIndex = CONDITIONS.index(r["condition"]) if r["condition"] in CONDITIONS else 0

        cond_vals = get_unique_values(r["condition"])
        cb = items[f"condval_{rid}"]
        cb.Clear()
        for v in cond_vals:
            cb.AddItem(v)
        if r["condition_value"] in cond_vals:
            cb.CurrentIndex = cond_vals.index(r["condition_value"])

        cb = items[f"act_{rid}"]
        cb.Clear()
        for a in ACTIONS:
            cb.AddItem(a)
        cb.CurrentIndex = ACTIONS.index(r["action"]) if r["action"] in ACTIONS else 0

        act_vals = get_action_values(r["action"])
        cb = items[f"actval_{rid}"]
        cb.Clear()
        for v in act_vals:
            cb.AddItem(v)
        if r["action_value"] in act_vals:
            cb.CurrentIndex = act_vals.index(r["action_value"])


def _collect_rules(win, rules):
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

        def _make_remove(r_id):
            return lambda ev: signal(f"remove_{r_id}")

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
                        if new_cond == rule["condition"] and rule["condition_value"] in vals:
                            # Event fired during init (condition unchanged): restore saved value.
                            cb.CurrentIndex = vals.index(rule["condition_value"])
                        else:
                            # User picked a different condition: reset to first item.
                            rule["condition"]       = new_cond
                            rule["condition_value"] = vals[0] if vals else ""
                        break
            return handler

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
                        if new_act == rule["action"] and rule["action_value"] in vals:
                            # Event fired during init (action unchanged): restore saved value.
                            cb.CurrentIndex = vals.index(rule["action_value"])
                        else:
                            # User picked a different action: reset to first item.
                            rule["action"]       = new_act
                            rule["action_value"] = vals[0] if vals else ""
                        break
            return handler

        win.On[f"remove_{rid}"].Clicked           = _make_remove(rid)
        win.On[f"cond_{rid}"].CurrentIndexChanged = _make_cond_changed(rid)
        win.On[f"act_{rid}"].CurrentIndexChanged  = _make_act_changed(rid)


# ── Main loop ─────────────────────────────────────────────────────────────────

_pending_action = None
_win            = None

def _run_window(rules):
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
