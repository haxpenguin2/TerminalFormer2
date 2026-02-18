# plugins/speed_portal.py
import time

CHAR = ">"
DEFAULT_MULTIPLIER = 2.0
DEFAULT_DURATION = 1.5

# visual char (editor/game)
DISPLAY_CHAR = ">"

# module-level active state so display hooks can expire and restore MOVE_SPEED
_ACTIVE = {
    # structure:
    # "level_name": {"active_until": float, "multiplier": float, "orig_move_speed": float}
}

def _now(): return time.time()

# --- runtime hooks ---

def runtime_solid(grid, x, y):
    """
    Portal is not solid — you pass through it.
    """
    ix, iy = int(x), int(y)
    if not (0 <= iy < len(grid) and 0 <= ix < len(grid[0])):
        return False
    return False

def _set_boost(level, multiplier, duration):
    """
    Activate boost for `level` for `duration` seconds with given multiplier.
    This stores original MOVE_SPEED and writes boosted value to the game's global.
    """
    exp = _now() + float(duration)
    entry = _ACTIVE.get(level)
    # attempt to import main module and read/set MOVE_SPEED
    try:
        import __main__ as main
        cur = getattr(main, "MOVE_SPEED", None)
    except Exception:
        main = None
        cur = None

    if entry is None:
        entry = {"active_until": exp, "multiplier": float(multiplier), "orig_move_speed": cur}
    else:
        # extend expiry if new one lasts longer
        entry["active_until"] = max(entry.get("active_until", 0.0), exp)
        # if new multiplier is larger, adopt it (simple policy)
        entry["multiplier"] = max(entry.get("multiplier", multiplier), float(multiplier))
        # keep orig_move_speed as-is (first recorded)

    _ACTIVE[level] = entry

    # apply global change immediately if we know original
    if main is not None and entry["orig_move_speed"] is not None:
        try:
            main.MOVE_SPEED = entry["orig_move_speed"] * entry["multiplier"]
        except Exception:
            pass

def _maybe_expire(level):
    """
    Check expiry and restore MOVE_SPEED if expired.
    Called from get_display_char (so it runs often enough while the level is rendering).
    """
    entry = _ACTIVE.get(level)
    if not entry: return
    now = _now()
    if now >= entry.get("active_until", 0.0):
        # restore
        try:
            import __main__ as main
            orig = entry.get("orig_move_speed")
            if orig is not None:
                main.MOVE_SPEED = orig
        except Exception:
            pass
        # remove entry
        del _ACTIVE[level]

def on_player_touch(game_state, player_state, tx, ty, plugin_data):
    """
    Called when the player touches the portal tile.
    Activates the speed boost for this level and gives a small immediate velocity nudge.
    """
    level = game_state.get("level", "<level>")
    grid = game_state.get("grid", [])
    h = len(grid); w = len(grid[0]) if h>0 else 0
    if not (0 <= ty < h and 0 <= tx < w):
        return

    if grid[ty][tx] != CHAR:
        return

    # read per-tile overrides if present in level meta
    key = f"{tx},{ty}"
    overrides = game_state.get("meta", {}).get("block_overrides", {})
    cfg = overrides.get(key, {})
    try:
        mult = float(cfg.get("multiplier", DEFAULT_MULTIPLIER))
    except Exception:
        mult = DEFAULT_MULTIPLIER
    try:
        dur = float(cfg.get("duration", DEFAULT_DURATION))
    except Exception:
        dur = DEFAULT_DURATION

    # activate module-level boost state
    _set_boost(level, mult, dur)

    # immediate small nudge to the player's current horizontal velocity so touch feels snappy
    try:
        if "vx" in player_state:
            player_state["vx"] = float(player_state.get("vx", 0.0)) * float(mult)
    except Exception:
        pass

    # nothing to return; the engine will read back vx/vy from the mutated player_state

def get_display_char(grid, plats, x, y, level_name):
    """
    Always render as the portal character. Also expire boosts when this runs (keeps MOVE_SPEED sane).
    """
    # expire any boost for this level if necessary (this runs every render frame for portal tiles)
    try:
        _maybe_expire(level_name)
    except Exception:
        pass

    ix, iy = int(x), int(y)
    if not (0 <= iy < len(grid) and 0 <= ix < len(grid[0])): return ' '
    if grid[iy][ix] != CHAR: return grid[iy][ix]
    return DISPLAY_CHAR

def on_reset(game_state):
    """
    On level reset/teleport, clear any active boost and restore original MOVE_SPEED.
    """
    level = game_state.get("level", "<level>")
    entry = _ACTIVE.get(level)
    if not entry: return

    try:
        import __main__ as main
        orig = entry.get("orig_move_speed")
        if orig is not None:
            main.MOVE_SPEED = orig
    except Exception:
        pass

    try:
        del _ACTIVE[level]
    except KeyError:
        pass

# --- editor hooks ---

def editor_on_context(editor, gx, gy, get_string_input):
    """
    Editor context to change multiplier and duration for this tile.
    Stores values in editor.meta['block_overrides'] keyed by 'x,y'.
    """
    key = f"{gx},{gy}"
    overrides = editor.meta.get("block_overrides", {})
    curr = overrides.get(key, {})
    mult = str(curr.get("multiplier", DEFAULT_MULTIPLIER))
    dur = str(curr.get("duration", DEFAULT_DURATION))

    m_val = get_string_input("Speed multiplier (e.g. 2.0)", mult)
    d_val = get_string_input("Duration seconds (e.g. 1.5)", dur)

    try:
        m_f = float(m_val)
        d_f = float(d_val)
        if "block_overrides" not in editor.meta: editor.meta["block_overrides"] = {}
        editor.meta["block_overrides"][key] = {"multiplier": m_f, "duration": d_f}
        editor.msg = f"Portal: x{m_f} for {d_f}s"
    except Exception:
        editor.msg = "Invalid values"

def editor_on_paint(editor, x, y):
    """
    When painting, place the char and set default override entry (optional).
    """
    # ensure there is a block_overrides dict
    if "block_overrides" not in editor.meta: editor.meta["block_overrides"] = {}
    key = f"{x},{y}"
    # only set defaults if no override exists
    if key not in editor.meta["block_overrides"]:
        editor.meta["block_overrides"][key] = {"multiplier": DEFAULT_MULTIPLIER, "duration": DEFAULT_DURATION}
    return {"char": CHAR, "color": "WHITE"}

def register():
    return {
        "char": CHAR,
        "name": "Speed Portal",
        "editor": {
            "display_char": DISPLAY_CHAR,
            "brush_name": "SPEED PORTAL",
            "on_paint": editor_on_paint,
            "on_context": editor_on_context,
            "hotkey": "s",
            "color": "WHITE"
        },
        "runtime": {
            "solid": runtime_solid,
            "deadly": False,
            "on_player_touch": on_player_touch,
            "on_reset": on_reset,
            "get_display_char": get_display_char,
            "display_char": DISPLAY_CHAR
        }
    }
