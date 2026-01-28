# plugins/breakable.py
import time

CHAR = "B"
DEFAULT_STAND = 1.0

# --- Textures ---
# ▓ = Solid / Healthy
# ▒ = Cracked / Reforming
# ░ = Broken / Ghost
TEX_SOLID = "▓"
TEX_MID   = "▒"
TEX_BROKEN = "░"

# Global state tracker to sync physics with rendering
_STATE = {}
_CURRENT_LEVEL = "<start>"

def _now(): return time.time()

def _get(level, x, y):
    # Normalize keys
    lvl = str(level) if level is not None else "<unknown>"
    key = (lvl, int(x), int(y))

    now = _now()
    if key not in _STATE:
        _STATE[key] = {
            "accum": 0.0,
            "stand_time": DEFAULT_STAND,
            "removed": False,
            "last_touch": 0.0,
            "last_frame": now
        }
    return _STATE[key]

# --- runtime ---

def runtime_solid(grid, x, y):
    """
    Called by the physics engine.
    Returns True if solid, False if air.
    """
    ix, iy = int(x), int(y)

    # Safety bounds check
    if not (0 <= iy < len(grid) and 0 <= ix < len(grid[0])):
        return False

    # If the grid doesn't have our char, it's not our business
    if grid[iy][ix] != CHAR:
        return False

    # Check our internal state
    ent = _get(_CURRENT_LEVEL, ix, iy)

    # IF REMOVED, NO COLLISION. PERIOD.
    if ent["removed"]:
        return False

    return True

def on_reset(game_state):
    global _CURRENT_LEVEL
    level = game_state.get("level", "<level>")
    _CURRENT_LEVEL = level

    # Reset all blocks to healthy on level start
    for k, ent in list(_STATE.items()):
        lvl, bx, by = k
        if str(lvl) == str(level):
            ent["removed"] = False
            ent["accum"] = 0.0
            ent["last_frame"] = _now()

def on_player_supported(game_state, player_state, tx, ty, ctx):
    global _CURRENT_LEVEL
    level = game_state.get("level", "<level>")
    _CURRENT_LEVEL = level

    grid = game_state.get("grid")
    bx = int(tx); by = int(ty)

    if by < 0 or by >= len(grid) or bx < 0 or bx >= len(grid[0]): return
    if grid[by][bx] != CHAR: return

    ent = _get(level, bx, by)

    # If it's removed, the physics engine shouldn't have let us stand here.
    # But if we somehow glitch onto it, we ignore it.
    if ent["removed"]: return

    dt = 0.016
    if isinstance(ctx, dict) and "dt" in ctx:
        try: dt = float(ctx["dt"])
        except: pass

    # --- DAMAGE LOGIC ---
    ent["accum"] += dt
    ent["last_touch"] = _now()

    limit = ent.get("stand_time", DEFAULT_STAND)
    if ent["accum"] >= limit:
        ent["removed"] = True
        # We do NOT remove the char from grid[][], keeping the ID for regeneration.

def get_display_char(grid, plats, x, y, level_name):
    global _CURRENT_LEVEL
    _CURRENT_LEVEL = level_name

    ix, iy = int(x), int(y)
    if not (0 <= iy < len(grid) and 0 <= ix < len(grid[0])): return ' '

    # Only render logic for our character
    if grid[iy][ix] != CHAR: return grid[iy][ix]

    ent = _get(level_name, ix, iy)
    limit = ent.get("stand_time", DEFAULT_STAND)
    now = _now()

    # Time delta calculation
    delta = now - ent["last_frame"]
    ent["last_frame"] = now
    if delta > 0.1: delta = 0.1

    # --- REGENERATION LOGIC ---
    time_since_touch = now - ent["last_touch"]

    # Wait 2 seconds before healing starts
    if time_since_touch > 2.0 and ent["accum"] > 0:
        # Heal speed: 0.5x
        ent["accum"] = max(0.0, ent["accum"] - (delta * 0.5))

        # Only solidify if FULLY healed (accum == 0)
        if ent["removed"] and ent["accum"] <= 0.0:
            ent["removed"] = False
            ent["accum"] = 0.0

    # --- VISUALS ---
    # Calculate how damaged it is (0.0 = Healthy, 1.0 = Broken)
    pct = max(0.0, min(1.0, ent["accum"] / limit))

    if ent["removed"]:
        # GHOST STATE (Regenerating)
        # It visually transitions from Light (Empty) -> Mid (Reforming)
        # But maintains "removed" status so you fall through.
        if pct > 0.5:
            return TEX_BROKEN  # ░ (Still very broken)
        else:
            return TEX_MID     # ▒ (Almost formed, but still ghost)

    else:
        # SOLID STATE (Standing)
        if pct < 0.3:
            return TEX_SOLID   # ▓ (Healthy)
        else:
            return TEX_MID     # ▒ (Cracking)

# --- editor hooks ---

def editor_on_context(editor, gx, gy, get_string_input):
    level = editor.meta.get('title', editor.filename)
    ent = _get(level, gx, gy)
    curr = ent.get("stand_time", DEFAULT_STAND)
    val = get_string_input("Break Time (s)", str(curr))
    try:
        ent["stand_time"] = float(val)
        editor.msg = f"Timer set to {val}s"
    except:
        editor.msg = "Invalid value"

def editor_on_paint(editor, x, y):
    return {"char": CHAR, "color": "BLUE"}

def register():
    return {
        "char": CHAR,
        "name": "Breakable Block",
        "editor": {
            "display_char": TEX_SOLID,
            "brush_name": "BREAKABLE",
            "on_paint": editor_on_paint,
            "on_context": editor_on_context,
            "hotkey": "b",
            "color": "BLUE"
        },
        "runtime": {
            "solid": runtime_solid,
            "deadly": False,
            "on_player_supported": on_player_supported,
            "on_player_death": on_reset,
            "on_reset": on_reset,
            "get_display_char": get_display_char,
            "display_char": TEX_SOLID
        }
    }
