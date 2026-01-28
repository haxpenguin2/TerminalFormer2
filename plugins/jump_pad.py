# plugins/jump_pad.py
"""
Jump Pad plugin
- Placeable char: -
- Editor: press E on a pad to set its boost (stored in block_overrides as {"boost": <float>})
- Runtime: non-solid; fires on on_player_touch to apply vertical velocity ("vy")
"""

import time

# We use '-' as the default char
CHAR = "≡"
DEFAULT_BOOST = -40.0
COOLDOWN = 0.12
_STATE = {}

def _now():
    return time.time()

def _key(level, x, y):
    return (str(level), int(x), int(y))

def _get(level, x, y):
    k = _key(level, x, y)
    if k not in _STATE:
        _STATE[k] = {"last_fired": 0.0}
    return _STATE[k]

# ---------------- Runtime ----------------

def runtime_solid(grid, x, y):
    if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
        return False
    return grid[y][x] == CHAR

def on_player_touch(game_state, player_state, tx, ty, ctx):
    level = game_state.get("level", "<level>")
    ent = _get(level, tx, ty)
    now = _now()
    if now - ent["last_fired"] < COOLDOWN:
        return {}
    ent["last_fired"] = now

    boost = DEFAULT_BOOST
    overrides = (game_state.get("meta") or {}).get("block_overrides", {})
    ov = overrides.get(f"{tx},{ty}", {})
    try:
        boost = float(ov.get("boost", boost))
    except Exception:
        pass

    try:
        if isinstance(player_state, dict):
            player_state['vy'] = float(boost)
    except Exception:
        pass

    return {"vy": float(boost)}

def on_player_collide(game_state, player_state, tx, ty, ctx):
    return on_player_touch(game_state, player_state, tx, ty, ctx)

def get_display_char(grid, plats, x, y, level_name):
    if not (0 <= y < len(grid) and 0 <= x < len(grid[0])): return ' '
    return CHAR if grid[y][x] == CHAR else grid[y][x]

# ---------------- Editor ----------------

def editor_on_paint(editor, x, y):
    # Added "color": "WHITE" here so it paints with the correct color immediately
    return {"char": CHAR, "color": "WHITE"}

def editor_on_context(editor, gx, gy, get_string_input):
    try:
        default = str((editor.meta.get("block_overrides", {}).get(f"{gx},{gy}", {}) or {}).get("boost", DEFAULT_BOOST))
        if callable(get_string_input):
            val = get_string_input("Jump Boost (negative = up)", default)
        else:
            val = default

        if val is not None and val != "":
            try:
                b = float(val)
                if "block_overrides" not in editor.meta:
                    editor.meta["block_overrides"] = {}
                editor.meta["block_overrides"][f"{gx},{gy}"] = {"boost": b}
                editor.msg = f"Pad boost set to {b}"
            except Exception:
                editor.msg = "Invalid number"
        else:
            editor.msg = "Cancelled"
    except Exception as e:
        try: editor.msg = f"Error: {e}"
        except: pass

# ---------------- Registration ----------------

def register():
    meta = {
        "char": CHAR,
        "name": "Jump Pad",
        "editor": {
            "char": CHAR,
            "display_char": CHAR,
            "brush_name": "JUMP PAD",
            "on_paint": editor_on_paint,
            "on_context": editor_on_context,
            "hotkey": "j",
            "color": "WHITE"  # Added color definition for the palette/cursor
        },
        "runtime": {
            "solid": False,
            "deadly": False,
            "on_player_touch": on_player_touch,
            "on_player_collide": on_player_collide,
            "get_display_char": get_display_char,
            "display_char": CHAR
        }
    }
    return [meta]
