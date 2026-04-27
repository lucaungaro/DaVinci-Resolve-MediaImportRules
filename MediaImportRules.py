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
    "Input sizing preset",
    "Pixel aspect ratio",
    # "ACES Gamut Compress",   # standby — API investigation pending
]

PAR_VALUES = ["Square", "1.25", "1.33", "1.5", "1.8", "2.0"]

CLIP_COLORS = [
    "Orange", "Apricot", "Yellow", "Lime", "Olive", "Green",
    "Teal", "Navy", "Blue", "Purple", "Violet", "Pink",
    "Tan", "Beige", "Brown", "Chocolate",
]
FLAG_COLORS = [
    "Blue", "Cyan", "Green", "Yellow", "Orange", "Red",
    "Pink", "Purple", "Fuchsia", "Rose", "Lavender", "Sky",
    "Mint", "Lemon", "Sand", "Cocoa", "Cream", "White",
]
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

def _fetch_input_sizing_presets():
    """
    Scan every clip in the media pool and return the sorted unique non-empty
    values of GetClipProperty("Input Sizing Preset").
    """
    if not media_pool:
        return []
    clips  = _all_clips(media_pool.GetRootFolder())
    values = {str(c.GetClipProperty("Input Sizing Preset") or "").strip() for c in clips}
    values.discard("")
    return sorted(values)

# ── Media pool / timeline helpers ─────────────────────────────────────────────

def _all_clips(folder):
    clips = list(folder.GetClipList() or [])
    for sub in folder.GetSubFolderList() or []:
        clips.extend(_all_clips(sub))
    return clips

def _all_timeline_items():
    """All video TimelineItems across every track of every timeline in the project."""
    if not project:
        return []
    items = []
    for i in range(1, project.GetTimelineCount() + 1):
        timeline = project.GetTimelineByIndex(i)
        if not timeline:
            continue
        for t in range(1, timeline.GetTrackCount("video") + 1):
            items.extend(timeline.GetItemListInTrack("video", t) or [])
    return items

# Populated at startup; read-only after that.
_color_groups         = _fetch_color_groups()
_input_sizing_presets = _fetch_input_sizing_presets()


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
    if action == "Input sizing preset":
        return _input_sizing_presets
    if action == "Pixel aspect ratio":
        return PAR_VALUES
    # if action == "ACES Gamut Compress":  # standby
    #     return ACES_OPTIONS
    return []

# ── Rule execution ────────────────────────────────────────────────────────────

def _matches(item, rule):
    """True if item (MediaPoolItem) satisfies all conditions in rule."""
    prop     = CONDITION_PROPS.get(rule.get("condition", ""))
    cond_val = rule.get("condition_value", "").strip()
    if not prop or not cond_val:
        return False
    if str(item.GetClipProperty(prop) or "").strip() != cond_val:
        return False
    if rule.get("and_condition", False):
        prop2     = CONDITION_PROPS.get(rule.get("condition2", ""))
        cond_val2 = rule.get("condition2_value", "").strip()
        if prop2 and cond_val2:
            if str(item.GetClipProperty(prop2) or "").strip() != cond_val2:
                return False
    return True

def _rule_label(rule):
    cond_val = rule.get("condition_value", "")
    action   = rule.get("action", "")
    act_val  = rule.get("action_value", "")
    if rule.get("and_condition", False):
        c2 = rule.get("condition2", "")
        v2 = rule.get("condition2_value", "")
        return f"{rule.get('condition')} is {cond_val!r} AND {c2} is {v2!r} → {action} = {act_val}"
    return f"{rule.get('condition')} is {cond_val!r} → {action} = {act_val}"

def execute_rules(rules):
    active = [r for r in rules if r.get("active", True)]
    if not active:
        return

    ti_items = _all_timeline_items()
    mp_clips = _all_clips(media_pool.GetRootFolder()) if media_pool else []

    for rule in active:
        action  = rule.get("action", "")
        act_val = rule.get("action_value", "").strip()

        if not all([rule.get("condition"), rule.get("condition_value"), action, act_val]):
            continue

        label = _rule_label(rule)

        if action == "Add to group":
            cg = next((g for g in _color_groups if g.GetName() == act_val), None)
            if not cg:
                continue
            for ti in ti_items:
                mpi = ti.GetMediaPoolItem()
                if mpi and _matches(mpi, rule):
                    ti.AssignToColorGroup(cg)
                    print(f"[MediaImportRules] Rule: {label} | Item: {ti.GetName()!r} | Action: assigned to color group {act_val}")

        elif action == "Clip color":
            for clip in mp_clips:
                if _matches(clip, rule):
                    clip.SetClipColor(act_val)
                    print(f"[MediaImportRules] Rule: {label} | Item: {clip.GetName()!r} | Action: set clip color to {act_val}")

        elif action == "Flags":
            for clip in mp_clips:
                if _matches(clip, rule):
                    clip.AddFlag(act_val)
                    print(f"[MediaImportRules] Rule: {label} | Item: {clip.GetName()!r} | Action: added flag {act_val}")

        elif action == "Input sizing preset":
            for clip in mp_clips:
                if _matches(clip, rule):
                    clip.SetClipProperty("Input Sizing Preset", act_val)
                    print(f"[MediaImportRules] Rule: {label} | Item: {clip.GetName()!r} | Action: set input sizing preset to {act_val}")

        elif action == "Pixel aspect ratio":
            for clip in mp_clips:
                if _matches(clip, rule):
                    clip.SetClipProperty("PAR", act_val)
                    print(f"[MediaImportRules] Rule: {label} | Item: {clip.GetName()!r} | Action: set PAR to {act_val}")

        # elif action == "ACES Gamut Compress":  # standby
        #     for clip in mp_clips:
        #         if _matches(clip, rule):
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
        rid     = r["_id"]
        has_and = r.get("and_condition", False)

        if not has_and:
            # Single-condition row
            rule_rows.append(
                ui.HGroup({"Weight": 0, "Spacing": 6}, [
                    ui.ComboBox({"ID": f"cond_{rid}",    "Weight": 1}),
                    ui.Label(  {"Text": "is",            "Weight": 0}),
                    ui.ComboBox({"ID": f"condval_{rid}", "Weight": 1}),
                    ui.CheckBox({"ID": f"and_{rid}", "Text": "And",
                                 "Checked": False, "Weight": 0}),
                    ui.Label(  {"Text": "→",             "Weight": 0}),
                    ui.ComboBox({"ID": f"act_{rid}",     "Weight": 1}),
                    ui.ComboBox({"ID": f"actval_{rid}",  "Weight": 1}),
                    ui.CheckBox({"ID": f"active_{rid}", "Text": "Active",
                                 "Checked": r.get("active", True), "Weight": 0}),
                    ui.Button(  {"ID": f"remove_{rid}", "Text": "✕",
                                 "Weight": 0, "MaximumSize": [28, 28]}),
                ])
            )
        else:
            # Two-condition rows: first row holds cond1 + And checkbox,
            # second row is indented and holds cond2 + action.
            rule_rows.append(
                ui.VGroup({"Weight": 0, "Spacing": 2}, [
                    ui.HGroup({"Weight": 0, "Spacing": 6}, [
                        ui.ComboBox({"ID": f"cond_{rid}",    "Weight": 1}),
                        ui.Label(  {"Text": "is",            "Weight": 0}),
                        ui.ComboBox({"ID": f"condval_{rid}", "Weight": 1}),
                        ui.CheckBox({"ID": f"and_{rid}", "Text": "And",
                                     "Checked": True, "Weight": 0}),
                        ui.HGap(515),
                    ]),
                    ui.HGroup({"Weight": 0, "Spacing": 6}, [
                        ui.Label({"Text": "", "Weight": 0, "MinimumSize": [32, 0]}),
                        ui.ComboBox({"ID": f"cond2_{rid}",    "Weight": 1}),
                        ui.Label(  {"Text": "is",              "Weight": 0}),
                        ui.ComboBox({"ID": f"cond2val_{rid}",  "Weight": 1}),
                        ui.Label(  {"Text": "→",               "Weight": 0}),
                        ui.ComboBox({"ID": f"act_{rid}",       "Weight": 1}),
                        ui.ComboBox({"ID": f"actval_{rid}",    "Weight": 1}),
                        ui.CheckBox({"ID": f"active_{rid}", "Text": "Active",
                                     "Checked": r.get("active", True), "Weight": 0}),
                        ui.Button(  {"ID": f"remove_{rid}", "Text": "✕",
                                     "Weight": 0, "MaximumSize": [28, 28]}),
                    ]),
                ])
            )

    if not rule_rows:
        rule_rows = [
            ui.Label({"Text": 'No rules defined. Click "+ Add Rule" to begin.',
                      "Alignment": {"AlignHCenter": True}, "Weight": 0}),
        ]

    # Position window near the current cursor so it opens on the active screen.
    try:
        pos = fusion.GetMousePos()
        wx  = max(0, int(pos["x"]) - 480)
        wy  = max(0, int(pos["y"]) - 80)
    except Exception:
        wx, wy = 100, 100

    # Height: title bar (~22 px) + outer margins (20) + spacing (16) + toolbar (28)
    # + bottom bar (28) = ~114 px fixed overhead, plus a small buffer = 130 px base.
    # When empty, the placeholder label counts as one row (28 px).
    row_h = sum(92 if r.get("and_condition", False) else 46 for r in rules)
    row_h = row_h if rules else 28
    win_h = min(600, 130 + row_h)

    return dispatcher.AddWindow(
        {
            "ID":             WIN_ID,
            "WindowTitle":    "Media Import Rules",
            "Geometry":       [wx, wy, 960, win_h],
            "MinimumSize":    [760, 160],
            "WindowFlags":    {"Dialog": True},
            "WindowModality": "ApplicationModal",
            "Events":         {"KeyPress": True},
        },
        [
            ui.VGroup({"Spacing": 8, "Margin": 10}, [
                # ── Toolbar ────────────────────────────────────────────────
                ui.HGroup({"Weight": 0, "Spacing": 6}, [
                    ui.Button({"ID": "btn_add", "Text": "+ Add Rule", "Weight": 0}),
                    ui.HGap(),
                ]),
                # ── Rule rows ─────────────────────────────────────────────
                ui.VGroup({"Spacing": 4, "Weight": 0}, rule_rows),
                # ── Bottom bar (always pinned at the bottom) ───────────────
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

        # ── Condition 1 ──────────────────────────────────────────────────────
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

        # ── Condition 2 (only when "and" row is present) ─────────────────────
        if r.get("and_condition", False):
            cb = items[f"cond2_{rid}"]
            cb.Clear()
            for c in CONDITIONS:
                cb.AddItem(c)
            cond2 = r.get("condition2", CONDITIONS[0])
            cb.CurrentIndex = CONDITIONS.index(cond2) if cond2 in CONDITIONS else 0

            cond2_vals = get_unique_values(r.get("condition2", CONDITIONS[0]))
            cb = items[f"cond2val_{rid}"]
            cb.Clear()
            for v in cond2_vals:
                cb.AddItem(v)
            if r.get("condition2_value", "") in cond2_vals:
                cb.CurrentIndex = cond2_vals.index(r["condition2_value"])

        # ── Action ───────────────────────────────────────────────────────────
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
        r["and_condition"]   = items[f"and_{rid}"].Checked
        r["action"]          = items[f"act_{rid}"].CurrentText
        r["action_value"]    = items[f"actval_{rid}"].CurrentText
        r["active"]          = items[f"active_{rid}"].Checked
        # cond2 widgets only exist when the layout was built with and=True
        if f"cond2_{rid}" in items:
            r["condition2"]       = items[f"cond2_{rid}"].CurrentText
            r["condition2_value"] = items[f"cond2val_{rid}"].CurrentText


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

        def _make_and_toggled(r_id):
            return lambda ev: signal(f"toggle_and_{r_id}")

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
                            cb.CurrentIndex = vals.index(rule["condition_value"])
                        else:
                            rule["condition"]       = new_cond
                            rule["condition_value"] = vals[0] if vals else ""
                        break
            return handler

        def _make_cond2_changed(r_id):
            def handler(ev):
                new_cond2 = items[f"cond2_{r_id}"].CurrentText
                cb = items[f"cond2val_{r_id}"]
                cb.Clear()
                vals = get_unique_values(new_cond2)
                for v in vals:
                    cb.AddItem(v)
                for rule in rules:
                    if rule["_id"] == r_id:
                        if new_cond2 == rule.get("condition2") and rule.get("condition2_value") in vals:
                            cb.CurrentIndex = vals.index(rule["condition2_value"])
                        else:
                            rule["condition2"]       = new_cond2
                            rule["condition2_value"] = vals[0] if vals else ""
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
                            cb.CurrentIndex = vals.index(rule["action_value"])
                        else:
                            rule["action"]       = new_act
                            rule["action_value"] = vals[0] if vals else ""
                        break
            return handler

        win.On[f"remove_{rid}"].Clicked           = _make_remove(rid)
        win.On[f"and_{rid}"].Clicked              = _make_and_toggled(rid)
        win.On[f"cond_{rid}"].CurrentIndexChanged = _make_cond_changed(rid)
        win.On[f"act_{rid}"].CurrentIndexChanged  = _make_act_changed(rid)
        if r.get("and_condition", False):
            win.On[f"cond2_{rid}"].CurrentIndexChanged = _make_cond2_changed(rid)


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
        if _win:
            _win.Hide()
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
            "and_condition":   False,
            "condition2":      CONDITIONS[0],
            "condition2_value": cond_vals[0] if cond_vals else "",
            "action":          act,
            "action_value":    act_vals[0] if act_vals else "",
            "active":          True,
        })

    elif action and action.startswith("remove_"):
        r_id  = int(action[len("remove_"):])
        rules = [r for r in rules if r["_id"] != r_id]

    elif action and action.startswith("toggle_and_"):
        r_id = int(action[len("toggle_and_"):])
        for r in rules:
            if r["_id"] == r_id:
                if r.get("and_condition", False) and not r.get("condition2"):
                    # "And" just turned on — set default second condition.
                    cond2_vals = get_unique_values(CONDITIONS[0])
                    r["condition2"]       = CONDITIONS[0]
                    r["condition2_value"] = cond2_vals[0] if cond2_vals else ""
                break
        # Loop continues → window rebuilds with updated layout.
