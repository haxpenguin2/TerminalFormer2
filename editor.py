#!/usr/bin/env python3
import curses, sys, os, json, time, math, glob, importlib.util
from datetime import datetime

# --- CONFIGURATION & CONSTANTS ---
LEVELS_DIR = "levels"
PLUGINS_DIR = "plugins"
DEFAULT_FILE = "level1.txt"

# Tile Constants
TILE_EMPTY = ' '
TILE_SOLID = '█'
TILE_SPIKE = '▲'
TILE_SPIKE_DOWN = '▼'
TILE_CHECKPOINT = 'C'
TILE_SPAWN = 'S'
TILE_GOAL = 'G'
TILE_PLATFORM = '='
TILE_BREAKABLE = 'B' # Added Breakable Block

# Color IDs
class Colors:
    DEFAULT = 1
    SOLID = 2
    DANGER = 3
    SPECIAL = 4
    UI = 5
    SELECT = 6
    CURSOR = 7
    PLATFORM_EDIT = 8
    PLATFORM_GAME = 9
    HELP_TEXT = 10
    DIM = 11
    BREAKABLE = 12

# Global State for Plugins
BLOCK_REGISTRY = {}
PLUGIN_LIST = []
BRUSHES = [
    (TILE_SOLID, "SOLID"),
    (TILE_BREAKABLE, "BREAKABLE"),
    (TILE_SPIKE, "SPIKE UP"),
    (TILE_SPIKE_DOWN, "SPIKE DOWN"),
    (TILE_CHECKPOINT, "CHECKPOINT"),
    (TILE_SPAWN, "SPAWN"),
    (TILE_GOAL, "GOAL"),
    (TILE_PLATFORM, "PLATFORM (Select -> P)"),
    (TILE_EMPTY, "ERASER (Brush #9)")
]

# --- UTILS: FILE IO & PLUGINS ---
def ensure_dirs():
    for d in [LEVELS_DIR, PLUGINS_DIR]:
        os.makedirs(d, exist_ok=True)

def load_plugins():
    """Dynamic plugin loader."""
    global BLOCK_REGISTRY, PLUGIN_LIST, BRUSHES
    ensure_dirs()
    BLOCK_REGISTRY.clear()
    PLUGIN_LIST.clear()
    # Reset brushes to core + eraser
    core_brushes = BRUSHES[:8] # Keep first 8

    for path in glob.glob(os.path.join(PLUGINS_DIR, "*.py")):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{name}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "register") and callable(module.register):
                meta = module.register()
                if not isinstance(meta, dict): continue
                ch = meta.get("char") or meta.get("editor", {}).get("char") or meta.get("id")
                if isinstance(ch, str) and len(ch) == 1:
                    BLOCK_REGISTRY[ch] = meta
                    if "editor" in meta: meta["editor"].setdefault("display_char", ch)
                    brush_name = meta.get("editor", {}).get("brush_name")
                    if brush_name: core_brushes.append((ch, brush_name))
                PLUGIN_LIST.append(meta)
        except Exception as e:
            print(f"Plugin Error [{name}]: {e}", file=sys.stderr)

    # Add Eraser last
    core_brushes.append((TILE_EMPTY, "ERASER"))
    BRUSHES = core_brushes

# --- UTILS: RENDERING HELPERS ---
def safe_addch(stdscr, y, x, ch, attr=0):
    h, w = stdscr.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        try: stdscr.addch(y, x, ch, attr)
        except curses.error: pass

def safe_addstr(stdscr, y, x, s, attr=0):
    h, w = stdscr.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        if x + len(s) >= w: s = s[:w - x - 1]
        try: stdscr.addstr(y, x, s, attr)
        except curses.error: pass

def draw_box(stdscr, title, lines):
    h, w = stdscr.getmaxyx()
    box_w = 50
    box_h = len(lines) + 4
    bx, by = (w - box_w) // 2, (h - box_h) // 2
    style_border = curses.color_pair(Colors.UI) | curses.A_BOLD
    style_bg = curses.color_pair(Colors.UI)

    for y in range(by, by+box_h):
        safe_addstr(stdscr, y, bx, " " * box_w, style_bg)
    border_top = "+" + "-"*(box_w-2) + "+"
    safe_addstr(stdscr, by, bx, border_top, style_border)
    safe_addstr(stdscr, by+box_h-1, bx, border_top, style_border)
    safe_addstr(stdscr, by + 1, bx + 2, title.center(box_w - 4), style_border)
    for i, line in enumerate(lines):
        safe_addstr(stdscr, by + 3 + i, bx + 2, line, style_bg)
    return bx, by, box_w, box_h

def get_string_input(stdscr, prompt, default=""):
    stdscr.nodelay(False); curses.echo(); curses.curs_set(1)
    bx, by, _, _ = draw_box(stdscr, prompt, [f"Current: {default}", "New Value: "])
    val = default
    try:
        safe_addstr(stdscr, by + 4, bx + 13, " " * 30, curses.color_pair(Colors.UI))
        inp = stdscr.getstr(by + 4, bx + 13, 20).decode('utf-8')
        if inp.strip(): val = inp.strip()
    except: pass
    curses.noecho(); curses.curs_set(0); stdscr.nodelay(True)
    return val

# --- CORE EDITOR CLASS ---
class Editor:
    def __init__(self, filename):
        self.filename = filename
        self.grid = []
        self.platforms = []
        self.meta = {"title": "Untitled", "block_overrides": {}}
        self.load_level()

        # Viewport
        self.cam_x, self.cam_y = 0, 0
        self.cx, self.cy = 1, 1

        # State
        self.mode = 'PAINT'
        self.brush_idx = 0
        self.sel_anchor = None
        self.clipboard = None # Now holds complex dict

        # System
        self.msg = f"Loaded {filename}"
        self.msg_timer = 50
        self.start_time = time.time()

    # --- DATA MANAGEMENT ---
    def load_level(self):
        ensure_dirs()
        path = os.path.join(LEVELS_DIR, self.filename)
        w, h = 40, 20
        self.grid = [[TILE_EMPTY for _ in range(w)] for _ in range(h)]
        self._apply_borders()

        if os.path.exists(path):
            try:
                with open(path, 'r') as f: content = f.read()
                parts = content.split('__METADATA__')
                lines = [l.rstrip('\n') for l in parts[0].strip().split('\n')]
                if lines:
                    fw = max(len(l) for l in lines)
                    self.grid = [list(l.ljust(fw, ' ')) for l in lines]
                if len(parts) > 1:
                    data = json.loads(parts[1])
                    if isinstance(data, dict):
                        self.meta = data
                        self.platforms = data.get('platforms', [])
                        # Ensure overrides exist
                        if "block_overrides" not in self.meta:
                            self.meta["block_overrides"] = {}
            except Exception as e:
                self.msg = f"Load Error: {e}"

        # Clean up visual representation of platforms
        for p in self.platforms:
            px, py, pw = int(p['x']), int(p['y']), int(p['w'])
            if 0 <= py < len(self.grid):
                for i in range(pw):
                    if 0 <= px+i < len(self.grid[0]):
                        self.grid[py][px+i] = TILE_PLATFORM

    def save_level(self):
        path = os.path.join(LEVELS_DIR, self.filename)
        valid_platforms = []
        for p in self.platforms:
            try:
                # Only save platforms that still exist visually on grid
                if self.grid[int(p['y'])][int(p['x'])] == TILE_PLATFORM:
                    valid_platforms.append(p)
            except IndexError: pass

        export_lines = []
        for row in self.grid:
            # Convert visual platform tiles to solid for generic viewers
            line = "".join([TILE_SOLID if c == TILE_PLATFORM else c for c in row])
            export_lines.append(line.rstrip())

        json_data = {
            "title": self.meta.get('title', 'Untitled'),
            "platforms": valid_platforms,
            "block_overrides": self.meta.get("block_overrides", {})
        }

        with open(path, 'w') as f:
            f.write("\n".join(export_lines))
            f.write("\n__METADATA__\n")
            json.dump(json_data, f, indent=2)

    def _apply_borders(self):
        if not self.grid: return
        h, w = len(self.grid), len(self.grid[0])
        for y in range(h): self.grid[y][0] = self.grid[y][w-1] = TILE_SOLID
        for x in range(w): self.grid[0][x] = self.grid[h-1][x] = TILE_SOLID

    # --- LOGIC & TOOLS ---
    def get_dims(self):
        return (len(self.grid[0]) if self.grid else 0), len(self.grid)

    def get_cell(self, x, y):
        w, h = self.get_dims()
        if 0 <= y < h and 0 <= x < w: return self.grid[y][x]
        return TILE_EMPTY

    def paint(self, x, y, brush=None):
        if brush is None: brush = BRUSHES[self.brush_idx][0]
        w, h = self.get_dims()
        if not (0 <= y < h and 0 <= x < w): return

        prev = self.grid[y][x]

        # If erasing a platform, remove the logic object
        if brush == TILE_EMPTY and prev == TILE_PLATFORM:
            self.platforms = [p for p in self.platforms if not (p['y'] == y and p['x'] <= x < p['x'] + p['w'])]

        # Plugin Paint Hook
        plugin = BLOCK_REGISTRY.get(brush)
        if plugin and 'editor' in plugin and callable(plugin['editor'].get('on_paint')):
            try:
                val = plugin['editor']['on_paint'](self, x, y)
                if val and isinstance(val, str):
                    self.grid[y][x] = val[0]; return
            except: pass

        self.grid[y][x] = brush

        # Clean up metadata if overwriting
        key = f"{x},{y}"
        if key in self.meta["block_overrides"]:
            del self.meta["block_overrides"][key]

    def get_selection_bounds(self):
        if not self.sel_anchor: return None
        x1, y1 = self.sel_anchor
        return (min(x1, self.cx), min(y1, self.cy), max(x1, self.cx), max(y1, self.cy))

    def get_platform_at(self, x, y):
        for p in self.platforms:
            if p['y'] == y and p['x'] <= x < p['x'] + p['w']: return p
        return None

    # --- ADVANCED SELECTION LOGIC ---
    def copy_selection(self):
        b = self.get_selection_bounds()
        if not b: return
        x1, y1, x2, y2 = b

        # 1. Copy Visual Grid
        grid_data = [[self.get_cell(x, y) for x in range(x1, x2+1)] for y in range(y1, y2+1)]

        # 2. Copy Platforms (Deep Copy & Relativize Coordinates)
        platform_data = []
        for p in self.platforms:
            # Check if platform origin is inside selection
            if x1 <= p['x'] <= x2 and y1 <= p['y'] <= y2:
                p_copy = p.copy()
                p_copy['x'] -= x1 # Make relative to selection top-left
                p_copy['y'] -= y1
                platform_data.append(p_copy)

        # 3. Copy Block Overrides (Deep Copy & Relativize)
        override_data = {}
        overrides = self.meta.get("block_overrides", {})
        for k, v in overrides.items():
            cx, cy = map(int, k.split(','))
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                rel_k = f"{cx-x1},{cy-y1}"
                override_data[rel_k] = v

        self.clipboard = {
            "grid": grid_data,
            "platforms": platform_data,
            "overrides": override_data
        }
        self.msg = f"Copied {len(grid_data)}x{len(grid_data[0])}"
        self.sel_anchor = None # Clear selection after copy

    def paste_selection(self):
        if not self.clipboard: self.msg = "Empty Clipboard"; return

        grid_data = self.clipboard["grid"]
        plat_data = self.clipboard.get("platforms", [])
        over_data = self.clipboard.get("overrides", {})

        # 1. Paste Grid
        for r, row in enumerate(grid_data):
            for c, val in enumerate(row):
                self.paint(self.cx + c, self.cy + r, val)

        # 2. Paste Platforms (Restore absolute coords)
        for p in plat_data:
            new_p = p.copy()
            new_p['x'] += self.cx
            new_p['y'] += self.cy

            # Remove any existing platforms at this new location to prevent stacking
            self.platforms = [ex for ex in self.platforms if not (ex['y'] == new_p['y'] and ex['x'] == new_p['x'])]
            self.platforms.append(new_p)

        # 3. Paste Overrides
        if "block_overrides" not in self.meta: self.meta["block_overrides"] = {}
        for rel_k, v in over_data.items():
            rx, ry = map(int, rel_k.split(','))
            abs_k = f"{self.cx + rx},{self.cy + ry}"
            self.meta["block_overrides"][abs_k] = v

        self.msg = "Pasted"

    def manipulate_selection(self, action):
        b = self.get_selection_bounds()
        if not b and action != 'paste': return
        if action == 'paste':
            self.paste_selection(); return

        x1, y1, x2, y2 = b

        if action == 'fill':
            for y in range(y1, y2+1):
                for x in range(x1, x2+1): self.paint(x, y)
        elif action == 'delete':
            for y in range(y1, y2+1):
                for x in range(x1, x2+1): self.paint(x, y, TILE_EMPTY)
        elif action == 'copy':
            self.copy_selection()
        elif action == 'flip_h':
            self._flip_area(x1, y1, x2, y2, 'H')
        elif action == 'flip_v':
            self._flip_area(x1, y1, x2, y2, 'V')

        if action != 'copy': self.sel_anchor = None

    def move_selection(self, dx, dy):
        """Advanced move: Uses copy/delete/paste to preserve metadata."""
        b = self.get_selection_bounds()
        if not b: return
        x1, y1, x2, y2 = b

        # 1. Copy data internally
        self.copy_selection() # This sets self.clipboard
        temp_clip = self.clipboard

        # 2. Erase old area
        for y in range(y1, y2+1):
            for x in range(x1, x2+1):
                self.paint(x, y, TILE_EMPTY)

        # 3. Update Anchor & Cursor
        self.sel_anchor = (x1 + dx, y1 + dy)
        self.cx += dx
        self.cy += dy

        # 4. Paste at new location (Top Left of selection)
        # We need to temporarily move cursor to top-left of new selection to paste correctly
        orig_cx, orig_cy = self.cx, self.cy
        self.cx = self.sel_anchor[0]
        self.cy = self.sel_anchor[1]

        self.paste_selection()

        # Restore cursor
        self.cx, self.cy = orig_cx, orig_cy

    def _flip_area(self, x1, y1, x2, y2, axis):
        # NOTE: Flipping complex objects is hard, this only flips visuals for now
        data = [[self.get_cell(x, y) for x in range(x1, x2+1)] for y in range(y1, y2+1)]
        if axis == 'V': data.reverse()
        else: [r.reverse() for r in data]
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.paint(x1+c, y1+r, val)

    def resize_map(self, stdscr):
        cw, ch = self.get_dims()
        try:
            nw = int(get_string_input(stdscr, "Resize Width", str(cw)))
            nh = int(get_string_input(stdscr, "Resize Height", str(ch)))
        except ValueError: self.msg = "Invalid Size"; return
        if nw < 5 or nh < 5: self.msg = "Too Small"; return

        new_grid = [[TILE_EMPTY for _ in range(nw)] for _ in range(nh)]
        for y in range(min(ch, nh)):
            for x in range(min(cw, nw)):
                new_grid[y][x] = self.grid[y][x]

        self.grid = new_grid
        self._apply_borders()
        self.msg = f"Resized to {nw}x{nh}"

    def open_platform_wizard(self, stdscr):
        p = self.get_platform_at(self.cx, self.cy)
        if not self.sel_anchor and p:
            is_h = p.get('lx',0) != 0
            d_s = get_string_input(stdscr, "Direction (H/V)", "H" if is_h else "V").upper()
            rng = float(get_string_input(stdscr, "Range", str(p.get('lx',0) if is_h else p.get('ly',0))))
            spd = float(get_string_input(stdscr, "Speed", str(p.get('spd', 1.0))))
            p['lx'] = rng if d_s == 'H' else 0
            p['ly'] = rng if d_s != 'H' else 0
            p['spd'] = spd
            self.msg = "Platform Updated"
            return

        b = self.get_selection_bounds()
        if not b: self.msg = "Select Area First"; return
        if b[1] != b[3]: self.msg = "Height must be 1"; return

        d_s = get_string_input(stdscr, "Direction (H/V)", "H").upper()
        rng = float(get_string_input(stdscr, "Range", "6"))
        spd = float(get_string_input(stdscr, "Speed", "2.0"))

        for x in range(b[0], b[2]+1): self.paint(x, b[1], TILE_PLATFORM)
        self.platforms = [p for p in self.platforms if not (p['y']==b[1] and b[0]<=p['x']<=b[2])]
        self.platforms.append({
            "x": b[0], "y": b[1], "w": b[2]-b[0]+1,
            "lx": rng if d_s == 'H' else 0,
            "ly": rng if d_s != 'H' else 0,
            "spd": spd
        })
        self.msg = "Platform Created"; self.sel_anchor = None

    def trigger_plugin_context(self, stdscr):
        ch = self.get_cell(self.cx, self.cy)
        plugin = BLOCK_REGISTRY.get(ch)

        # If it's a generic block, we might want to edit manual overrides
        if ch == TILE_BREAKABLE or (plugin and 'editor' in plugin):
            key = f"{self.cx},{self.cy}"
            curr_hp = self.meta["block_overrides"].get(key, {}).get("hp", 1)

            try:
                # If plugin has specific context, use it
                if plugin and callable(plugin['editor'].get('on_context')):
                    plugin['editor']['on_context'](self, self.cx, self.cy, lambda p, d: get_string_input(stdscr, p, d))
                else:
                    # Default Breakable Logic
                    new_hp = get_string_input(stdscr, "Block HP", str(curr_hp))
                    if "block_overrides" not in self.meta: self.meta["block_overrides"] = {}
                    self.meta["block_overrides"][key] = {"hp": int(new_hp)}
                self.msg = "Updated Block Data"
            except Exception as e: self.msg = f"Error: {e}"
        else: self.msg = "No Settings"

# --- MAIN RENDER & LOOP ---
def main(stdscr):
    curses.start_color(); curses.use_default_colors()
    curses.init_pair(Colors.SOLID, curses.COLOR_WHITE, -1)
    curses.init_pair(Colors.DANGER, curses.COLOR_RED, -1)
    curses.init_pair(Colors.SPECIAL, curses.COLOR_GREEN, -1)
    curses.init_pair(Colors.UI, curses.COLOR_CYAN, -1)
    curses.init_pair(Colors.SELECT, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(Colors.CURSOR, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(Colors.PLATFORM_EDIT, curses.COLOR_YELLOW, -1)
    curses.init_pair(Colors.PLATFORM_GAME, curses.COLOR_WHITE, -1)
    curses.init_pair(Colors.HELP_TEXT, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(Colors.DIM, curses.COLOR_BLUE, -1)
    curses.init_pair(Colors.BREAKABLE, curses.COLOR_MAGENTA, -1)

    curses.curs_set(0); stdscr.nodelay(True)
    filename = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    editor = Editor(filename)
    load_plugins()
    show_help = False

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        gw, gh = editor.get_dims()

        if show_help:
            draw_help_menu(stdscr)
            k = stdscr.getch()
            if k in (ord('h'), ord('?'), 27): show_help = False
            continue

        if editor.cx < editor.cam_x + 2: editor.cam_x = max(0, editor.cx - 2)
        if editor.cx >= editor.cam_x + w - 2: editor.cam_x = editor.cx - (w - 3)
        if editor.cy < editor.cam_y + 2: editor.cam_y = max(0, editor.cy - 2)
        if editor.cy >= editor.cam_y + h - 6: editor.cam_y = editor.cy - (h - 7)
        off_x = (w - gw) // 2 if gw < w else -editor.cam_x
        off_y = (h - gh) // 2 if gh < h - 4 else -editor.cam_y

        # Render Grid
        bounds = editor.get_selection_bounds()
        start_y, end_y = max(0, -off_y), min(gh, h - off_y - 4)
        start_x, end_x = max(0, -off_x), min(gw, w - off_x)

        for r in range(start_y, end_y):
            scr_y = off_y + r
            row = editor.grid[r]
            for c in range(start_x, end_x):
                char = row[c]
                disp_char = char
                col_id = Colors.DEFAULT

                # Plugin Display
                if char in BLOCK_REGISTRY:
                    ed_cfg = BLOCK_REGISTRY[char].get('editor', {})
                    disp_char = ed_cfg.get('display_char', char)

                if disp_char == TILE_SOLID: col_id = Colors.SOLID
                elif disp_char in (TILE_SPIKE, TILE_SPIKE_DOWN): col_id = Colors.DANGER
                elif disp_char == TILE_BREAKABLE: col_id = Colors.BREAKABLE
                elif disp_char in (TILE_SPAWN, TILE_GOAL, TILE_CHECKPOINT): col_id = Colors.SPECIAL
                elif char == TILE_PLATFORM: col_id = Colors.PLATFORM_EDIT; disp_char = TILE_SOLID

                attr = curses.color_pair(col_id)
                if bounds and (bounds[0] <= c <= bounds[2] and bounds[1] <= r <= bounds[3]):
                    attr = curses.color_pair(Colors.SELECT)
                if c == editor.cx and r == editor.cy and editor.mode != 'PREVIEW':
                    attr = curses.color_pair(Colors.CURSOR) | curses.A_BOLD
                safe_addch(stdscr, scr_y, off_x + c, disp_char, attr)

        # Physics Preview
        if editor.mode == 'PREVIEW':
            dt = time.time() - editor.start_time
            for p in editor.platforms:
                swing = math.sin(dt * p.get('spd', 1.0))
                dx = int(swing * (p.get('lx', 0)/2))
                dy = int(swing * (p.get('ly', 0)/2))
                py, px = int(p['y']) + dy, int(p['x']) + dx
                if 0 <= off_y + py < h-4:
                    for i in range(int(p['w'])):
                        safe_addch(stdscr, off_y + py, off_x + px + i, TILE_SOLID, curses.color_pair(Colors.PLATFORM_GAME))

        # UI Overlay
        mode_cols = {'PAINT': Colors.UI, 'SELECT': Colors.SELECT, 'MOVE': Colors.DANGER, 'PREVIEW': Colors.SPECIAL}
        mode_col = curses.color_pair(mode_cols.get(editor.mode, Colors.DEFAULT)) | curses.A_BOLD | curses.A_REVERSE
        safe_addstr(stdscr, 0, 0, f" {editor.mode} ", mode_col)
        safe_addstr(stdscr, 0, 10, f"Pos: {editor.cx},{editor.cy}  Size: {gw}x{gh}", curses.color_pair(Colors.UI))
        safe_addstr(stdscr, 0, 40, "Press '?' for HELP", curses.color_pair(Colors.UI) | curses.A_BOLD)
        t_str = f"'{editor.meta.get('title','?')}'"
        safe_addstr(stdscr, 0, w - len(t_str) - 2, t_str, curses.color_pair(Colors.SPECIAL))

        if editor.msg:
            safe_addstr(stdscr, 1, w - len(editor.msg) - 2, editor.msg, curses.color_pair(Colors.UI) | curses.A_REVERSE)
            editor.msg_timer -= 1
            if editor.msg_timer <= 0: editor.msg = None

        if editor.mode != 'PREVIEW':
            bc, bn = BRUSHES[editor.brush_idx]
            d = TILE_SOLID if bc == TILE_PLATFORM else bc
            safe_addstr(stdscr, h-4, 1, f"BRUSH: [{d}] {bn}", curses.color_pair(Colors.SOLID) | curses.A_BOLD)

            # Show Block Metadata under cursor
            meta_key = f"{editor.cx},{editor.cy}"
            if meta_key in editor.meta["block_overrides"]:
                info = str(editor.meta["block_overrides"][meta_key])
                safe_addstr(stdscr, h-4, 30, f"DATA: {info}", curses.color_pair(Colors.SPECIAL))

            instr = ""
            if editor.mode == 'PAINT': instr = "TAB: Select | 0: Preview | SPACE: Paint | R: Resize | S: Save"
            elif editor.mode == 'SELECT': instr = "SPACE: Anchor | C/V: Copy/Paste | F/X: Fill/Del | M: Move | P: Platform"
            elif editor.mode == 'MOVE': instr = "ARROWS: Move | ENTER: Confirm"
            safe_addstr(stdscr, h-2, 1, instr, curses.color_pair(Colors.DIM))
        else:
             safe_addstr(stdscr, h-2, 1, "PREVIEWING... PRESS '0' TO STOP", curses.color_pair(Colors.SPECIAL))

        # Inputs
        k = stdscr.getch()
        if k == -1: curses.napms(30); continue
        if k in (ord('h'), ord('?')): show_help = True; continue
        if k in (ord('q'), ord('Q')): break
        if k == ord('0'):
            editor.mode = 'PREVIEW' if editor.mode != 'PREVIEW' else 'PAINT'
            editor.start_time = time.time(); editor.sel_anchor = None
            continue
        if editor.mode == 'PREVIEW': continue

        # Cursor Move
        if k == curses.KEY_UP: editor.cy = max(0, editor.cy - 1)
        elif k == curses.KEY_DOWN: editor.cy = min(gh - 1, editor.cy + 1)
        elif k == curses.KEY_LEFT: editor.cx = max(0, editor.cx - 1)
        elif k == curses.KEY_RIGHT: editor.cx = min(gw - 1, editor.cx + 1)

        # Actions
        elif editor.mode == 'MOVE':
            if k == curses.KEY_UP: editor.move_selection(0, -1)
            elif k == curses.KEY_DOWN: editor.move_selection(0, 1)
            elif k == curses.KEY_LEFT: editor.move_selection(-1, 0)
            elif k == curses.KEY_RIGHT: editor.move_selection(1, 0)
            elif k in (10, 13): editor.mode = 'SELECT'; editor.msg = "Placed"

        elif editor.mode == 'PAINT':
            if k == 9: editor.mode = 'SELECT'
            elif ord('1') <= k <= ord('9'): editor.brush_idx = min(len(BRUSHES)-1, k - ord('1'))
            elif k == ord(' '): editor.paint(editor.cx, editor.cy)
            elif k in (curses.KEY_BACKSPACE, 127, curses.KEY_DC): editor.paint(editor.cx, editor.cy, TILE_EMPTY)
            elif k in (ord('p'), ord('P')): editor.open_platform_wizard(stdscr)
            elif k in (ord('e'), ord('E')): editor.trigger_plugin_context(stdscr)
            elif k in (ord('s'), ord('S')): editor.save_level(); editor.msg = "Saved!"
            elif k in (ord('n'), ord('N')):
                 t = get_string_input(stdscr, "Level Title", editor.meta.get('title',''))
                 if t: editor.meta['title'] = t
            elif k in (ord('r'), ord('R')): editor.resize_map(stdscr)

        elif editor.mode == 'SELECT':
            if k == 9: editor.mode = 'PAINT'; editor.sel_anchor = None
            elif k == ord(' '):
                editor.sel_anchor = None if editor.sel_anchor else (editor.cx, editor.cy)
            elif not editor.sel_anchor:
                if k in (ord('v'), ord('V')): editor.manipulate_selection('paste')
                elif k in (ord('p'), ord('P')): editor.open_platform_wizard(stdscr)
            else:
                if k in (ord('f'), ord('F')): editor.manipulate_selection('fill')
                elif k in (ord('x'), ord('X')): editor.manipulate_selection('delete')
                elif k in (ord('c'), ord('C')): editor.manipulate_selection('copy')
                elif k in (ord('h'), ord('H')): editor.manipulate_selection('flip_h')
                elif k in (ord('y'), ord('Y')): editor.manipulate_selection('flip_v')
                elif k in (ord('m'), ord('M')): editor.mode = 'MOVE'
                elif k in (ord('p'), ord('P')): editor.open_platform_wizard(stdscr); editor.mode = 'PAINT'

def draw_help_menu(stdscr):
    sections = [
        ("GLOBAL", [("H/?", "Help"), ("TAB", "Mode"), ("0", "Preview"), ("S", "Save"), ("Q", "Quit")]),
        ("PAINT", [("1-9", "Brush"), ("SPACE", "Paint"), ("E", "Edit Data"), ("P", "Platform")]),
        ("SELECT", [("SPACE", "Anchor"), ("C/V", "Copy/Paste"), ("M", "Move"), ("P", "Platform")])
    ]
    h, w = stdscr.getmaxyx()
    box_w, box_h = 60, sum(len(s[1]) + 2 for s in sections) + 4
    bx, by = (w - box_w) // 2, (h - box_h) // 2
    for y in range(by, by+box_h): safe_addstr(stdscr, y, bx, " " * box_w, curses.color_pair(Colors.UI))
    safe_addstr(stdscr, by, bx, "+" + "-"*(box_w-2) + "+", curses.color_pair(Colors.UI))
    cy = by + 2
    for title, keys in sections:
        safe_addstr(stdscr, cy, bx + 2, f"[{title}]", curses.color_pair(Colors.SPECIAL))
        cy += 1
        for k, desc in keys:
            safe_addstr(stdscr, cy, bx + 4, f"{k}: {desc}", curses.color_pair(Colors.SOLID))
            cy += 1
        cy += 1

if __name__ == "__main__":
    try: curses.wrapper(main)
    except Exception as e: print(f"Fatal Error: {e}")
