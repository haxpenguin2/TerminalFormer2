#!/usr/bin/env python3
import curses, sys, os, json, time, math

# --- CONFIGURATION ---
LEVELS_DIR = "levels"
DEFAULT_FILE = "level1.txt"

# Tile Definitions
TILE_EMPTY = ' '
TILE_SOLID = '█'
TILE_SPIKE = '▲'
TILE_SPIKE_DOWN = '▼'
TILE_CHECKPOINT = 'C'
TILE_SPAWN = 'S'
TILE_GOAL = 'G'
# Internal Editor ID for platform (looks like Solid in game, Yellow in Editor)
TILE_PLATFORM = '='

BRUSHES = [
    (TILE_SOLID, "SOLID"),
    (TILE_SPIKE, "SPIKE UP"),
    (TILE_SPIKE_DOWN, "SPIKE DOWN"),
    (TILE_CHECKPOINT, "CHECKPOINT"),
    (TILE_SPAWN, "SPAWN"),
    (TILE_GOAL, "GOAL"),
    (TILE_PLATFORM, "PLATFORM (Select -> P)"),
    (TILE_EMPTY, "ERASER")
]

# Colors
C_DEFAULT = 1
C_SOLID = 2
C_DANGER = 3
C_SPECIAL = 4
C_UI = 5
C_SELECT = 6
C_CURSOR = 7
C_PLATFORM_EDIT = 8  # Yellow (Editing)
C_PLATFORM_GAME = 9  # White (Preview)

def ensure_levels_dir():
    if not os.path.exists(LEVELS_DIR): os.makedirs(LEVELS_DIR)

# --- CRASH PROTECTION: SAFE DRAWING ---
def safe_addch(stdscr, y, x, ch, attr=0):
    """Draws a character only if it fits on screen."""
    h, w = stdscr.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        try: stdscr.addch(y, x, ch, attr)
        except curses.error: pass

def safe_addstr(stdscr, y, x, s, attr=0):
    """Draws a string, clipping it if it hits the edge."""
    h, w = stdscr.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        # Clip string length to avoid wrapping or bottom-right corner crash
        if x + len(s) >= w:
            s = s[:w - x - 1]
        try: stdscr.addstr(y, x, s, attr)
        except curses.error: pass

# --- HELPER: BORDERS & IO ---
def apply_border(grid):
    h = len(grid)
    if h == 0: return grid
    w = len(grid[0])
    for y in range(h):
        grid[y][0] = TILE_SOLID
        grid[y][w-1] = TILE_SOLID
    for x in range(w):
        grid[0][x] = TILE_SOLID
        grid[h-1][x] = TILE_SOLID
    return grid

def load_level(filename):
    ensure_levels_dir()
    path = os.path.join(LEVELS_DIR, filename)
    w, h = 40, 20
    platforms = []
    meta = {"title": "Untitled Level"}
    grid = [[TILE_EMPTY for _ in range(w)] for _ in range(h)]
    grid = apply_border(grid)

    if os.path.exists(path):
        with open(path, 'r') as f: content = f.read()
        parts = content.split("__METADATA__")

        # 1. Load Grid
        lines = [l.rstrip('\n') for l in parts[0].strip().split('\n')]
        if lines:
            file_w = max(len(l) for l in lines)
            grid = [list(l.ljust(file_w, ' ')) for l in lines]

        # 2. Load Metadata & Platforms
        if len(parts) > 1:
            try:
                data = json.loads(parts[1])
                if isinstance(data, list):
                    platforms = data
                elif isinstance(data, dict):
                    meta['title'] = data.get('title', "Untitled Level")
                    platforms = data.get('platforms', [])
            except: pass

    # Post-Process: Mark platform tiles in the editor grid
    for p in platforms:
        px, py, pw = int(p['x']), int(p['y']), int(p['w'])
        if 0 <= py < len(grid):
            for i in range(pw):
                if 0 <= px + i < len(grid[0]):
                    grid[py][px + i] = TILE_PLATFORM

    return grid, platforms, meta

def save_level(filename, grid, platforms, meta):
    ensure_levels_dir()
    path = os.path.join(LEVELS_DIR, filename)

    # 1. Prune orphaned platform data
    valid_platforms = []
    for p in platforms:
        try:
            # Check if the origin is still a platform tile
            if grid[int(p['y'])][int(p['x'])] == TILE_PLATFORM:
                valid_platforms.append(p)
        except IndexError: pass

    # 2. Prepare Grid for Export
    export_grid = []
    for row in grid:
        new_row = ""
        for char in row:
            if char == TILE_PLATFORM: new_row += TILE_SOLID
            else: new_row += char
        export_grid.append(new_row)

    json_data = {
        "title": meta['title'],
        "platforms": valid_platforms
    }

    with open(path, 'w') as f:
        for row in export_grid:
            f.write(row.rstrip() + "\n")
        f.write("\n__METADATA__\n")
        json.dump(json_data, f)

# --- UI BOXES ---
def draw_box(stdscr, title, lines):
    h, w = stdscr.getmaxyx()
    box_w = 50
    box_h = len(lines) + 4
    bx = (w - box_w) // 2
    by = (h - box_h) // 2

    # Draw Box Background
    for y in range(by, by+box_h):
        safe_addstr(stdscr, y, bx, " " * box_w, curses.color_pair(C_UI) | curses.A_REVERSE)

    # Draw Borders
    safe_addstr(stdscr, by, bx, "+" + "-"*(box_w-2) + "+", curses.color_pair(C_UI) | curses.A_REVERSE)
    safe_addstr(stdscr, by+box_h-1, bx, "+" + "-"*(box_w-2) + "+", curses.color_pair(C_UI) | curses.A_REVERSE)

    # Title
    safe_addstr(stdscr, by + 1, bx + 2, title.center(box_w - 4), curses.color_pair(C_UI) | curses.A_REVERSE | curses.A_BOLD)

    # Content
    for i, line in enumerate(lines):
        safe_addstr(stdscr, by + 3 + i, bx + 2, line, curses.color_pair(C_UI) | curses.A_REVERSE)

    return bx, by, box_w, box_h

def get_string_input(stdscr, prompt, default=""):
    stdscr.nodelay(False); curses.echo(); curses.curs_set(1)
    bx, by, bw, bh = draw_box(stdscr, prompt, [f"Current: {default}", "New Value: "])

    val = default
    try:
        # Move cursor safely
        safe_addstr(stdscr, by + 4, bx + 13, "")
        inp = stdscr.getstr(by + 4, bx + 13, 20).decode('utf-8')
        if inp.strip(): val = inp.strip()
    except: pass

    curses.noecho(); curses.curs_set(0); stdscr.nodelay(True)
    return val

class Editor:
    def __init__(self, filename):
        self.filename = filename
        self.grid, self.platforms, self.meta = load_level(filename)
        self.cam_x, self.cam_y = 0, 0
        self.brush_idx = 0
        self.mode = 'PAINT' # PAINT, SELECT, MOVE, PREVIEW
        self.cx, self.cy = 1, 1
        self.sel_anchor = None
        self.clipboard = None
        self.msg = f"Loaded {filename}"
        self.msg_timer = 50
        self.start_time = time.time()

    def grid_dims(self):
        return (len(self.grid[0]) if len(self.grid) > 0 else 0), len(self.grid)

    def paint(self, x, y, brush=None):
        if brush is None: brush = BRUSHES[self.brush_idx][0]
        h = len(self.grid); w = len(self.grid[0]) if h > 0 else 0
        if 0 <= y < h and 0 <= x < w:
            self.grid[y][x] = brush

    def get_cell(self, x, y):
        h = len(self.grid); w = len(self.grid[0]) if h > 0 else 0
        if 0 <= y < h and 0 <= x < w: return self.grid[y][x]
        return TILE_EMPTY

    def get_selection_bounds(self):
        if not self.sel_anchor: return None
        x1, y1 = self.sel_anchor; x2, y2 = self.cx, self.cy
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def get_platform_at(self, x, y):
        for p in self.platforms:
            if p['y'] == y and p['x'] <= x < p['x'] + p['w']:
                return p
        return None

    # --- TOOLS ---
    def resize_map(self, stdscr):
        cur_w, cur_h = self.grid_dims()
        try:
            new_w_str = get_string_input(stdscr, "Resize Width", str(cur_w))
            new_h_str = get_string_input(stdscr, "Resize Height", str(cur_h))
            new_w = int(new_w_str)
            new_h = int(new_h_str)
        except ValueError:
            self.msg = "Invalid Size"; return

        if new_w < 5 or new_h < 5:
            self.msg = "Too Small"; return

        new_grid = [[TILE_EMPTY for _ in range(new_w)] for _ in range(new_h)]
        copy_h = min(cur_h, new_h)
        copy_w = min(cur_w, new_w)

        for y in range(copy_h):
            for x in range(copy_w):
                new_grid[y][x] = self.grid[y][x]

        new_grid = apply_border(new_grid)
        self.grid = new_grid
        self.msg = f"Resized to {new_w}x{new_h}"

    def fill_selection(self):
        b = self.get_selection_bounds()
        if not b: return
        for y in range(b[1], b[3]+1):
            for x in range(b[0], b[2]+1): self.paint(x, y)
        self.msg = "Filled"; self.sel_anchor = None

    def delete_selection(self):
        b = self.get_selection_bounds()
        if not b: return
        for y in range(b[1], b[3]+1):
            for x in range(b[0], b[2]+1): self.paint(x, y, TILE_EMPTY)
        self.msg = "Deleted"; self.sel_anchor = None

    def copy_selection(self):
        b = self.get_selection_bounds()
        if not b: return
        self.clipboard = []
        for y in range(b[1], b[3]+1):
            self.clipboard.append([self.get_cell(x, y) for x in range(b[0], b[2]+1)])
        self.msg = "Copied"; self.sel_anchor = None

    def paste_selection(self):
        if not self.clipboard: self.msg = "Clipboard Empty"; return
        for r, row in enumerate(self.clipboard):
            for c, val in enumerate(row):
                self.paint(self.cx + c, self.cy + r, val)
        self.msg = "Pasted"

    def flip_selection(self, axis):
        b = self.get_selection_bounds()
        if not b: return
        data = []
        for y in range(b[1], b[3]+1):
            data.append([self.get_cell(x, y) for x in range(b[0], b[2]+1)])

        for y in range(b[1], b[3]+1):
            for x in range(b[0], b[2]+1): self.paint(x, y, TILE_EMPTY)

        if axis == 'V': data.reverse()
        else:
            for row in data: row.reverse()

        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.paint(b[0]+c, b[1]+r, val)
        self.msg = f"Flipped {axis}"; self.sel_anchor = None

    def move_selection_step(self, dx, dy):
        b = self.get_selection_bounds()
        if not b: return

        # Update Visual Grid
        data = []
        for y in range(b[1], b[3]+1):
            data.append([self.get_cell(x, y) for x in range(b[0], b[2]+1)])

        for y in range(b[1], b[3]+1):
            for x in range(b[0], b[2]+1): self.paint(x, y, TILE_EMPTY)

        self.sel_anchor = (self.sel_anchor[0]+dx, self.sel_anchor[1]+dy)
        self.cx += dx; self.cy += dy

        # Update Hidden Platform Data
        old_x1, old_y1 = b[0], b[1]
        old_x2, old_y2 = b[2], b[3]

        for p in self.platforms:
            if old_y1 <= p['y'] <= old_y2 and old_x1 <= p['x'] <= old_x2:
                p['x'] += dx
                p['y'] += dy

        # Repaint Visuals
        new_b = self.get_selection_bounds()
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.paint(new_b[0]+c, new_b[1]+r, val)

    # --- PLATFORM WIZARD (Edit or Create) ---
    def open_platform_wizard(self, stdscr):
        existing_p = self.get_platform_at(self.cx, self.cy)

        if not self.sel_anchor and existing_p:
            # EDIT MODE
            dir_def = "H" if existing_p.get('lx',0) != 0 else "V"
            range_val = existing_p.get('lx',0) if dir_def == 'H' else existing_p.get('ly',0)
            range_def = str(range_val)
            spd_def = str(existing_p.get('spd', 1.0))

            dir_s = get_string_input(stdscr, "Direction (H/V)", dir_def).upper()
            rng = float(get_string_input(stdscr, "Range (Total Swing)", range_def))
            spd = float(get_string_input(stdscr, "Speed", spd_def))

            existing_p['lx'] = rng if dir_s == 'H' else 0
            existing_p['ly'] = rng if dir_s != 'H' else 0
            existing_p['spd'] = spd
            self.msg = "Platform Updated!"
            return

        # CREATE MODE
        b = self.get_selection_bounds()
        if not b: self.msg = "Select area or hover platform!"; self.msg_timer=30; return
        if b[1] != b[3]: self.msg = "Height must be 1!"; self.msg_timer=30; return

        dir_s = get_string_input(stdscr, "Direction (H/V)", "H").upper()
        rng = float(get_string_input(stdscr, "Range (Total Swing)", "6"))
        spd = float(get_string_input(stdscr, "Speed", "2.0"))

        lx = rng if dir_s == 'H' else 0
        ly = rng if dir_s != 'H' else 0

        for x in range(b[0], b[2]+1): self.paint(x, b[1], TILE_PLATFORM)

        # Remove overlaps
        self.platforms = [p for p in self.platforms if not (p['y']==b[1] and p['x']>=b[0] and p['x']<=b[2])]

        self.platforms.append({
            "x": b[0], "y": b[1], "w": (b[2]-b[0]+1),
            "lx": lx, "ly": ly, "spd": spd, "ease": "SINE"
        })
        self.msg = "Platform Created!"; self.sel_anchor = None

def main(stdscr):
    # Crash Prevention Setup
    curses.curs_set(0); stdscr.nodelay(True)
    if curses.has_colors():
        curses.start_color(); curses.use_default_colors()
        for i in range(1, 10):
            curses.init_pair(i, curses.COLOR_WHITE, -1)

        # Override specific colors
        curses.init_pair(C_SOLID, curses.COLOR_WHITE, -1)
        curses.init_pair(C_DANGER, curses.COLOR_RED, -1)
        curses.init_pair(C_SPECIAL, curses.COLOR_GREEN, -1)
        curses.init_pair(C_UI, curses.COLOR_CYAN, -1)
        curses.init_pair(C_SELECT, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(C_CURSOR, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(C_PLATFORM_EDIT, curses.COLOR_YELLOW, -1)
        curses.init_pair(C_PLATFORM_GAME, curses.COLOR_WHITE, -1)

    filename = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    editor = Editor(filename)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        gw, gh = editor.grid_dims()

        # --- CAMERA ---
        # Keep camera safe bounds
        if editor.cx < editor.cam_x + 2: editor.cam_x = max(0, editor.cx - 2)
        if editor.cx >= editor.cam_x + w - 2: editor.cam_x = editor.cx - (w - 3)
        if editor.cy < editor.cam_y + 2: editor.cam_y = max(0, editor.cy - 2)
        if editor.cy >= editor.cam_y + h - 6: editor.cam_y = editor.cy - (h - 7)

        off_x = (w - gw) // 2 if gw < w else -editor.cam_x
        off_y = (h - gh) // 2 if gh < h - 4 else -editor.cam_y

        # --- RENDER GRID ---
        bounds = editor.get_selection_bounds()

        for r in range(gh):
            scr_y = off_y + r
            if not (0 <= scr_y < h - 4): continue
            for c in range(gw):
                scr_x = off_x + c
                if not (0 <= scr_x < w): continue

                char = editor.grid[r][c]

                if editor.mode == 'PREVIEW' and char == TILE_PLATFORM:
                    char = TILE_EMPTY

                pair = C_DEFAULT
                disp_char = char

                if char == TILE_SOLID: pair = C_SOLID
                elif char in [TILE_SPIKE, TILE_SPIKE_DOWN]: pair = C_DANGER
                elif char in [TILE_SPAWN, TILE_GOAL, TILE_CHECKPOINT]: pair = C_SPECIAL
                elif char == TILE_PLATFORM:
                    pair = C_PLATFORM_EDIT; disp_char = TILE_SOLID

                attr = curses.color_pair(pair)
                if bounds and (bounds[0] <= c <= bounds[2] and bounds[1] <= r <= bounds[3]):
                    attr = curses.color_pair(C_SELECT)
                if c == editor.cx and r == editor.cy and editor.mode != 'PREVIEW':
                    attr = curses.color_pair(C_CURSOR) | curses.A_BOLD

                safe_addch(stdscr, scr_y, scr_x, disp_char, attr)

        # --- RENDER PREVIEW PHYSICS ---
        if editor.mode == 'PREVIEW':
            now = time.time()
            elapsed = now - editor.start_time
            for p in editor.platforms:
                t = elapsed * p.get('spd', 1.0)
                lx, ly = p.get('lx', 0), p.get('ly', 0)

                # Centered Sine Movement
                offset_x = math.sin(t) * (lx / 2)
                offset_y = math.sin(t) * (ly / 2)

                px = int(p['x'] + offset_x)
                py = int(p['y'] + offset_y)

                if 0 <= off_y+py < h-4:
                    for i in range(p['w']):
                        scr_x_p = off_x + px + i
                        scr_y_p = off_y + py
                        safe_addch(stdscr, scr_y_p, scr_x_p, TILE_SOLID, curses.color_pair(C_PLATFORM_GAME))

        # --- HUD ---
        col = curses.color_pair(C_UI)
        if editor.mode == 'SELECT': col = curses.color_pair(C_SELECT) | curses.A_BOLD
        if editor.mode == 'MOVE': col = curses.color_pair(C_DANGER) | curses.A_REVERSE
        if editor.mode == 'PREVIEW': col = curses.color_pair(C_SPECIAL) | curses.A_REVERSE

        safe_addstr(stdscr, 0, 0, f" {editor.mode} ", col)
        safe_addstr(stdscr, 0, 10, f"Pos:{editor.cx},{editor.cy} Size:{gw}x{gh}", curses.color_pair(C_UI))

        # Metadata Title
        title_str = f"'{editor.meta.get('title', 'Untitled')}'"
        safe_addstr(stdscr, 0, 30, title_str, curses.color_pair(C_SPECIAL))

        # Hover Info
        p_hov = editor.get_platform_at(editor.cx, editor.cy)
        if p_hov and editor.mode != 'PREVIEW':
             rng_val = max(p_hov.get('lx',0), p_hov.get('ly',0))
             info = f"[PLATFORM] Range:{rng_val} Spd:{p_hov.get('spd',1.0)} (Press P)"
             safe_addstr(stdscr, 0, w - len(info) - 1, info, curses.color_pair(C_PLATFORM_EDIT) | curses.A_REVERSE)

        if editor.msg:
            safe_addstr(stdscr, 1, w - len(editor.msg) - 2, editor.msg, curses.color_pair(C_UI) | curses.A_REVERSE)
            editor.msg_timer -= 1
            if editor.msg_timer <= 0: editor.msg = None

        if editor.mode != 'PREVIEW':
            b_c, b_n = BRUSHES[editor.brush_idx]
            disp = TILE_SOLID if b_c == TILE_PLATFORM else b_c
            safe_addstr(stdscr, h-4, 1, f"BRUSH: [{disp}] {b_n}", curses.color_pair(C_SOLID))

            instr = ""
            if editor.mode == 'PAINT': instr = "TAB: Select | 0: Preview | SPACE: Paint | R: Resize | S: Save | N: Rename"
            elif editor.mode == 'SELECT': instr = "SPACE: Anchor | P: Platform | C/V: Copy/Paste | F/X: Fill/Del | M: Move | R: Resize"
            elif editor.mode == 'MOVE': instr = "ARROWS: Move Selection | ENTER: Confirm Place"
            safe_addstr(stdscr, h-2, 1, instr, curses.color_pair(C_UI) | curses.A_DIM)
        else:
            safe_addstr(stdscr, h-2, 1, "PREVIEWING... PRESS 0 TO EDIT", curses.color_pair(C_SPECIAL))

        # --- INPUT ---
        key = stdscr.getch()
        if key == -1:
            curses.napms(30); continue

        # GLOBAL
        if key == ord('0'):
            editor.mode = 'PREVIEW' if editor.mode != 'PREVIEW' else 'PAINT'
            editor.start_time = time.time(); editor.sel_anchor = None
            continue
        if editor.mode == 'PREVIEW': continue
        if key in (ord('q'), ord('Q')): break
        if key in (ord('s'), ord('S')):
            save_level(editor.filename, editor.grid, editor.platforms, editor.meta)
            editor.msg = "SAVED!"; editor.msg_timer=30
            continue
        if key in (ord('n'), ord('N')):
            new_title = get_string_input(stdscr, "Level Title", editor.meta.get('title', ""))
            if new_title: editor.meta['title'] = new_title
            continue
        if key == 9: # TAB
            editor.mode = 'SELECT' if editor.mode == 'PAINT' else 'PAINT'
            editor.sel_anchor = None
            continue
        if key in (ord('r'), ord('R')):
            editor.resize_map(stdscr)
            continue

        # MOVE MODE INTERCEPT
        if editor.mode == 'MOVE':
            if key == curses.KEY_UP: editor.move_selection_step(0, -1)
            elif key == curses.KEY_DOWN: editor.move_selection_step(0, 1)
            elif key == curses.KEY_LEFT: editor.move_selection_step(-1, 0)
            elif key == curses.KEY_RIGHT: editor.move_selection_step(1, 0)
            elif key in (10, 13): editor.mode = 'SELECT'; editor.msg = "Moved"
            continue

        # NAVIGATION
        if key == curses.KEY_UP: editor.cy = max(0, editor.cy - 1)
        elif key == curses.KEY_DOWN: editor.cy = min(gh - 1, editor.cy + 1)
        elif key == curses.KEY_LEFT: editor.cx = max(0, editor.cx - 1)
        elif key == curses.KEY_RIGHT: editor.cx = min(gw - 1, editor.cx + 1)

        # PAINT MODE
        elif editor.mode == 'PAINT':
            if ord('1') <= key <= ord('8'): editor.brush_idx = key - ord('1')
            elif key == ord(' '): editor.paint(editor.cx, editor.cy)
            elif key in (ord('p'), ord('P')):
                if editor.get_platform_at(editor.cx, editor.cy): editor.open_platform_wizard(stdscr)

        # SELECT MODE
        elif editor.mode == 'SELECT':
            if key == ord(' '):
                editor.sel_anchor = None if editor.sel_anchor else (editor.cx, editor.cy)

            # Non-Anchor Actions
            if not editor.sel_anchor:
                if key in (ord('v'), ord('V')): editor.paste_selection()
                elif key in (ord('p'), ord('P')): editor.open_platform_wizard(stdscr)

            # Anchor Actions
            else:
                if key in (ord('f'), ord('F')): editor.fill_selection()
                elif key in (ord('x'), ord('X')): editor.delete_selection()
                elif key in (ord('c'), ord('C')): editor.copy_selection()
                elif key in (ord('h'), ord('H')): editor.flip_selection('H')
                elif key in (ord('y'), ord('Y')): editor.flip_selection('V')
                elif key in (ord('m'), ord('M')): editor.mode = 'MOVE'
                elif key in (ord('p'), ord('P')): editor.open_platform_wizard(stdscr); editor.mode = 'PAINT'

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as e:
        print(f"Error: {e}")
