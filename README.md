
# Media Import Rules

A DaVinci Resolve Workflow Integration plugin that applies bulk metadata-based actions to clips at import time.

Inspired by Filmlight [Daylight](https://www.filmlight.ltd.uk/products/daylight/overview_dl.php)'s Media Import Rules menu, this plugin offers a similar rule-based approach — albeit more limited — directly inside DaVinci Resolve, with no external dependencies.

<img width="1072" height="454" alt="Capture d’écran 2026-04-27 à 19 59 28" src="https://github.com/user-attachments/assets/86df6e28-e6af-431b-ba2d-8476a3b72d16" />
---

## Overview

Media Import Rules lets you define rules of the form:

> **If** [condition] **is** [value] **→** [action] [value]

Each rule can optionally add a second condition (AND logic). Rules are saved between sessions and can be toggled active/inactive individually.

---

## Requirements

- DaVinci Resolve 18 or higher
- No external Python packages required

---

## Installation

Copy `MediaImportRules.py` into the Workflow Integration Plugins folder:

**macOS:**
```
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/
```

**Windows:**
```
%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\
```

**Linux:**
```
~/.local/share/DaVinciResolve/Workflow Integration Plugins/
```

Then restart DaVinci Resolve and launch the plugin from:

```
Workspace → Workflow Integrations → MediaImportRules
```

---

## Usage

### Adding rules

Click **+ Add Rule** to append a new rule row. Each row contains:

- **Condition selector** — the clip metadata property to evaluate
- **Condition value** — the value to match (populated dynamically from clips in the Media Pool)
- **And checkbox** — when checked, adds a second condition that must also match
- **Action selector** — the operation to perform on matching clips
- **Action value** — the target value for the action
- **Active checkbox** — enables or disables the rule without deleting it
- **✕ button** — removes the rule

### Saving and executing

| Button / Key | Behaviour |
|---|---|
| **Save and Exit** | Saves rules to disk and closes the window |
| **Save and Execute** | Saves rules, closes the window, then applies all active rules |
| **Escape** | Save and Exit |
| **Return / Enter** | Save and Execute |

Rules are stored in `MediaImportRules.json` alongside the plugin file.

---

## Conditions

| Condition | Clip property |
|---|---|
| Resolution | `Resolution` |
| Shot Frame Rate | `FPS` |
| Video Codec | `Video Codec` |
| Camera # | `Camera #` |
| Camera Type | `Camera Type` |

Condition values are fetched dynamically from all clips in the Media Pool at plugin launch.

---

## Actions

| Action | Description |
|---|---|
| **Add to group** | Assigns matching timeline items to a Color Group (values fetched from the project's Color Groups) |
| **Clip color** | Sets the clip color on matching Media Pool items |
| **Flags** | Adds a flag color to matching Media Pool items |
| **Pixel aspect ratio** | Sets the PAR on matching Media Pool items — fixed list: `Square`, `1.25`, `1.33`, `1.5`, `1.8`, `2.0` |

**Add to group** operates on timeline items across all timelines in the project. All other actions operate on Media Pool items directly.

---

## Settings

Rules are persisted to:

**macOS:**
```
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/MediaImportRules.json
```

**Windows:**
```
%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\MediaImportRules.json
```

---

## Current Limitations

- Condition values are scanned once at launch. If new clips are added to the Media Pool after the plugin opens, close and reopen the plugin to refresh the lists.
- AND logic supports a maximum of two conditions per rule.
