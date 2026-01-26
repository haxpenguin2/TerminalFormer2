import sys
import time
import math

# --- CONFIGURATION ---
CHAR = "B"            # Character used in the level text file
DEFAULT_STAND = 1.0   # Seconds before breaking
RESET_DELAY = 3.0     # FIX: Increased to 3.0s so it doesn't reset mid-jump

# VISUALS:
# Start at "▒" (Medium Shade), fade to "░" (Light Shade)
STAGES = ["▒", "░"]

# Global state
STATE = {}

def _now():
    return time.time()

def _get_entity(level, x, y):
    key = (str(level), int(x), int(y))
    if key not in STATE:
        STATE[key] = {
            "accum": 0.0,
            "stand_time": DEFAULT_STAND,
            "removed": False,
            "last_seen": 0.0
        }
    return STATE[key]

# --- RUNTIME LOGIC ---

def runtime_solid(grid, x, y):
    # If it is broken (' '), it is not solid.
    if grid[y][x] == ' ':
        return False
    return True

def on_reset(game_state):
    """
    Called when the player dies to restore blocks.
    Fixes the grid if the engine doesn't reload the level file automatically.
    """
    level = game_state.get("level", "default_level")
    grid = game_state.get("grid")

    # Iterate over all known blocks in memory
    for key, ent in STATE.items():
        lvl, x, y = key

        # Only reset blocks for the current level
        if str(lvl) == str(level):
            ent["removed"] = False
            ent["accum"] = 0.0

            # Physically put the block back in the grid if it's missing
            if grid and 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                if grid[y][x] == ' ':
                    grid[y][x] = CHAR

def on_player_supported(game_state, player_state, tx, ty, ctx):
    """
    Called every frame.
    We iterate over nearby blocks to see if we are standing on a breakable one.
    """
    level = game_state.get("level", "default_level")
    grid = game_state.get("grid")

    # Player integer coordinates
    px_int = int(tx)
    py_int = int(ty)

    # We check the block directly below the player (ty)
    block_y = int(ty)

    # Candidates: The block directly under center, and neighbors
    candidates = [px_int, px_int - 1, px_int + 1]

    current_time = _now()
    dt = 0.016
    if isinstance(ctx, dict) and "dt" in ctx:
        dt = float(ctx["dt"])

    for block_x in candidates:
        # 1. Bounds check
        if block_y < 0 or block_y >= len(grid) or block_x < 0 or block_x >= len(grid[0]):
            continue

        # 2. Is this actually a breakable block?
        if grid[block_y][block_x] != CHAR:
            continue

        # 3. COLLISION MATH
        player_width = 0.6 # slightly forgiving width
        p_left = tx - (player_width / 2)
        p_right = tx + (player_width / 2)

        b_left = float(block_x)
        b_right = float(block_x) + 1.0

        # Intersection test:
        if p_right > b_left and p_left < b_right:
            # WE ARE STANDING ON THIS BLOCK

            ent = _get_entity(level, block_x, block_y)
            if ent["removed"]: continue

            # Reset logic: Only reset if we haven't touched it in RESET_DELAY seconds
            # Since RESET_DELAY is now 3.0, short jumps won't trigger this.
            if (current_time - ent["last_seen"]) > RESET_DELAY:
                ent["accum"] = 0.0

            # Add damage
            ent["accum"] += dt
            ent["last_seen"] = current_time

            # Break logic
            limit = ent.get("stand_time", DEFAULT_STAND)
            if ent["accum"] >= limit:
                ent["removed"] = True
                grid[block_y][block_x] = ' ' # Poof

def on_player_left(game_state, player_state, tx, ty, ctx):
    """
    FIX: This function no longer resets damage.
    It is kept as a stub in case we want to add visual effects later.
    """
    pass

def get_display_char(grid, platforms, x, y, level_name):
    """Visuals"""
    ent = _get_entity(level_name, x, y)

    # --- AUTO-HEAL DESYNC ---
    # If the engine reloaded the map file (grid has 'B'), but our memory says
    # it's removed, we know the player died/reset. Sync memory to reality.
    if grid[y][x] == CHAR and ent["removed"]:
        ent["removed"] = False
        ent["accum"] = 0.0
    # ------------------------

    if grid[y][x] != CHAR: return ' '
    if ent["removed"]: return ' '

    acc = ent["accum"]
    total = ent.get("stand_time", DEFAULT_STAND)

    if total <= 0: return STAGES[0]

    percent = acc / total
    percent = max(0.0, min(1.0, percent))

    index = int(percent * len(STAGES))
    if index >= len(STAGES): index = len(STAGES) - 1

    return STAGES[index]

# --- EDITOR ---
def editor_on_context(editor, gx, gy, get_string_input):
    level = editor.meta.get('title', editor.filename)
    ent = _get_entity(level, gx, gy)
    current_val = ent.get("stand_time", DEFAULT_STAND)
    val = get_string_input(f"Break Time (s)", str(current_val))
    if val:
        try:
            ent["stand_time"] = float(val)
            editor.msg = f"Timer set to {val}s"
        except: pass

def register():
    return {
        "char": CHAR,
        "name": "Breakable Block",
        "editor": {
            "brush_name": "Breakable Block",
            "display_char": STAGES[0],
            "brush_help": "E: Set Timer",
            "on_paint": lambda e, x, y: CHAR,
            "on_context": editor_on_context
        },
        "runtime": {
            "solid": runtime_solid,
            "deadly": False,
            "on_player_supported": on_player_supported,
            "on_player_left": on_player_left,
            "on_player_death": on_reset,  # Hook for death
            "on_reset": on_reset,         # Hook for generic reset
            "get_display_char": get_display_char,
            "display_char": STAGES[0]
        }
    }
