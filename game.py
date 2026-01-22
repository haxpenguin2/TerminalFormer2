#!/usr/bin/env python3
import curses, time, os, math, sys, threading, json
from collections import deque

# --- CONFIGURATION ---
GRAVITY = 100
JUMP_V = -30
MOVE_SPEED = 24.0
FPS = 60.0
DT = 1.0 / FPS
MAX_SUBSTEP = 0.15

# Folder Configuration
LEVELS_DIR = "levels"           # For custom levels
CAMPAIGN_DIR = "campaignlevels" # For main story levels
SCORES_FILE = "scores.json"

# Visuals
TILE_SOLID = '█'
TILE_SPIKE = '▲'
TILE_SPIKE_DOWN = '▼'
TILE_CHECKPOINT = 'C'
TILE_SPAWN = 'S'
TILE_GOAL = 'G'
PLAYER_CHAR = '#'

# Physics
HALF_W = 0.4
HALF_H = 0.5

# --- SCORE MANAGER ---
def save_score(category, new_time):
    """Saves the score to scores.json, keeping top 5 fastest."""
    data = {}
    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, 'r') as f:
                data = json.load(f)
        except: pass

    if category not in data:
        data[category] = []

    data[category].append(new_time)
    data[category].sort() # Sort ascending
    data[category] = data[category][:5]

    with open(SCORES_FILE, 'w') as f:
        json.dump(data, f)

# --- INPUT ENGINE ---
try:
    import evdev
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

class InputEngine:
    def __init__(self):
        self.keys = {k: False for k in ['LEFT', 'RIGHT', 'UP', 'DOWN', 'JUMP', 'RESET', 'QUIT', 'CONTINUE']}
        self.pressed = set()
        self.running = True
        self.using_evdev = False
        self.dev = None

        if HAS_EVDEV:
            try:
                devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
                for dev in devices:
                    if "keyboard" in dev.name.lower():
                        self.dev = dev
                        self.using_evdev = True
                        threading.Thread(target=self._run, daemon=True).start()
                        break
            except: pass

    def _run(self):
        for event in self.dev.read_loop():
            if not self.running: break
            if event.type == evdev.ecodes.EV_KEY:
                down = (event.value == 1 or event.value == 2)
                code = event.code
                k = None
                if code in [105, 30]: k = 'LEFT'
                elif code in [106, 32]: k = 'RIGHT'
                elif code in [103, 17, 57]: k = 'JUMP'
                elif code in [19]: k = 'RESET'
                elif code in [16]: k = 'QUIT'
                elif code in [28]: k = 'CONTINUE'

                if k:
                    if down and not self.keys[k]: self.pressed.add(k)
                    self.keys[k] = down

    def update(self, stdscr):
        if self.using_evdev: return
        stdscr.nodelay(True)

        ch = stdscr.getch()
        while ch != -1:
            k = None
            if ch in (curses.KEY_LEFT, ord('a')): k = 'LEFT'
            elif ch in (curses.KEY_RIGHT, ord('d')): k = 'RIGHT'
            elif ch in (curses.KEY_UP, ord('w'), ord(' ')): k = 'JUMP'
            elif ch in (ord('r'), ord('R')): k = 'RESET'
            elif ch in (ord('q'), ord('Q')): k = 'QUIT'
            elif ch == 10: k = 'CONTINUE'

            if k:
                self.keys[k] = True
                self.pressed.add(k)
            ch = stdscr.getch()

        for k in self.keys:
            if self.keys[k]: self.keys[k] = False

    def was_pressed(self, k): return k in self.pressed
    def is_down(self, k): return self.keys[k]
    def clear(self): self.pressed.clear()
    def stop(self): self.running = False

# --- PHYSICS ---
def load_level(path):
    if not os.path.exists(path): return None
    with open(path, "r") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]
    if not lines: return None
    w = max(len(l) for l in lines)
    grid = [list(l.ljust(w, ' ')) for l in lines]
    return grid

def is_solid(grid, x, y):
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        return grid[int(y)][int(x)] == TILE_SOLID
    return True

def check_rect(grid, cx, cy):
    min_x, max_x = cx - HALF_W, cx + HALF_W
    min_y, max_y = cy - HALF_H, cy + HALF_H
    for y in range(int(min_y), int(max_y)+1):
        for x in range(int(min_x), int(max_x)+1):
            if is_solid(grid, x, y): return True
    return False

# --- RENDERING ---
def draw_scene(stdscr, grid, px, py, cam_x, cam_y, fps, msg, elapsed_time, visible=True):
    h, w = stdscr.getmaxyx()
    stdscr.erase()

    grid_h = len(grid)
    grid_w = len(grid[0])

    offset_x = (w - grid_w) // 2 if grid_w < w else 0
    offset_y = (h - grid_h) // 2 if grid_h < h else 0
    start_x = cam_x if grid_w >= w else 0
    start_y = cam_y if grid_h >= h else 0

    # Draw Map
    for scr_y in range(h - 1):
        map_y = scr_y - offset_y + start_y
        if 0 <= map_y < grid_h:
            row_str = "".join(grid[map_y])
            if grid_w >= w:
                stdscr.addstr(scr_y, 0, row_str[start_x : start_x + w])
            else:
                try: stdscr.addstr(scr_y, offset_x, row_str)
                except: pass

    # Draw Player
    scr_px = int(px - start_x) + offset_x
    scr_py = int(py - start_y) + offset_y
    if visible and 0 <= scr_px < w and 0 <= scr_py < h-1:
        stdscr.addch(scr_py, scr_px, PLAYER_CHAR, curses.A_BOLD)

    # UI
    if msg: stdscr.addstr(0, 1, msg, curses.A_REVERSE | curses.A_BOLD)
    timer_str = f"TIME: {elapsed_time:.2f}s"
    try: stdscr.addstr(0, w - len(timer_str) - 2, timer_str, curses.A_BOLD)
    except: pass
    try: stdscr.addstr(h-1, 0, f"Pos: {int(px)},{int(py)} | FPS: {int(fps)}")
    except: pass

    stdscr.refresh()

# --- MAIN LOOP ---
def play_level(stdscr, level_file, inp, timer_offset=0.0):
    grid = load_level(level_file)
    if not grid: return "NO_FILE", 0.0

    px, py = 1.5, 1.5
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == TILE_SPAWN: px, py = x + 0.5, y + 0.5

    checkpoint = (px, py)
    vx, vy = 0.0, 0.0
    cam_x, cam_y = 0, 0
    fps_hist = deque(maxlen=30)

    start_time = time.time()
    current_level_time = 0.0
    msg = None
    msg_end = 0
    last_time = time.time()

    while True:
        inp.update(stdscr)

        # --- PAUSE MENU (Safe Quit) ---
        if inp.was_pressed('QUIT'):
            inp.clear()
            curses.flushinp()

            while True:
                draw_scene(stdscr, grid, px, py, int(cam_x), int(cam_y), 0, "PAUSED (Q:QUIT / SPACE:RESUME)", timer_offset + current_level_time)
                inp.update(stdscr)

                if inp.was_pressed('QUIT'):
                    curses.flushinp()
                    return "QUIT", 0.0

                if inp.was_pressed('JUMP') or inp.was_pressed('CONTINUE'):
                    last_time = time.time()
                    break
                time.sleep(0.05)
            inp.clear()

        now = time.time()
        dt = now - last_time
        last_time = now
        if dt > 0.1: dt = 0.1
        if dt < 0: dt = DT

        current_level_time = (now - start_time)
        total_time = timer_offset + current_level_time

        if inp.was_pressed('RESET'):
            px, py = checkpoint[0], checkpoint[1] - 0.1
            vx, vy = 0, 0

        # Physics
        vx = (inp.is_down('RIGHT') - inp.is_down('LEFT')) * MOVE_SPEED
        grounded = check_rect(grid, px, py + 0.05)
        if inp.was_pressed('JUMP') and grounded:
            vy = JUMP_V; grounded = False
        elif grounded: vy = 0.0
        else: vy += GRAVITY * dt

        inp.clear()

        dx = vx * dt
        steps = max(1, int(abs(dx)/MAX_SUBSTEP))
        for _ in range(steps):
            if not check_rect(grid, px + dx/steps, py): px += dx/steps
            else: vx = 0; break

        dy = vy * dt
        steps = max(1, int(abs(dy)/MAX_SUBSTEP))
        for _ in range(steps):
            new_y = py + dy/steps
            if not check_rect(grid, px, new_y): py = new_y
            else:
                if vy > 0: py = math.floor(new_y + HALF_H) - HALF_H - 0.001
                elif vy < 0: py = math.floor(new_y - HALF_H) + HALF_H + 1.001
                vy = 0; break

        cx, cy = int(px), int(py)
        tile = grid[cy][cx] if (0 <= cy < len(grid) and 0 <= cx < len(grid[0])) else ' '

        if tile in (TILE_SPIKE, TILE_SPIKE_DOWN):
            for _ in range(5):
                inp.update(stdscr)
                if inp.was_pressed('QUIT'):
                    curses.flushinp()
                    return "QUIT", 0.0
                draw_scene(stdscr, grid, px, py, int(cam_x), int(cam_y), 60, "DEAD!", total_time, False)
                time.sleep(0.05)
                draw_scene(stdscr, grid, px, py, int(cam_x), int(cam_y), 60, "DEAD!", total_time, True)
                time.sleep(0.05)
            px, py = checkpoint[0], checkpoint[1] - 0.1
            vx, vy = 0, 0

        elif tile == TILE_CHECKPOINT:
            if (cx+0.5, cy+0.5) != checkpoint:
                checkpoint = (cx+0.5, cy+0.5)
                msg = "CHECKPOINT SAVED"; msg_end = time.time() + 1.5

        elif tile == TILE_GOAL:
            return "NEXT_LEVEL", current_level_time

        h, w = stdscr.getmaxyx()
        cam_x += (int(px) - w//2 - cam_x) * 0.1
        cam_y += (int(py) - h//2 - cam_y) * 0.1
        cxi = max(0, min(int(cam_x), max(0, len(grid[0]) - w)))
        cyi = max(0, min(int(cam_y), max(0, len(grid) - h)))

        fps = 1.0/dt if dt > 0 else 60
        fps_hist.append(fps)
        if time.time() > msg_end: msg = None

        draw_scene(stdscr, grid, px, py, cxi, cyi, sum(fps_hist)/len(fps_hist), msg, total_time)
        time.sleep(0.005)

# --- ENTRY POINT ---
def main_wrapper(stdscr):
    curses.curs_set(0)
    inp = InputEngine()

    mode = "CAMPAIGN"
    start_lvl = 1
    specific_file = None

    if len(sys.argv) > 1:
        mode = "SINGLE"
        specific_file = sys.argv[1]

    total_campaign_time = 0.0
    current_lvl = start_lvl

    try:
        while True:
            if mode == "SINGLE":
                path = specific_file
                if not os.path.exists(path):
                    # Check in custom levels folder
                    if os.path.exists(os.path.join(LEVELS_DIR, path)):
                        path = os.path.join(LEVELS_DIR, path)
            else:
                # Use CAMPAIGN_DIR for story mode
                path = os.path.join(CAMPAIGN_DIR, f"level{current_lvl}.txt")

            res, elapsed = play_level(stdscr, path, inp, total_campaign_time)

            if res == "QUIT":
                curses.flushinp()
                return "MENU"

            if res == "NO_FILE":
                if mode == "CAMPAIGN" and current_lvl > 1:
                    save_score("campaign", total_campaign_time)
                    stdscr.clear()
                    msg = f"CAMPAIGN FINISHED! TIME: {total_campaign_time:.2f}s"
                    stdscr.addstr(curses.LINES//2, (curses.COLS - len(msg))//2, msg, curses.A_BOLD)
                    stdscr.refresh()
                    time.sleep(3)
                curses.flushinp()
                return "MENU"

            if res == "NEXT_LEVEL":
                stdscr.clear()
                msg = f"LEVEL COMPLETE! TIME: {elapsed:.2f}s"
                stdscr.addstr(curses.LINES//2 - 1, (curses.COLS - len(msg))//2, msg, curses.A_BOLD)
                stdscr.addstr(curses.LINES//2 + 1, (curses.COLS - 20)//2, "Press ENTER to continue")
                stdscr.refresh()
                curses.flushinp()

                while True:
                    inp.update(stdscr)
                    if inp.was_pressed('CONTINUE') or inp.was_pressed('JUMP'):
                        inp.clear()
                        break
                    time.sleep(0.05)

                if mode == "SINGLE":
                    fname = os.path.basename(specific_file)
                    save_score(fname, elapsed)
                    return "MENU"
                else:
                    total_campaign_time += elapsed
                    current_lvl += 1

    finally:
        inp.stop()

if __name__ == "__main__":
    # Ensure both folders exist
    if not os.path.exists(LEVELS_DIR): os.makedirs(LEVELS_DIR, exist_ok=True)
    if not os.path.exists(CAMPAIGN_DIR): os.makedirs(CAMPAIGN_DIR, exist_ok=True)

    res = curses.wrapper(main_wrapper)

    if res == "MENU":
        game_dir = os.path.dirname(os.path.abspath(__file__))
        menu_path = os.path.join(game_dir, "menu.py")
        if os.path.exists(menu_path):
            time.sleep(0.1)
            os.execl(sys.executable, sys.executable, menu_path)
