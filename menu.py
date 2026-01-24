#!/usr/bin/env python3
import curses, os, sys, json, subprocess, random, time, math

# --- CONFIGURATION ---
LEVELS_DIR = "levels"
CAMPAIGN_DIR = "campaignlevels"
SCORES_FILE = "scores.json"

BG_SCROLL_SPEED_X = 1
BG_SCROLL_SPEED_Y = 0

# --- MOVING PLATFORM LOGIC ---
class MovingPlatform:
    def __init__(self, data):
        self.x_origin = data['x']
        self.y_origin = data['y']
        self.w = data['w']
        self.limit_x = data.get('lx', 0)
        self.limit_y = data.get('ly', 0)
        self.speed = data.get('spd', 1.0)
        self.easing = data.get('ease', 'SINE')

        self.x = self.x_origin
        self.y = self.y_origin
        self.timer = 0.0

    def update(self, dt):
        self.timer += dt * self.speed
        offset = 0
        if self.easing == 'SINE':
            offset = math.sin(self.timer)
        else:
            t = (self.timer / math.pi) % 2
            offset = (t - 1) if t > 1 else (1 - t)

        self.x = self.x_origin + (offset * (self.limit_x / 2))
        self.y = self.y_origin + (offset * (self.limit_y / 2))

# --- FILE OPERATIONS ---
def ensure_dirs():
    if not os.path.exists(LEVELS_DIR): os.makedirs(LEVELS_DIR)
    if not os.path.exists(CAMPAIGN_DIR): os.makedirs(CAMPAIGN_DIR)

def get_custom_levels():
    ensure_dirs()
    return sorted([f for f in os.listdir(LEVELS_DIR) if f.endswith(".txt")])

def load_scores():
    data = {}
    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, 'r') as f:
                data = json.load(f)
        except: pass
    return data

def load_level_data(path):
    """Returns: (grid_list, platform_object_list, level_title)"""
    if not os.path.exists(path): return None, [], "Unknown"

    try:
        with open(path, 'r') as f:
            content = f.read()

        parts = content.split("__METADATA__")
        lines = [l.rstrip("\n") for l in parts[0].strip().split('\n')]

        if not lines: return None, [], "Empty"

        w = max(len(l) for l in lines)
        grid = [list(l.ljust(w, ' ')) for l in lines]
        platforms = []
        title = os.path.basename(path) # Default to filename

        if len(parts) > 1:
            try:
                meta = json.loads(parts[1])
                plat_data = []

                if isinstance(meta, list):
                    plat_data = meta
                elif isinstance(meta, dict):
                    plat_data = meta.get('platforms', [])
                    # Extract title and clean quotes
                    if "title" in meta:
                        title = str(meta["title"]).replace('"', '')

                for p in plat_data:
                    new_plat = MovingPlatform(p)
                    platforms.append(new_plat)
                    # Clear grid under platform
                    for i in range(new_plat.w):
                        gx, gy = int(new_plat.x_origin) + i, int(new_plat.y_origin)
                        if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]):
                            grid[gy][gx] = ' '
            except: pass

        grid_strs = ["".join(row) for row in grid]
        return grid_strs, platforms, title

    except: return None, [], "Error"

def load_random_level_data():
    ensure_dirs()
    candidates = []

    if os.path.exists(LEVELS_DIR):
        for f in os.listdir(LEVELS_DIR):
            if f.endswith(".txt"): candidates.append(os.path.join(LEVELS_DIR, f))

    if os.path.exists(CAMPAIGN_DIR):
        for f in os.listdir(CAMPAIGN_DIR):
            if f.endswith(".txt"): candidates.append(os.path.join(CAMPAIGN_DIR, f))

    if candidates:
        chosen = random.choice(candidates)
        return load_level_data(chosen)

    # Fallback
    return ([
        "########################################",
        "#                                      #",
        "#            TerminalFormer2           #",
        "#                                      #",
        "########################################"
    ] * 5, [], "Menu")

# --- INPUT HELPER ---
def get_string_input(stdscr, prompt):
    curses.echo()
    curses.curs_set(1)
    stdscr.nodelay(False)

    stdscr.clear()
    h, w = stdscr.getmaxyx()
    msg = f" {prompt} "
    stdscr.addstr(h//2 - 2, (w-len(msg))//2, msg, curses.A_BOLD)
    stdscr.move(h//2, (w//2) - 10)
    stdscr.refresh()

    inp = stdscr.getstr(h//2, (w//2) - 10, 20).decode('utf-8')

    curses.noecho()
    curses.curs_set(0)
    stdscr.nodelay(True)
    return inp.strip()

# --- UNIFIED DRAWING ENGINE ---
def draw_background(stdscr, level_data, cam_x, cam_y):
    if not level_data: return
    # Unpack safely (handle potential 2-tuple or 3-tuple)
    grid = level_data[0]
    platforms = level_data[1]
    
    if not grid: return

    h, w = stdscr.getmaxyx()

    stdscr.attron(curses.A_DIM)

    grid_h = len(grid)
    grid_w = len(grid[0]) if grid_h > 0 else 0

    # 1. Draw Static Grid
    for y in range(h):
        map_y = int(y + cam_y) % grid_h
        row_str = grid[map_y]
        start_x = int(cam_x) % grid_w

        drawn_len = 0
        line_buffer = ""
        current_x = start_x

        while drawn_len < w:
            chunk_size = min(grid_w - current_x, w - drawn_len)
            line_buffer += row_str[current_x : current_x + chunk_size]
            drawn_len += chunk_size
            current_x = 0

        try: stdscr.addstr(y, 0, line_buffer)
        except: pass

    # 2. Draw Moving Platforms (Robust Tiling)
    base_offset_x = -int(cam_x % grid_w)
    base_offset_y = -int(cam_y % grid_h)

    for p in platforms:
        curr_y = base_offset_y
        while curr_y < h:
            curr_x = base_offset_x
            while curr_x < w:
                scr_x = int(curr_x + p.x)
                scr_y = int(curr_y + p.y)

                if -p.w < scr_x < w and 0 <= scr_y < h:
                    draw_str = '█' * p.w
                    start_char = 0
                    if scr_x < 0:
                        start_char = -scr_x
                        scr_x = 0

                    final_len = len(draw_str) - start_char
                    if scr_x + final_len >= w:
                        final_len = w - scr_x

                    if final_len > 0:
                        try: stdscr.addstr(scr_y, scr_x, draw_str[start_char:start_char+final_len])
                        except: pass
                curr_x += grid_w
            curr_y += grid_h

    stdscr.attroff(curses.A_DIM)

def draw_menu_frame(stdscr, level_data, cam_x, cam_y, title, items, selected_idx):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    draw_background(stdscr, level_data, cam_x, cam_y)

    menu_height = len(items) * 2
    start_y = (h - menu_height) // 2

    stdscr.attron(curses.A_BOLD | curses.A_UNDERLINE)
    stdscr.addstr(start_y - 4, (w - len(title))//2, title)
    stdscr.attroff(curses.A_BOLD | curses.A_UNDERLINE)

    for i, label in enumerate(items):
        y = start_y + (i * 2)
        if i == selected_idx:
            text = f">  {label}  <"
            stdscr.attron(curses.A_BOLD)
            stdscr.addstr(y, (w - len(text))//2, text)
            stdscr.attroff(curses.A_BOLD)
        else:
            text = f"   {label}   "
            stdscr.addstr(y, (w - len(text))//2, text)

    hint = "UP/DOWN: Navigate  |  ENTER: Select  |  Q: Back/Quit"
    stdscr.addstr(h - 2, (w - len(hint))//2, hint, curses.A_DIM)
    stdscr.refresh()

def show_scoreboard(stdscr, bg_data, cam_x, cam_y):
    stdscr.nodelay(False)
    scores = load_scores()
    stdscr.erase()
    draw_background(stdscr, bg_data, cam_x, cam_y)

    h, w = stdscr.getmaxyx()
    title = "--- HIGH SCORES ---"
    stdscr.addstr(3, (w-len(title))//2, title, curses.A_BOLD | curses.A_UNDERLINE)

    row = 6
    col = max(2, (w // 2) - 15)

    stdscr.addstr(row, col, "CAMPAIGN:", curses.A_BOLD); row += 1
    if "campaign" in scores:
        for i, t in enumerate(scores["campaign"]):
            stdscr.addstr(row, col+2, f"{i+1}. {t:.2f}s")
            row += 1
    else:
        stdscr.addstr(row, col+2, "No runs yet."); row += 1

    row += 2
    stdscr.addstr(row, col, "CUSTOM LEVEL BESTS:", curses.A_BOLD); row += 1
    all_keys = sorted([k for k in scores.keys() if k != "campaign"])

    for lvl in all_keys:
        if row >= h - 4: break
        best = scores[lvl][0] if scores[lvl] else 0.0
        stdscr.addstr(row, col+2, f"{lvl}: {best:.2f}s")
        row += 1

    msg = "Press ANY KEY to return"
    stdscr.addstr(h-3, (w-len(msg))//2, msg, curses.A_BOLD)
    stdscr.refresh()
    stdscr.getch()
    stdscr.nodelay(True)

# --- SUB MENUS ---
def run_menu_loop(stdscr, default_bg_data, title, items):
    idx = 0
    cam_x, cam_y = 0.0, 0.0
    stdscr.nodelay(True)
    stdscr.timeout(30)

    while True:
        cam_x += BG_SCROLL_SPEED_X
        cam_y += BG_SCROLL_SPEED_Y

        # Determine active level data
        current_item = items[idx]
        active_data = default_bg_data

        if len(current_item) > 2 and current_item[2] is not None:
            active_data = current_item[2]

        # --- UPDATE ALL PHYSICS ---
        if default_bg_data:
             # default_bg_data is (grid, platforms, title)
             for p in default_bg_data[1]: p.update(0.05)

        for item in items:
            if len(item) > 2 and item[2]:
                # item[2] is (grid, platforms, title)
                platforms = item[2][1]
                for p in platforms:
                    p.update(0.05)

        labels = [item[0] for item in items]
        draw_menu_frame(stdscr, active_data, cam_x, cam_y, title, labels, idx)

        key = stdscr.getch()
        if key == -1: continue

        if key == curses.KEY_UP:
            idx = (idx - 1) % len(items)
        elif key == curses.KEY_DOWN:
            idx = (idx + 1) % len(items)
        elif key in (10, 13):
            action = items[idx][1]
            result = action()
            if result == "BACK": return
            if result == "RELOAD": return "RELOAD"
            stdscr.clear()
            curses.curs_set(0)
            stdscr.nodelay(True)
            stdscr.timeout(30)
        elif key in (ord('q'), ord('Q')):
            return

def play_game(path=None):
    try:
        curses.endwin()
        args = [sys.executable, "game.py"]
        if path: args.append(path)
        subprocess.run(args)
    except: pass

def open_editor_subprocess(path):
    try:
        curses.endwin()
        subprocess.run([sys.executable, "editor.py", path])
    except: pass

# --- SPECIFIC MENU LOGIC ---
def menu_level_selector(stdscr, default_bg_data):
    levels = get_custom_levels()
    if not levels: return

    items = []
    for lvl in levels:
        full_path = os.path.join(LEVELS_DIR, lvl)
        lvl_data = load_level_data(full_path)
        # Display: Title (filename.txt)
        lvl_title = lvl_data[2]
        display_name = f"{lvl_title} ({lvl})"
        
        items.append( (display_name, lambda p=full_path: play_game(p), lvl_data) )

    items.append( ("BACK", lambda: "BACK", None) )
    run_menu_loop(stdscr, default_bg_data, "SELECT CUSTOM LEVEL", items)

def menu_editor(stdscr, default_bg_data):
    while True:
        levels = get_custom_levels()
        items = []

        def do_new():
            name = get_string_input(stdscr, "New Level Name:")
            if name:
                if not name.endswith(".txt"): name += ".txt"
                open_editor_subprocess(name)
            return "RELOAD"

        items.append( ("CREATE NEW LEVEL", do_new, None) )

        for lvl in levels:
            full_path = os.path.join(LEVELS_DIR, lvl)
            lvl_data = load_level_data(full_path)
            # Display: EDIT: Title (filename.txt)
            lvl_title = lvl_data[2]
            display_name = f"EDIT: {lvl_title} ({lvl})"
            
            # Now passing lvl_data to the 3rd tuple element allows background preview!
            items.append( (display_name, lambda l=lvl: open_editor_subprocess(l), lvl_data) )

        items.append( ("BACK", lambda: "BACK", None) )

        res = run_menu_loop(stdscr, default_bg_data, "LEVEL EDITOR", items)
        if res != "RELOAD": break

# --- MAIN ENTRY ---
def main(stdscr):
    curses.curs_set(0)
    ensure_dirs()

    bg_data = load_random_level_data()
    cam_x, cam_y = 0.0, 0.0

    main_options = [
        ("PLAY CAMPAIGN", lambda: play_game(), None),
        ("CUSTOM LEVELS", lambda: menu_level_selector(stdscr, bg_data), None),
        ("LEVEL EDITOR",  lambda: menu_editor(stdscr, bg_data), None),
        ("HIGH SCORES",   lambda: show_scoreboard(stdscr, bg_data, cam_x, cam_y), None),
        ("QUIT GAME",     sys.exit, None)
    ]

    idx = 0
    stdscr.nodelay(True)
    stdscr.timeout(30)

    while True:
        cam_x += BG_SCROLL_SPEED_X
        cam_y += BG_SCROLL_SPEED_Y

        active_data = bg_data
        if len(main_options[idx]) > 2 and main_options[idx][2]:
            active_data = main_options[idx][2]

        if bg_data:
            # bg_data[1] is platforms list
            for p in bg_data[1]: p.update(0.05)

        labels = [opt[0] for opt in main_options]
        draw_menu_frame(stdscr, active_data, cam_x, cam_y, "TerminalFormer2", labels, idx)

        key = stdscr.getch()
        if key == -1: continue

        if key == curses.KEY_UP:
            idx = (idx - 1) % len(main_options)
        elif key == curses.KEY_DOWN:
            idx = (idx + 1) % len(main_options)
        elif key in (10, 13):
            func = main_options[idx][1]
            func()

            stdscr.clear()
            curses.curs_set(0)
            stdscr.nodelay(True)
            stdscr.timeout(30)

            bg_data = load_random_level_data()

        elif key in (ord('q'), ord('Q')):
            sys.exit(0)

if __name__ == "__main__":
    curses.wrapper(main)
