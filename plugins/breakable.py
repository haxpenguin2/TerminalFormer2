# plugins/breakable.py
import time, os, traceback

CHAR = "B"
DEFAULT_STAND = 1.0

# --- Textures ---
TEX_SOLID = "▓"
TEX_MID   = "▒"
TEX_BROKEN = "░"

# Runtime transient state:
# keyed by (normalized_level, x, y) -> {"accum":..., "removed":..., "last_touch":..., "last_frame":...}
_STATE = {}

def _now(): return time.time()

def _normalize_level(level):
    if level is None:
        return "<unknown>"
    s = str(level)
    if s.startswith("<") and s.endswith(">"):
        return s
    try:
        base = os.path.splitext(os.path.basename(s))[0]
        return base if base != "" else s
    except:
        return s

def _key(level, x, y):
    return (_normalize_level(level), int(x), int(y))

def _get_state(level, x, y):
    k = _key(level, x, y)
    if k not in _STATE:
        _STATE[k] = {
            "accum": 0.0,
            "removed": False,
            "last_touch": 0.0,
            "last_frame": _now()
        }
    return _STATE[k]

def _clear_level_state(level):
    nl = _normalize_level(level)
    for k in list(_STATE.keys()):
        if k[0] == nl:
            del _STATE[k]

def _read_override_from_meta(game_state, x, y):
    """
    Returns stand_time override (float) if present in game_state.meta["block_overrides"] else None.
    Editor and level saving use meta["block_overrides"] with keys "x,y" -> {"stand_time":N}
    """
    try:
        if not game_state: return None
        meta = game_state.get("meta", {}) if isinstance(game_state, dict) else {}
        overrides = meta.get("block_overrides", {}) if isinstance(meta, dict) else {}
        key = f"{int(x)},{int(y)}"
        entry = overrides.get(key)
        if isinstance(entry, dict):
            val = entry.get("stand_time")
            if val is None:
                # backward-compatible: maybe editor used "hp" or "time"
                for alt in ("hp", "time", "dur", "break_time"):
                    if alt in entry:
                        try: return float(entry[alt])
                        except: pass
            else:
                try: return float(val)
                except: pass
    except Exception:
        # be silent, but safe
        try:
            open(os.path.expanduser("~/.tf2_debug.log"), "a").write(time.strftime("%Y-%m-%d %H:%M:%S ") + "meta read error\n" + traceback.format_exc() + "\n")
        except: pass
    return None

# --- runtime API (be flexible about signatures) ---

def runtime_solid(*args, **kwargs):
    """
    Compatible with multiple call signatures:
      runtime_solid(grid, x, y, level_name=None)
    or
      runtime_solid(game_state_dict, x, y)
    Returns True if tile acts solid (not removed), False if it's gone.
    """
    # detect whether first arg is a game_state (dict with 'grid') or raw grid
    try:
        if isinstance(args[0], dict) and 'grid' in args[0]:
            game_state = args[0]; x = args[1]; y = args[2]
            level = game_state.get("level")
            grid = game_state.get("grid", [])
        else:
            grid = args[0]; x = args[1]; y = args[2]
            level = args[3] if len(args) > 3 else kwargs.get("level_name")
    except Exception:
        return False

    ix, iy = int(x), int(y)
    if not (0 <= iy < len(grid) and 0 <= ix < len(grid[0])):
        return False
    if grid[iy][ix] != CHAR:
        return False

    ent = _get_state(level, ix, iy)
    return not bool(ent.get("removed", False))

def on_reset(game_state):
    """
    Called when level resets/starts. Clear runtime state for this level
    and pre-seed stand_time from metadata if present (for nicer visuals).
    """
    level = game_state.get("level", "<level>") if isinstance(game_state, dict) else "<level>"
    # clear existing runtime entries for this level
    _clear_level_state(level)

    # If metadata provides overrides, create state entries with no accum and default removed=False.
    try:
        meta = game_state.get("meta", {}) if isinstance(game_state, dict) else {}
        overrides = meta.get("block_overrides", {}) if isinstance(meta, dict) else {}
        for k, v in overrides.items():
            try:
                sx, sy = map(int, k.split(","))
                # create a state entry so get_display_char can immediately show configured visuals
                entry = _get_state(level, sx, sy)
                # store the configured stand_time on the runtime entry for convenience (not authoritative)
                if isinstance(v, dict) and "stand_time" in v:
                    try: entry["stand_time"] = float(v["stand_time"])
                    except: entry["stand_time"] = DEFAULT_STAND
            except Exception:
                continue
    except Exception:
        pass

def on_player_supported(game_state, player_state, tx, ty, ctx):
    """
    game_state is a dict with keys: grid, platforms, level, meta
    ctx is expected to include "dt" (float) but we accept missing.
    Accumulate dt into per-tile 'accum' and check stand_time from metadata.
    """
    try:
        grid = game_state.get("grid")
        level = game_state.get("level")
    except Exception:
        return

    bx, by = int(tx), int(ty)
    if not (0 <= by < len(grid) and 0 <= bx < len(grid[0])): return
    if grid[by][bx] != CHAR: return

    ent = _get_state(level, bx, by)
    if ent.get("removed", False): return

    dt = 0.016
    if isinstance(ctx, dict) and "dt" in ctx:
        try: dt = float(ctx["dt"])
        except: dt = 0.016

    # read stand_time from metadata (authoritative configuration)
    override_val = _read_override_from_meta(game_state, bx, by)
    if override_val is None:
        # fallback: maybe runtime stored a pre-seeded value (from on_reset)
        limit = float(ent.get("stand_time", DEFAULT_STAND))
    else:
        limit = float(override_val)
        # save it to runtime entry for faster subsequent reads/visuals
        ent["stand_time"] = limit

    ent["accum"] = ent.get("accum", 0.0) + dt
    ent["last_touch"] = _now()

    if ent["accum"] >= (limit if limit > 0 else DEFAULT_STAND):
        ent["removed"] = True
        # do NOT mutate grid here; engine expects removed -> runtime solidity false

def get_display_char(grid, plats, x, y, level_name):
    """
    Called by renderer. Signature: (grid, plats, x, y, level_name)
    We use the runtime state for visuals. If metadata provided stand_time and we have no runtime
    entry yet, visuals will fallback to defaults until on_player_supported/on_reset seeds state.
    """
    ix, iy = int(x), int(y)
    if not (0 <= iy < len(grid) and 0 <= ix < len(grid[0])): return ' '
    if grid[iy][ix] != CHAR: return grid[iy][ix]

    ent = _get_state(level_name, ix, iy)
    limit = float(ent.get("stand_time", DEFAULT_STAND))
    now = _now()
    delta = now - ent.get("last_frame", now)
    ent["last_frame"] = now
    if delta > 0.1: delta = 0.1

    # try to reduce accum slowly if not recently touched (visual regen)
    if now - ent.get("last_touch", 0) > 2.0 and ent.get("accum", 0.0) > 0.0:
        ent["accum"] = max(0.0, ent["accum"] - (delta * 0.5))
        if ent.get("removed", False) and ent["accum"] <= 0.0:
            ent["removed"] = False
            ent["accum"] = 0.0

    pct = max(0.0, min(1.0, (ent.get("accum", 0.0) / (limit if limit > 0 else DEFAULT_STAND))))

    if ent.get("removed", False):
        return TEX_BROKEN if pct > 0.5 else TEX_MID
    else:
        return TEX_SOLID if pct < 0.3 else TEX_MID

# --- editor hooks ---

def editor_on_context(editor, gx, gy, get_string_input):
    """
    Write configuration to editor.meta['block_overrides'] as:
      "x,y" : { "stand_time": <float> }
    This persists into the level __METADATA__ when editor.save_level() is called.
    """
    try:
        # ensure meta dict exists
        if "block_overrides" not in editor.meta or not isinstance(editor.meta["block_overrides"], dict):
            editor.meta["block_overrides"] = {}

        key = f"{int(gx)},{int(gy)}"
        curr = editor.meta["block_overrides"].get(key, {}).get("stand_time", DEFAULT_STAND)
        val = get_string_input("Break Time (s)", str(curr))
        # accept blank or cancel -> no change
        if val is None or val == "":
            editor.msg = "Canceled"
            return

        newt = float(val)
        editor.meta["block_overrides"][key] = {"stand_time": newt}
        editor.msg = f"Break time set to {newt:.2f}s"

        # If runtime state exists in-memory (editor may be running in same process), update it for immediate visual feedback
        try:
            lvl = editor.meta.get("title", editor.filename)
            nk = _key(lvl, gx, gy)
            if nk in _STATE:
                _STATE[nk]["stand_time"] = float(newt)
        except Exception:
            pass

    except Exception:
        editor.msg = "Invalid value"

def editor_on_paint(editor, x, y):
    """
    Return dict to allow editor to set metadata at paint time if desired.
    Here we just return the char and color; the context menu is used for setting time.
    """
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
