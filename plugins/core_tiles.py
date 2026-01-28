# plugins/core_tiles.py
# Core tiles + engine constants plugin

# ============================================================
# Engine / Editor exports
# ============================================================

EXPORTS = {
    "DIRS": {
        "LEVELS": "levels",
        "CAMP": "campaignlevels",
        "SCORES": "scores.json",
        "PLUGINS": "plugins"
    },
    "TILES": {
        "SOLID": '█',
        "SPIKE": '▲',
        "SPIKE_DN": '▼',
        "CP": 'C',
        "SPAWN": 'S',
        "GOAL": 'G',
        "PLAYER": '#'
    },
    "PHYS": {
        "HW": 0.4,
        "HH": 0.5,
        "TOL": 0.001
    },
    "GRAVITY": 90.0,
    "JUMP_V": -28.0,
    "MOVE_SPEED": 24.0,
    "FPS": 60.0,
    "MAX_SUBSTEP": 0.02
}

# ============================================================
# Helpers
# ============================================================

def make_tile(char, name, *, runtime=None, editor=None, role=None):
    meta = {"char": char, "name": name}
    if runtime: meta["runtime"] = runtime
    if editor: meta["editor"] = editor
    if role: meta["role"] = role
    return meta

def solid_true(grid, x, y): return True
def solid_false(grid, x, y): return False
def deadly_true(grid, x, y): return True

# ============================================================
# Plugin entry
# ============================================================

def register():
    tiles = []

    # Core exports
    tiles.append({"provides": "core", "exports": EXPORTS})

    # --------------------------------------------------------
    # Solid block (Safe)
    # --------------------------------------------------------
    tiles.append(make_tile(
        EXPORTS["TILES"]["SOLID"],
        "Solid Block",
        runtime={
            "solid": solid_true,
            "deadly": False,  # CHANGED: Was solid_false
            "get_display_char": lambda grid, plats, x, y, lvl: EXPORTS["TILES"]["SOLID"]
        },
        editor={
            "display_char": EXPORTS["TILES"]["SOLID"],
            "brush_name": "SOLID"
        }
    ))

    # --------------------------------------------------------
    # Spike up (Deadly)
    # --------------------------------------------------------
    tiles.append(make_tile(
        EXPORTS["TILES"]["SPIKE"],
        "Spike Up",
        runtime={
            "solid": solid_false,
            "deadly": True, # Explicitly True
            "get_display_char": lambda grid, plats, x, y, lvl: EXPORTS["TILES"]["SPIKE"]
        },
        editor={
            "display_char": EXPORTS["TILES"]["SPIKE"],
            "brush_name": "SPIKE UP"
        }
    ))

    # --------------------------------------------------------
    # Spike down (Deadly)
    # --------------------------------------------------------
    tiles.append(make_tile(
        EXPORTS["TILES"]["SPIKE_DN"],
        "Spike Down",
        runtime={
            "solid": solid_false,
            "deadly": True, # Explicitly True
            "get_display_char": lambda grid, plats, x, y, lvl: EXPORTS["TILES"]["SPIKE_DN"]
        },
        editor={
            "display_char": EXPORTS["TILES"]["SPIKE_DN"],
            "brush_name": "SPIKE DOWN"
        }
    ))

    # --------------------------------------------------------
    # Checkpoint (Safe)
    # --------------------------------------------------------
    tiles.append(make_tile(
        EXPORTS["TILES"]["CP"],
        "Checkpoint",
        runtime={
            "solid": solid_false,
            "deadly": False, # CHANGED: Was solid_false
            "checkpoint": True,
            "get_display_char": lambda grid, plats, x, y, lvl: EXPORTS["TILES"]["CP"]
        },
        editor={
            "display_char": EXPORTS["TILES"]["CP"],
            "brush_name": "CHECKPOINT"
        },
        role="checkpoint"
    ))

    # --------------------------------------------------------
    # Spawn (Safe)
    # --------------------------------------------------------
    tiles.append(make_tile(
        EXPORTS["TILES"]["SPAWN"],
        "Spawn",
        runtime={
            "solid": solid_false,
            "deadly": False, # CHANGED: Was solid_false
            "spawn": True,
            "get_display_char": lambda grid, plats, x, y, lvl: EXPORTS["TILES"]["SPAWN"]
        },
        editor={
            "display_char": EXPORTS["TILES"]["SPAWN"],
            "brush_name": "SPAWN"
        },
        role="spawn"
    ))

    # --------------------------------------------------------
    # Goal (Safe)
    # --------------------------------------------------------
    tiles.append(make_tile(
        EXPORTS["TILES"]["GOAL"],
        "Goal",
        runtime={
            "solid": solid_false,
            "deadly": False, # CHANGED: Was solid_false
            "goal": True,
            "get_display_char": lambda grid, plats, x, y, lvl: EXPORTS["TILES"]["GOAL"]
        },
        editor={
            "display_char": EXPORTS["TILES"]["GOAL"],
            "brush_name": "GOAL"
        },
        role="goal"
    ))

    # --------------------------------------------------------
    # Player display
    # --------------------------------------------------------
    tiles.append({
        "id": "player_char",
        "name": "Player",
        "exports": {"PLAYER_CHAR": EXPORTS["TILES"]["PLAYER"]},
        "editor": {"display_char": EXPORTS["TILES"]["PLAYER"]}
    })

    return tiles
