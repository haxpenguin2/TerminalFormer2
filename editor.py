#!/usr/bin/env python3
import curses, sys, os

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

BRUSHES = [
    (TILE_SOLID, "SOLID"),
    (TILE_SPIKE, "SPIKE UP"),
    (TILE_SPIKE_DOWN, "SPIKE DOWN"),
    (TILE_CHECKPOINT, "CHECKPOINT"),
    (TILE_SPAWN, "SPAWN"),
    (TILE_GOAL, "GOAL"),
    (TILE_EMPTY, "ERASER")
]

# Color Pairs IDs
C_DEFAULT = 1
C_SOLID = 2
C_DANGER = 3
C_SPECIAL = 4
C_UI = 5
C_SELECT = 6
C_CURSOR = 7

def ensure_levels_dir():
    if not os.path.exists(LEVELS_DIR):
        os.makedirs(LEVELS_DIR)

# --- HELPER: APPLY BORDERS ---
def apply_border(grid):
    """Forces the outer rectangle of the grid to be walls."""
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

    if not os.path.exists(path):
        grid = [[TILE_EMPTY for _ in range(w)] for _ in range(h)]
        return apply_border(grid)

    with open(path, 'r') as f:
        lines = [l.rstrip('\n') for l in f.readlines()]

    if not lines:
        grid = [[TILE_EMPTY for _ in range(w)] for _ in range(h)]
        return apply_border(grid)

    file_w = max(len(l) for l in lines)
    grid = [list(l.ljust(file_w, ' ')) for l in lines]
    return grid

def save_level(filename, grid):
    ensure_levels_dir()
    path = os.path.join(LEVELS_DIR, filename)
    with open(path, 'w') as f:
        for row in grid:
            f.write("".join(row).rstrip() + "\n")

# --- INPUT HELPER ---
def get_number_input(stdscr, prompt, current_val):
    stdscr.nodelay(False)
    curses.flushinp()
    curses.echo()
    curses.curs_set(1)

    h, w = stdscr.getmaxyx()
    box_w, box_h = 44, 7
    bx = (w - box_w) // 2
    by = (h - box_h) // 2

    for y in range(by, by+box_h):
        stdscr.addstr(y, bx, " " * box_w, curses.color_pair(C_UI) | curses.A_REVERSE)

    try:
        stdscr.addstr(by, bx, "+" + "-"*(box_w-2) + "+", curses.color_pair(C_UI) | curses.A_REVERSE)
        stdscr.addstr(by+box_h-1, bx, "+" + "-"*(box_w-2) + "+", curses.color_pair(C_UI) | curses.A_REVERSE)
    except: pass

    stdscr.addstr(by + 2, bx + 2, prompt, curses.color_pair(C_UI) | curses.A_REVERSE | curses.A_BOLD)
    stdscr.addstr(by + 3, bx + 2, f"Current Size: {current_val}", curses.color_pair(C_UI) | curses.A_REVERSE)
    stdscr.addstr(by + 4, bx + 2, "New Size: ", curses.color_pair(C_UI) | curses.A_REVERSE)

    stdscr.refresh()
    val = None
    try:
        inp = stdscr.getstr(by + 4, bx + 12, 5).decode('utf-8')
        if inp.strip(): val = int(inp)
    except: pass

    curses.noecho()
    curses.curs_set(0)
    stdscr.nodelay(True)
    return val

class Editor:
    def __init__(self, filename):
        self.filename = filename
        self.grid = load_level(filename)
        self.cam_x = 0
        self.cam_y = 0
        self.brush_idx = 0
        self.mode = 'PAINT' # PAINT, SELECT, MOVE
        self.cx = 0
        self.cy = 0
        self.sel_anchor = None
        self.clipboard = None
        self.msg = f"Loaded {filename}"
        self.msg_timer = 50

    def grid_dims(self):
        h = len(self.grid)
        w = len(self.grid[0]) if h > 0 else 0
        return w, h

    def set_size(self, w_new, h_new):
        old_w, old_h = self.grid_dims()
        # Clean old borders
        if w_new is not None and w_new > old_w:
            for y in range(old_h): self.grid[y][old_w - 1] = TILE_EMPTY
        if h_new is not None and h_new > old_h:
            for x in range(len(self.grid[0])): self.grid[old_h - 1][x] = TILE_EMPTY

        # Resize
        if w_new is not None:
            w_new = max(5, w_new)
            for i in range(len(self.grid)):
                row = self.grid[i]
                if w_new > len(row): row.extend([TILE_EMPTY] * (w_new - len(row)))
                else: self.grid[i] = row[:w_new]

        if h_new is not None:
            h_new = max(5, h_new)
            cur_w = len(self.grid[0])
            if h_new > len(self.grid):
                for _ in range(h_new - len(self.grid)): self.grid.append([TILE_EMPTY] * cur_w)
            else: self.grid = self.grid[:h_new]

        apply_border(self.grid)
        new_w, new_h = self.grid_dims()
        self.cx = min(self.cx, new_w - 1)
        self.cy = min(self.cy, new_h - 1)
        self.msg = f"Resized to {self.grid_dims()}"
        self.msg_timer = 30

    def get_cell(self, x, y):
        if 0 <= y < len(self.grid) and 0 <= x < len(self.grid[0]):
            return self.grid[y][x]
        return None

    def paint(self, x, y, brush=None):
        if brush is None: brush = BRUSHES[self.brush_idx][0]
        h = len(self.grid)
        w = len(self.grid[0]) if h > 0 else 0
        if 0 <= y < h and 0 <= x < w:
            self.grid[y][x] = brush

    def smart_toggle(self):
        cell = self.get_cell(self.cx, self.cy)
        if cell is None: return
        if cell != TILE_EMPTY:
            self.paint(self.cx, self.cy, TILE_EMPTY)
            self.msg = "Deleted"
        else:
            self.paint(self.cx, self.cy, BRUSHES[self.brush_idx][0])
            self.msg = "Placed"
        self.msg_timer = 20

    def rotate_brush(self):
        curr = BRUSHES[self.brush_idx][0]
        target = TILE_SPIKE_DOWN if curr == TILE_SPIKE else (TILE_SPIKE if curr == TILE_SPIKE_DOWN else None)
        if target:
            for i, b in enumerate(BRUSHES):
                if b[0] == target:
                    self.brush_idx = i
                    self.msg = f"Rotated to {b[1]}"
                    self.msg_timer = 20
                    return

    def get_selection_bounds(self):
        if not self.sel_anchor: return None
        x1, y1 = self.sel_anchor
        x2, y2 = self.cx, self.cy
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def fill_selection(self):
        b = self.get_selection_bounds()
        if not b: return
        x1, y1, x2, y2 = b
        char = BRUSHES[self.brush_idx][0]
        for y in range(y1, y2+1):
            for x in range(x1, x2+1): self.paint(x, y, char)
        self.msg = "Filled"
        self.sel_anchor = None

    def delete_selection(self):
        b = self.get_selection_bounds()
        if not b: return
        x1, y1, x2, y2 = b
        for y in range(y1, y2+1):
            for x in range(x1, x2+1): self.paint(x, y, TILE_EMPTY)
        self.msg = "Deleted"
        self.sel_anchor = None

    def copy_selection(self):
        b = self.get_selection_bounds()
        if not b: return
        x1, y1, x2, y2 = b
        self.clipboard = []
        for y in range(y1, y2+1):
            self.clipboard.append([self.get_cell(x, y) for x in range(x1, x2+1)])
        self.msg = "Copied"
        self.sel_anchor = None

    def paste_at_cursor(self):
        if not self.clipboard: return
        for r, row in enumerate(self.clipboard):
            for c, val in enumerate(row):
                self.paint(self.cx + c, self.cy + r, val)
        self.msg = "Pasted"

    # --- NEW: FLIP FUNCTIONS ---
    def flip_selection(self, axis):
        """
        axis: 'horizontal' or 'vertical'
        """
        b = self.get_selection_bounds()
        if not b:
            self.msg = "No Selection"; self.msg_timer = 20
            return

        x1, y1, x2, y2 = b

        # 1. Extract Data
        data = []
        for y in range(y1, y2+1):
            data.append([self.get_cell(x, y) for x in range(x1, x2+1)])

        # 2. Clear old area
        for y in range(y1, y2+1):
            for x in range(x1, x2+1): self.paint(x, y, TILE_EMPTY)

        # 3. Transform Data
        if axis == 'vertical':
            data.reverse() # Reverse rows
            # Swap directions
            for r in range(len(data)):
                for c in range(len(data[r])):
                    char = data[r][c]
                    if char == TILE_SPIKE: data[r][c] = TILE_SPIKE_DOWN
                    elif char == TILE_SPIKE_DOWN: data[r][c] = TILE_SPIKE
        elif axis == 'horizontal':
            for row in data:
                row.reverse() # Reverse items in row

        # 4. Paste back
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.paint(x1 + c, y1 + r, val)

        self.msg = f"Flipped {axis.capitalize()}"
        self.msg_timer = 20

    # --- MOVE SELECTION LOGIC ---
    def move_selection_step(self, dx, dy):
        b = self.get_selection_bounds()
        if not b: return
        x1, y1, x2, y2 = b

        # 1. Copy data
        data = []
        for y in range(y1, y2+1):
            data.append([self.get_cell(x, y) for x in range(x1, x2+1)])

        # 2. Delete Old
        for y in range(y1, y2+1):
            for x in range(x1, x2+1): self.paint(x, y, TILE_EMPTY)

        # 3. Update Anchor and Cursor
        self.sel_anchor = (self.sel_anchor[0] + dx, self.sel_anchor[1] + dy)
        self.cx += dx
        self.cy += dy

        # 4. Paste New
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                self.paint(x1 + dx + c, y1 + dy + r, val)

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)

    # Colors
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(C_DEFAULT, curses.COLOR_WHITE, -1)
        curses.init_pair(C_SOLID, curses.COLOR_WHITE, -1)
        curses.init_pair(C_DANGER, curses.COLOR_RED, -1) # Made Spikes Red for visibility
        curses.init_pair(C_SPECIAL, curses.COLOR_GREEN, -1)
        curses.init_pair(C_UI, curses.COLOR_CYAN, -1)
        curses.init_pair(C_SELECT, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(C_CURSOR, curses.COLOR_BLACK, curses.COLOR_CYAN)
    else:
        for i in range(1, 8): curses.init_pair(i, 0, 0)

    filename = DEFAULT_FILE
    if len(sys.argv) > 1: filename = sys.argv[1]
    editor = Editor(filename)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        grid_w, grid_h = editor.grid_dims()

        # Camera
        if editor.cx < editor.cam_x + 2: editor.cam_x = max(0, editor.cx - 2)
        if editor.cx >= editor.cam_x + w - 2: editor.cam_x = editor.cx - (w - 3)
        if editor.cy < editor.cam_y + 2: editor.cam_y = max(0, editor.cy - 2)
        if editor.cy >= editor.cam_y + h - 6: editor.cam_y = editor.cy - (h - 7)

        offset_x = (w - grid_w) // 2 if grid_w < w else -editor.cam_x
        offset_y = (h - grid_h) // 2 if grid_h < h - 4 else -editor.cam_y

        # Draw Grid
        bounds = editor.get_selection_bounds()
        for r in range(grid_h):
            scr_y = offset_y + r
            if not (0 <= scr_y < h - 4): continue
            row_str = editor.grid[r]
            for c in range(len(row_str)):
                scr_x = offset_x + c
                if not (0 <= scr_x < w): continue
                char = row_str[c]
                pair = C_DEFAULT
                if char == TILE_SOLID: pair = C_SOLID
                elif char in [TILE_SPIKE, TILE_SPIKE_DOWN]: pair = C_DANGER
                elif char in [TILE_SPAWN, TILE_GOAL, TILE_CHECKPOINT]: pair = C_SPECIAL
                attr = curses.color_pair(pair)

                if bounds and (bounds[0] <= c <= bounds[2] and bounds[1] <= r <= bounds[3]):
                    attr = curses.color_pair(C_SELECT)

                if c == editor.cx and r == editor.cy:
                    attr = curses.color_pair(C_CURSOR) | curses.A_BOLD

                try: stdscr.addch(scr_y, scr_x, char, attr)
                except: pass

        # Draw UI
        mode_color = curses.color_pair(C_UI)
        if editor.mode == 'SELECT': mode_color = curses.color_pair(C_SELECT) | curses.A_BOLD
        if editor.mode == 'MOVE': mode_color = curses.color_pair(C_DANGER) | curses.A_REVERSE

        header = f" {editor.mode} "
        info = f" Pos: {editor.cx},{editor.cy} | Size: {grid_w}x{grid_h} "
        stdscr.addstr(0, 0, header, mode_color)
        stdscr.addstr(0, len(header), info, curses.color_pair(C_UI))

        if editor.msg:
            stdscr.addstr(0, w - len(editor.msg) - 2, editor.msg, curses.color_pair(C_UI) | curses.A_REVERSE)
            editor.msg_timer -= 1
            if editor.msg_timer <= 0: editor.msg = None

        brush_c, brush_n = BRUSHES[editor.brush_idx]
        stdscr.addstr(h-4, 1, "BRUSH: ", curses.color_pair(C_UI))
        stdscr.addstr(h-4, 8, f"[{brush_c}] {brush_n} (1-7)", curses.color_pair(C_SOLID))

        # Dynamic Instructions
        instr = ""
        if editor.mode == 'PAINT':
            instr = "ARROWS: Move | SPACE: Paint | R: Rotate Spike | TAB: Select Mode | S: Save | Q: Quit"
        elif editor.mode == 'SELECT':
            instr = "SPACE: Set Anchor | M: Move Sel | V: Flip Vert | H: Flip Horz | C/P: Copy/Paste | X: Del"
        elif editor.mode == 'MOVE':
            instr = "ARROWS: Move Selection | ENTER/M: Confirm Place"

        stdscr.addstr(h-2, 1, instr, curses.color_pair(C_UI) | curses.A_DIM)

        # Input Handling
        key = stdscr.getch()

        # MOVEMENT MODE INTERCEPTION
        if editor.mode == 'MOVE':
            if key == curses.KEY_UP: editor.move_selection_step(0, -1)
            elif key == curses.KEY_DOWN: editor.move_selection_step(0, 1)
            elif key == curses.KEY_LEFT: editor.move_selection_step(-1, 0)
            elif key == curses.KEY_RIGHT: editor.move_selection_step(1, 0)
            elif key in (10, 13, ord('m'), ord('M'), 27): # Enter, M or Esc to Drop
                editor.mode = 'SELECT'
                editor.msg = "Moved"
            continue

        # STANDARD MODES
        if key == curses.KEY_UP: editor.cy = max(0, editor.cy - 1)
        elif key == curses.KEY_DOWN: editor.cy = min(grid_h - 1, editor.cy + 1)
        elif key == curses.KEY_LEFT: editor.cx = max(0, editor.cx - 1)
        elif key == curses.KEY_RIGHT: editor.cx = min(grid_w - 1, editor.cx + 1)

        elif ord('1') <= key <= ord('7'): editor.brush_idx = key - ord('1')
        elif key in (ord('r'), ord('R')): editor.rotate_brush()
        elif key in (ord('w'), ord('W')):
            new_w = get_number_input(stdscr, "WIDTH", grid_w)
            if new_w: editor.set_size(new_w, None)
        elif key in (ord('h'), ord('H')) and editor.mode == 'PAINT': # Only resize height in paint mode to avoid conflict with flip
             new_h = get_number_input(stdscr, "HEIGHT", grid_h)
             if new_h: editor.set_size(None, new_h)

        elif key == 9: # TAB
            editor.mode = 'SELECT' if editor.mode == 'PAINT' else 'PAINT'
            editor.sel_anchor = None

        elif key in (ord('t'), ord('T')): editor.smart_toggle()
        elif key == ord(' '):
            if editor.mode == 'PAINT': editor.paint(editor.cx, editor.cy)
            elif editor.mode == 'SELECT':
                if editor.sel_anchor is None:
                    editor.sel_anchor = (editor.cx, editor.cy)
                    editor.msg = "Anchor Set"
                else:
                    editor.sel_anchor = None
                    editor.msg = "Anchor Cleared"

        # SELECTION COMMANDS
        if editor.mode == 'SELECT' and editor.sel_anchor:
            if key in (ord('x'), ord('X')): editor.delete_selection()
            elif key in (ord('f'), ord('F')): editor.fill_selection()
            elif key in (ord('c'), ord('C')): editor.copy_selection()
            elif key in (ord('p'), ord('P')): editor.paste_at_cursor()

            # FLIP COMMANDS
            elif key in (ord('v'), ord('V')): editor.flip_selection('vertical')
            elif key in (ord('h'), ord('H')): editor.flip_selection('horizontal')

            # MOVE COMMAND
            elif key in (ord('m'), ord('M')):
                 editor.mode = 'MOVE'
                 editor.msg = "MOVE MODE"

        if key in (ord('s'), ord('S')):
            save_level(editor.filename, editor.grid)
            editor.msg = "SAVED!"
            editor.msg_timer = 30
        elif key in (ord('q'), ord('Q')): break

if __name__ == "__main__":
    curses.wrapper(main)
