# plugins/high_jump_coin.py
"""Optimized High-Jump Coin plugin.
Stackable, respawnable, editor-configurable, and just a little bit sparkly.
"""

import time
import sys
import threading

CHAR = "o"
DEFAULT_TIME = 5.0
DEFAULT_MULT = 2.5
DEFAULT_FORCE = None
RESPAWN_DELAY = 5.0

_STATE = {}
_LOCK = threading.Lock()

_now = lambda: time.time()
_key = lambda lvl: str(lvl or "<level>")

def _gm():
    return sys.modules.get("__main__") or sys.modules.get("game")


_FRAMES = ["O", "0", "|", "0", "O"]
FRAME_RATE = 6.0


def _normalize_mult(v):
    try:
        m = float(v)
    except Exception:
        return float(DEFAULT_MULT)
    if m >= 10:
        m = m / 10.0
    if m != m:
        return float(DEFAULT_MULT)
    return max(0.1, min(50.0, m))


def _parse_mult(ov):
    if not ov:
        return float(DEFAULT_MULT)
    if "mult_input" in ov:
        return _normalize_mult(ov.get("mult_input"))
    if "mult" in ov:
        return _normalize_mult(ov.get("mult"))
    return float(DEFAULT_MULT)


def _ensure(lvl):
    k = _key(lvl)
    with _LOCK:
        if k not in _STATE:
            _STATE[k] = {"until": 0.0, "orig_jump": None, "mult": DEFAULT_MULT, "timer": None, "removed": {}}
        return _STATE[k]


def _cancel_timer(t):
    if isinstance(t, threading.Timer):
        try:
            t.cancel()
        except Exception:
            pass


def _schedule_deactivation(lvl):
    st = _STATE.get(_key(lvl))
    if not st:
        return

    remaining = st.get("until", 0.0) - _now()
    _cancel_timer(st.get("timer"))
    st["timer"] = None

    if remaining <= 0:
        _deactivate(lvl)
        return

    def on_expire():
        try:
            _deactivate(lvl)
        except Exception:
            pass

    t = threading.Timer(remaining, on_expire)
    t.daemon = True
    st["timer"] = t
    try:
        t.start()
    except Exception:
        st["timer"] = None


def _activate(lvl, extra_t, mult_norm):
    now = _now()
    st = _ensure(lvl)
    gm = _gm()

    if st["orig_jump"] is None:
        try:
            st["orig_jump"] = float(getattr(gm, "JUMP_V")) if gm and hasattr(gm, "JUMP_V") else None
        except Exception:
            st["orig_jump"] = None

    try:
        cand = float(mult_norm)
    except Exception:
        cand = float(DEFAULT_MULT)
    cand = max(0.1, min(50.0, cand))
    st["mult"] = cand

    with _LOCK:
        base = st.get("until", 0.0) if st.get("until", 0.0) > now else now
        st["until"] = float(base) + float(extra_t)

    try:
        if gm and st.get("orig_jump") is not None:
            setattr(gm, "JUMP_V", float(st["orig_jump"]) * float(st.get("mult", DEFAULT_MULT)))
    except Exception:
        pass

    _schedule_deactivation(lvl)


def _deactivate(lvl):
    k = _key(lvl)
    with _LOCK:
        st = _STATE.get(k)
        if not st:
            return
        _cancel_timer(st.get("timer"))
        st["timer"] = None
        gm = _gm()
        try:
            if gm and st.get("orig_jump") is not None:
                setattr(gm, "JUMP_V", float(st["orig_jump"]))
        except Exception:
            pass
        # Reset only the buff state; respawn bookkeeping is allowed to keep living its best life.
        st["until"] = 0.0
        st["orig_jump"] = None
        st["mult"] = DEFAULT_MULT


def _schedule_coin_respawn(lvl, tx, ty, grid_ref, delay=RESPAWN_DELAY):
    st = _ensure(lvl)
    with _LOCK:
        prev = st["removed"].get((tx, ty))
        if prev:
            _cancel_timer(prev.get("timer"))

        def do_respawn():
            try:
                with _LOCK:
                    state = _STATE.get(_key(lvl))
                    if not state:
                        return
                    entry = state["removed"].pop((tx, ty), None)
                if entry:
                    g = entry.get("grid")
                    if g is not None and 0 <= ty < len(g) and 0 <= tx < len(g[0]):
                        g[ty][tx] = CHAR
            except Exception:
                pass

        t = threading.Timer(delay, do_respawn)
        t.daemon = True
        st["removed"][(tx, ty)] = {"timer": t, "grid": grid_ref}
        try:
            t.start()
        except Exception:
            st["removed"][(tx, ty)]["timer"] = None


def _respawn_all_on_death(lvl, runtime_grid=None):
    k = _key(lvl)
    with _LOCK:
        st = _STATE.get(k)
        if not st:
            return
        items = list(st["removed"].items())
        st["removed"].clear()

    for (tx, ty), info in items:
        try:
            _cancel_timer(info.get("timer"))
        except Exception:
            pass
        grid_to_use = runtime_grid if runtime_grid is not None else info.get("grid")
        try:
            if grid_to_use is not None and 0 <= ty < len(grid_to_use) and 0 <= tx < len(grid_to_use[0]):
                grid_to_use[ty][tx] = CHAR
        except Exception:
            pass


# runtime hooks
def runtime_solid(grid, x, y):
    return False


def _read_float(val, fallback):
    try:
        return float(val)
    except Exception:
        return fallback


def on_player_touch(game_state, player_state, tx, ty, ctx):
    lvl = game_state.get("level", "<level>")
    overrides = (game_state.get("meta") or {}).get("block_overrides", {}) or {}
    ov = overrides.get(f"{tx},{ty}", {}) or {}

    extra_time = _read_float(ov.get("time", DEFAULT_TIME), DEFAULT_TIME)
    mult_norm = _parse_mult(ov)
    respawn_delay = _read_float(ov.get("respawn", RESPAWN_DELAY), RESPAWN_DELAY)

    force = None
    if "force" in ov:
        try:
            fv = ov.get("force")
            force = None if fv in (None, "") else float(fv)
        except Exception:
            force = None

    try:
        grid = game_state.get("grid")
        if grid and 0 <= ty < len(grid) and 0 <= tx < len(grid[0]):
            grid[ty][tx] = " "
            _schedule_coin_respawn(lvl, tx, ty, grid, delay=respawn_delay)
    except Exception:
        pass

    if force is not None:
        try:
            if isinstance(player_state, dict):
                player_state["vy"] = float(force)
        except Exception:
            pass

    _activate(lvl, extra_time, mult_norm)
    return ({"vy": float(force)} if force is not None else {})


def on_player_collide(game_state, player_state, tx, ty, ctx):
    return on_player_touch(game_state, player_state, tx, ty, ctx)


def on_player_death(game_state, ctx):
    lvl = game_state.get("level", "<level>")
    grid = game_state.get("grid")
    _respawn_all_on_death(lvl, runtime_grid=grid)
    _deactivate(lvl)


def get_display_char(grid, plats, x, y, level_name):
    st = _STATE.get(_key(level_name))
    if st:
        try:
            gm = _gm()
            if gm and st.get("orig_jump") is not None:
                setattr(gm, "JUMP_V", float(st["orig_jump"]) * float(st.get("mult", DEFAULT_MULT)))
        except Exception:
            pass

    if st:
        rem = max(0.0, st.get("until", 0.0) - _now())
        label = f"HJ:{rem:0.1f}s"
        try:
            gw = len(grid[0]) if grid and grid[0] else 0
        except Exception:
            gw = 0
        sx = 1 if gw >= len(label) + 2 else 0
        if y == 0 and sx <= x < sx + len(label):
            return label[x - sx]

    try:
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] == CHAR:
            idx = int(_now() * FRAME_RATE) % len(_FRAMES)
            return _FRAMES[idx]
    except Exception:
        pass

    return grid[y][x] if 0 <= y < len(grid) and 0 <= x < len(grid[0]) else " "


# editor hooks
def editor_on_paint(editor, x, y):
    return {"char": CHAR, "color": "YELLOW", "meta": None}


def editor_on_context(editor, gx, gy, get_string_input):
    try:
        key = f"{gx},{gy}"
        overrides = editor.meta.setdefault("block_overrides", {})
        cur = overrides.get(key, {}) or {}

        def_time = str(cur.get("time", DEFAULT_TIME))
        def_mult = str(cur.get("mult_input", cur.get("mult", DEFAULT_MULT)))
        def_force = "" if cur.get("force", None) is None else str(cur.get("force"))
        def_resp = str(cur.get("respawn", RESPAWN_DELAY))

        if callable(get_string_input):
            t_val = get_string_input("High-Jump Time (seconds)", def_time)
            m_val = get_string_input("Jump Multiplier (raw input, e.g. 30 -> 3.0 ; 10 -> 1.0)", def_mult)
            f_val = get_string_input("Immediate Force (vy) [leave blank for none]", def_force)
            r_val = get_string_input("Respawn Delay (seconds) [leave blank for default]", def_resp)
        else:
            t_val, m_val, f_val, r_val = def_time, def_mult, def_force, def_resp

        t_f = float(t_val)
        m_input_saved = m_val
        f_f = None if f_val is None or f_val == "" else float(f_val)
        r_f = _read_float(r_val, RESPAWN_DELAY)

        overrides[key] = {"time": t_f, "mult_input": m_input_saved, "force": f_f, "respawn": r_f}
        editor.msg = f"Coin set: {t_f}s raw_mult={m_input_saved} respawn={r_f}" + ("" if f_f is None else f", force={f_f}")
    except Exception:
        editor.msg = "Invalid values"


def register():
    return {
        "char": CHAR,
        "name": "High-Jump Coin",
        "editor": {
            "char": CHAR,
            "display_char": CHAR,
            "brush_name": "HIGH-JUMP COIN",
            "on_paint": editor_on_paint,
            "on_context": editor_on_context,
            "hotkey": "c",
            "color": "YELLOW",
        },
        "runtime": {
            "solid": False,
            "deadly": False,
            "on_player_touch": on_player_touch,
            "on_player_collide": on_player_collide,
            "on_player_death": on_player_death,
            "get_display_char": get_display_char,
            "display_char": CHAR,
        },
    }
