#!/usr/bin/env python3
import curses, os, sys, json, subprocess, random, time

LEVELS_DIR = "levels"
SCORES_FILE = "scores.json"

# --- CONFIGURATION ---
BG_SCROLL_SPEED_X = 1
BG_SCROLL_SPEED_Y = 0

def ensure_levels_dir():
    if not os.path.exists(LEVELS_DIR):
        os.makedirs(LEVELS_DIR)

def get_levels():
    ensure_levels_dir()
    return sorted([f for f in os.listdir(LEVELS_DIR) if f.endswith(".txt")])

def load_scores():
    data = {}
    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, 'r') as f:
                data = json.load(f)
        except: pass
    return data

def load_level_grid(filename):
    """Loads a specific level grid for preview."""
    path = os.path.join(LEVELS_DIR, filename)
    if not os.path.exists(path): return None
    try:
        with open(path, 'r') as f:
            lines = [l.rstrip("\n") for l in f.readlines()]
        if not lines: return None
        w = max(len(l) for l in lines)
        return [l.ljust(w, ' ') for l in lines]
    except: return None

def load_random_level_grid():
    """Loads a random level for the background."""
    levels = get_levels()
    if levels:
        chosen = random.choice(levels)
        grid = load_level_grid(chosen)
        if grid: return grid

    # Fallback grid
    return [
        "########################################",
        "#                                      #",
        "#            TerminalFormer2           #",
        "#                                      #",
        "########################################"
    ] * 5

# --- INPUT HELPER ---
def get_string_input(stdscr, prompt):
    """Blocking text input for new filenames."""
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
def draw_background(stdscr, grid, cam_x, cam_y):
    """Draws the level grid dimmed as a background."""
    if not grid: return
    h, w = stdscr.getmaxyx()

    # PURE MONOCHROME: Use A_DIM to make it dark grey
    stdscr.attron(curses.A_DIM)

    grid_h = len(grid)
    grid_w = len(grid[0]) if grid_h > 0 else 0

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

    stdscr.attroff(curses.A_DIM)

def draw_menu_frame(stdscr, bg_grid, cam_x, cam_y, title, items, selected_idx):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    # 1. Background
    draw_background(stdscr, bg_grid, cam_x, cam_y)

    # 2. Calculate Layout
    menu_height = len(items) * 2
    start_y = (h - menu_height) // 2

    # 3. Title
    stdscr.attron(curses.A_BOLD | curses.A_UNDERLINE)
    stdscr.addstr(start_y - 4, (w - len(title))//2, title)
    stdscr.attroff(curses.A_BOLD | curses.A_UNDERLINE)

    # 4. Items
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

    # 5. Footer
    hint = "UP/DOWN: Navigate  |  ENTER: Select  |  Q: Back/Quit"
    stdscr.addstr(h - 2, (w - len(hint))//2, hint, curses.A_DIM)

    stdscr.refresh()

def show_scoreboard(stdscr, bg_grid, cam_x, cam_y):
    stdscr.nodelay(False)
    scores = load_scores()
    stdscr.erase()
    draw_background(stdscr, bg_grid, cam_x, cam_y)

    h, w = stdscr.getmaxyx()
    title = "--- HIGH SCORES ---"
    stdscr.addstr(3, (w-len(title))//2, title, curses.A_BOLD | curses.A_UNDERLINE)

    row = 6
    col = max(2, (w // 2) - 15)

    # Campaign
    stdscr.addstr(row, col, "CAMPAIGN:", curses.A_BOLD); row += 1
    if "campaign" in scores:
        for i, t in enumerate(scores["campaign"]):
            stdscr.addstr(row, col+2, f"{i+1}. {t:.2f}s")
            row += 1
    else:
        stdscr.addstr(row, col+2, "No runs yet."); row += 1

    row += 2

    # Levels
    stdscr.addstr(row, col, "LEVEL BESTS:", curses.A_BOLD); row += 1
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

def run_menu_loop(stdscr, default_bg, title, items):
    """
    Items Structure:
    [ (Label, Action_Callback, Optional_Preview_Grid), ... ]
    """
    idx = 0
    cam_x, cam_y = 0.0, 0.0

    stdscr.nodelay(True)
    stdscr.timeout(30)

    while True:
        # Animate BG
        cam_x += BG_SCROLL_SPEED_X
        cam_y += BG_SCROLL_SPEED_Y

        # Determine which BG to show
        # If the currently selected item has a specific grid (index 2), use it.
        # Otherwise, use default_bg.
        current_item = items[idx]
        active_bg = default_bg

        if len(current_item) > 2 and current_item[2] is not None:
            active_bg = current_item[2]

        # Extract labels
        labels = [item[0] for item in items]
        draw_menu_frame(stdscr, active_bg, cam_x, cam_y, title, labels, idx)

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

            # Reset state
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

def menu_level_selector(stdscr, default_bg):
    levels = get_levels()
    if not levels: return

    items = []
    for lvl in levels:
        full_path = os.path.join(LEVELS_DIR, lvl)
        # Load grid for preview
        grid = load_level_grid(lvl)
        # (Label, Action, PreviewGrid)
        items.append( (lvl, lambda p=full_path: play_game(p), grid) )

    items.append( ("BACK", lambda: "BACK", None) )
    run_menu_loop(stdscr, default_bg, "SELECT LEVEL", items)

def menu_editor(stdscr, default_bg):
    while True:
        levels = get_levels()
        items = []

        def do_new():
            name = get_string_input(stdscr, "New Level Name:")
            if name:
                if not name.endswith(".txt"): name += ".txt"
                open_editor_subprocess(name)
            return "RELOAD"

        items.append( ("CREATE NEW LEVEL", do_new, None) )

        for lvl in levels:
            grid = load_level_grid(lvl)
            items.append( (f"EDIT: {lvl}", lambda l=lvl: open_editor_subprocess(l), grid) )

        items.append( ("BACK", lambda: "BACK", None) )

        res = run_menu_loop(stdscr, default_bg, "LEVEL EDITOR", items)
        if res != "RELOAD": break

# --- MAIN ENTRY ---

def main(stdscr):
    curses.curs_set(0)

    # Setup Background
    bg_grid = load_random_level_grid()
    cam_x, cam_y = 0.0, 0.0

    main_options = [
        ("PLAY CAMPAIGN", lambda: play_game(), None),
        ("SELECT LEVEL",  lambda: menu_level_selector(stdscr, bg_grid), None),
        ("LEVEL EDITOR",  lambda: menu_editor(stdscr, bg_grid), None),
        ("HIGH SCORES",   lambda: show_scoreboard(stdscr, bg_grid, cam_x, cam_y), None),
        ("QUIT GAME",     sys.exit, None)
    ]

    idx = 0
    stdscr.nodelay(True)
    stdscr.timeout(30)

    while True:
        cam_x += BG_SCROLL_SPEED_X
        cam_y += BG_SCROLL_SPEED_Y

        # Determine BG (Main menu usually just keeps the random one,
        # unless we wanted to preview level 1 on "Play Campaign")
        active_bg = bg_grid
        if len(main_options[idx]) > 2 and main_options[idx][2]:
            active_bg = main_options[idx][2]

        labels = [opt[0] for opt in main_options]
        draw_menu_frame(stdscr, active_bg, cam_x, cam_y, "TerminalFormer2", labels, idx)

        key = stdscr.getch()

        if key == -1: continue

        if key == curses.KEY_UP:
            idx = (idx - 1) % len(main_options)
        elif key == curses.KEY_DOWN:
            idx = (idx + 1) % len(main_options)
        elif key in (10, 13):
            func = main_options[idx][1]
            func()

            # Restore state
            stdscr.clear()
            curses.curs_set(0)
            stdscr.nodelay(True)
            stdscr.timeout(30)

        elif key in (ord('q'), ord('Q')):
            sys.exit(0)

if __name__ == "__main__":
    curses.wrapper(main)
