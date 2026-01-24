#!/usr/bin/env python3
import curses, time, os, math, sys, json
from collections import deque

# --- CONFIGURATION ---
GRAVITY = 90.0
JUMP_V = -28.0
MOVE_SPEED = 24.0
FPS = 60.0
DT = 1.0 / FPS
MAX_SUBSTEP = 0.02

# Folder Configuration
LEVELS_DIR = "levels"
CAMPAIGN_DIR = "campaignlevels"
SCORES_FILE = "scores.json"

# Visuals
TILE_SOLID = '█'
TILE_SPIKE = '▲'
TILE_SPIKE_DOWN = '▼'
TILE_CHECKPOINT = 'C'
TILE_SPAWN = 'S'
TILE_GOAL = 'G'
PLAYER_CHAR = '#'

# Physics Constants
HALF_W = 0.4
HALF_H = 0.5
PLATFORM_TOP_TOLERANCE = 0.001

# --- SCORE MANAGER ---
def save_score(category, new_time):
    data = {}
    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, 'r') as f:
                data = json.load(f)
        except: pass

    if category not in data:
        data[category] = []

    data[category].append(new_time)
    data[category].sort()
    data[category] = data[category][:5]

    with open(SCORES_FILE, 'w') as f:
        json.dump(data, f)

# --- INPUT ENGINE ---
try:
    import evdev_input
    HAS_EVDEV_WRAPPER = True
except ImportError:
    HAS_EVDEV_WRAPPER = False

class InputEngine:
    def __init__(self):
        self.keys = {k: False for k in ['LEFT', 'RIGHT', 'UP', 'DOWN', 'JUMP', 'RESET', 'QUIT', 'CONTINUE']}
        self.pressed = set()
        self.ev_handler = None

        if not HAS_EVDEV_WRAPPER:
            curses.endwin()
            print("[ERROR] MISSING evdev_input.py")
            sys.exit(1)

        try:
            self.ev_handler = evdev_input.EvdevInput()
            if not self.ev_handler.devices:
                curses.endwin()
                print("[ERROR] INPUT PERMISSION DENIED (Run with sudo?)")
                sys.exit(1)
        except Exception as e:
            curses.endwin()
            sys.exit(1)

    def update(self, stdscr):
        if self.ev_handler:
            events = self.ev_handler.poll(timeout=0.0)
            for token, value in events:
                k = None
                if token == 'LEFT': k = 'LEFT'
                elif token == 'RIGHT': k = 'RIGHT'
                elif token in ['UP', 'SPACE']: k = 'JUMP'
                elif token == 'R': k = 'RESET'
                elif token == 'Q': k = 'QUIT'
                elif token in ['CONTINUE', 'SPACE']: k = 'CONTINUE'

                if k:
                    if value == 1:
                        if not self.keys[k]:
                            self.pressed.add(k)
                        self.keys[k] = True
                    elif value == 0:
                        self.keys[k] = False

    def was_pressed(self, k): return k in self.pressed
    def is_down(self, k): return self.keys[k]
    def clear(self): self.pressed.clear()
    def stop(self):
        if self.ev_handler: self.ev_handler.close()

# --- MOVING PLATFORM CLASS ---
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
        self.last_x = self.x
        self.last_y = self.y
        self.timer = 0.0

    def update(self, dt):
        self.last_x = self.x
        self.last_y = self.y
        self.timer += dt * self.speed

        offset = 0
        if self.easing == 'SINE':
            offset = math.sin(self.timer)
        else:
            t = (self.timer / math.pi) % 2
            offset = (t - 1) if t > 1 else (1 - t)

        self.x = self.x_origin + (offset * (self.limit_x / 2))
        self.y = self.y_origin + (offset * (self.limit_y / 2))

    def get_rect(self):
        return (self.x, self.y, self.x + self.w, self.y + 1)

# --- PHYSICS ---
def load_level(path):
    if not os.path.exists(path): return None, [], "UNKNOWN"

    with open(path, "r") as f:
        content = f.read()

    parts = content.split("__METADATA__")
    lines = [l.rstrip("\n") for l in parts[0].strip().split('\n')]

    w = max(len(l) for l in lines) if lines else 0
    grid = [list(l.ljust(w, ' ')) for l in lines]

    platforms = []
    # Default title is the filename without extension
    level_title = os.path.splitext(os.path.basename(path))[0]

    if len(parts) > 1:
        try:
            data = json.loads(parts[1])
            plat_data = []

            if isinstance(data, dict):
                # Get title and strip any existing quotes to avoid double quoting later
                raw_title = data.get("title", level_title)
                level_title = str(raw_title).replace('"', '')

                plat_data = data.get("platforms", [])
            elif isinstance(data, list):
                plat_data = data

            for p in plat_data:
                platforms.append(MovingPlatform(p))
                for i in range(p['w']):
                    gx, gy = int(p['x']) + i, int(p['y'])
                    if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]):
                        grid[gy][gx] = ' '
        except: pass

    return grid, platforms, level_title

def is_solid(grid, x, y):
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        return grid[int(y)][int(x)] == TILE_SOLID
    return True

def check_rect_grid(grid, left, top, right, bottom):
    min_tx = int(math.floor(left))
    max_tx = int(math.floor(right))
    min_ty = int(math.floor(top))
    max_ty = int(math.floor(bottom))

    for y in range(min_ty, max_ty + 1):
        for x in range(min_tx, max_tx + 1):
            if is_solid(grid, x, y):
                return True
    return False

def check_platform_collision(platforms, left, top, right, bottom):
    for p in platforms:
        pl, pt, pr, pb = p.get_rect()
        if (left < pr and right > pl and top < pb and bottom > pt):
            return p
    return None

# --- RENDERING ---
def draw_scene(stdscr, grid, platforms, px, py, cam_x, cam_y, fps, msg, elapsed_time, lvl_num, lvl_title, visible=True):
    h, w = stdscr.getmaxyx()
    stdscr.erase()

    grid_h = len(grid)
    grid_w = len(grid[0]) if grid_h > 0 else 0

    max_cam_x = max(0, grid_w - w)
    max_cam_y = max(0, grid_h - h)

    target_x = int(max(0, min(cam_x, max_cam_x)))
    target_y = int(max(0, min(cam_y, max_cam_y)))

    offset_x = (w - grid_w) // 2 if grid_w < w else 0
    offset_y = (h - grid_h) // 2 if grid_h < h else 0

    start_x = target_x if grid_w >= w else 0
    start_y = target_y if grid_h >= h else 0

    # Draw Map
    for scr_y in range(h - 1):
        map_y = scr_y - offset_y + start_y
        if 0 <= map_y < grid_h:
            row_str = "".join(grid[map_y])
            if grid_w >= w:
                slice_end = min(start_x + w, len(row_str))
                stdscr.addstr(scr_y, 0, row_str[start_x : slice_end])
            else:
                try: stdscr.addstr(scr_y, offset_x, row_str)
                except: pass

    # Draw Platforms
    for p in platforms:
        scr_px = int(p.x - start_x) + offset_x
        scr_py = int(p.y - start_y) + offset_y
        if 0 <= scr_py < h-1:
            draw_len = p.w
            if scr_px < 0:
                draw_len += scr_px
                scr_px = 0
            if scr_px + draw_len >= w:
                draw_len = w - scr_px
            if draw_len > 0:
                try: stdscr.addstr(scr_py, scr_px, TILE_SOLID * int(draw_len), curses.A_BOLD)
                except: pass

    # Draw Player
    scr_px = int(px - start_x) + offset_x
    scr_py = int(py - start_y) + offset_y
    if visible and 0 <= scr_px < w and 0 <= scr_py < h-1:
        stdscr.addch(scr_py, scr_px, PLAYER_CHAR, curses.A_BOLD)

    # UI
    # LEVEL NAME DISPLAY (Top Left)
    # Format: LEVEL 1 "Introduction"
    if not msg:
        title_str = f"LEVEL {lvl_num} \"{lvl_title}\""
        try: stdscr.addstr(0, 0, title_str, curses.A_BOLD)
        except: pass

    # Message Overlay
    if msg: stdscr.addstr(0, 1, msg, curses.A_REVERSE | curses.A_BOLD)

    # Timer (Top Right)
    timer_str = f"TIME: {elapsed_time:.2f}s"
    try: stdscr.addstr(0, w - len(timer_str) - 2, timer_str, curses.A_BOLD)
    except: pass

    # Debug info (Bottom Left)
    try: stdscr.addstr(h-1, 0, f"Pos: {int(px)},{int(py)} | FPS: {int(fps)}")
    except: pass

    stdscr.refresh()

# --- MAIN LOOP ---
def play_level(stdscr, level_file, inp, level_num, timer_offset=0.0):
    grid, platforms, level_title = load_level(level_file)
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

    active_platform = None
    platform_offset_x = 0.0

    while True:
        inp.update(stdscr)

        if inp.was_pressed('QUIT'):
            inp.clear()
            curses.flushinp()
            while True:
                draw_scene(stdscr, grid, platforms, px, py, int(cam_x), int(cam_y), 0, "PAUSED (Q:QUIT / SPACE:RESUME)", timer_offset + current_level_time, level_num, level_title)
                inp.update(stdscr)
                if inp.was_pressed('QUIT'): return "QUIT", 0.0
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

        # 1. Update Platforms
        for p in platforms: p.update(dt)

        if inp.was_pressed('RESET'):
            px, py = checkpoint[0], checkpoint[1] - 0.1
            vx, vy = 0, 0
            active_platform = None

        input_dir = (inp.is_down('RIGHT') - inp.is_down('LEFT'))

        # --- PHYSICS ---
        if active_platform:
            # === ATTACHED MODE ===
            if inp.was_pressed('JUMP'):
                vy = JUMP_V
                px = active_platform.x + platform_offset_x
                active_platform = None
            else:
                # 1. Move Offset (Input)
                local_vx = input_dir * MOVE_SPEED
                remaining_dt = dt
                current_offset = platform_offset_x

                while remaining_dt > 0:
                    step = min(remaining_dt, MAX_SUBSTEP)
                    remaining_dt -= step

                    next_offset = current_offset + local_vx * step
                    world_x_next = active_platform.x + next_offset
                    world_y_fixed = active_platform.y - HALF_H - PLATFORM_TOP_TOLERANCE

                    if check_rect_grid(grid, world_x_next - HALF_W, world_y_fixed - HALF_H + 0.1, world_x_next + HALF_W, world_y_fixed + HALF_H - 0.1):
                        local_vx = 0
                    else:
                        current_offset = next_offset

                platform_offset_x = current_offset

                # 2. Sync Physics Position
                px = active_platform.x + platform_offset_x
                py = active_platform.y - HALF_H - PLATFORM_TOP_TOLERANCE
                vy = 0

                # 3. Bounds Check
                if px < active_platform.x - 0.1 or px > active_platform.x + active_platform.w + 0.1:
                    active_platform = None

                # 4. Ceiling Crush
                if check_rect_grid(grid, px - HALF_W + 0.1, py - HALF_H + 0.1, px + HALF_W - 0.1, py + HALF_H - 0.1):
                    pass

        else:
            # === DETACHED MODE ===
            is_grounded_grid = check_rect_grid(grid, px - HALF_W, py + HALF_H, px + HALF_W, py + HALF_H + 0.05)

            if inp.was_pressed('JUMP') and is_grounded_grid:
                 vy = JUMP_V
            else:
                 vy += GRAVITY * dt

            vx = input_dir * MOVE_SPEED

            remaining_dt = dt
            while remaining_dt > 0:
                step = min(remaining_dt, MAX_SUBSTEP)
                remaining_dt -= step
                next_px = px + vx * step

                if check_rect_grid(grid, next_px - HALF_W, py - HALF_H + 0.01, next_px + HALF_W, py + HALF_H - 0.01):
                    vx = 0
                else:
                    p_hit = check_platform_collision(platforms, next_px - HALF_W, py - HALF_H + 0.1, next_px + HALF_W, py + HALF_H - 0.1)
                    if p_hit:
                        vx = 0
                    else:
                        px = next_px

            remaining_dt = dt
            while remaining_dt > 0:
                step = min(remaining_dt, MAX_SUBSTEP)
                remaining_dt -= step
                next_py = py + vy * step

                # 1. Grid Collision
                if check_rect_grid(grid, px - HALF_W, next_py - HALF_H, px + HALF_W, next_py + HALF_H):
                    if vy > 0:
                        py = math.floor(next_py + HALF_H) - HALF_H - 0.001
                    elif vy < 0:
                        py = math.floor(next_py - HALF_H) + HALF_H + 1.001
                    vy = 0
                else:
                    # 2. Platform Collision
                    hit_platform = False

                    if vy >= 0: # Moving DOWN (Landing)
                        p_hit = check_platform_collision(platforms, px - HALF_W, next_py - HALF_H, px + HALF_W, next_py + HALF_H)
                        if p_hit:
                            # Only land if we were previously ABOVE the platform centerline
                            if (py + HALF_H) <= (p_hit.y + 1.5):
                                active_platform = p_hit
                                platform_offset_x = px - active_platform.x
                                py = active_platform.y - HALF_H - PLATFORM_TOP_TOLERANCE
                                vy = 0
                                hit_platform = True

                    elif vy < 0: # Moving UP (Ceiling Bonk)
                        p_hit = check_platform_collision(platforms, px - HALF_W, next_py - HALF_H, px + HALF_W, next_py + HALF_H)
                        if p_hit:
                            py = p_hit.y + 1.0 + HALF_H + 0.001
                            vy = 0
                            hit_platform = True

                    if not hit_platform:
                        py = next_py

        # --- DEATH CHECK ---
        cx, cy = int(px), int(py)
        is_crushed = check_rect_grid(grid, px - HALF_W + 0.2, py - HALF_H + 0.2, px + HALF_W - 0.2, py + HALF_H - 0.2)
        tile = grid[cy][cx] if (0 <= cy < len(grid) and 0 <= cx < len(grid[0])) else ' '

        if is_crushed or tile in (TILE_SPIKE, TILE_SPIKE_DOWN):
            for _ in range(5):
                draw_scene(stdscr, grid, platforms, px, py, int(cam_x), int(cam_y), 60, "DEAD!", current_level_time, level_num, level_title, False)
                time.sleep(0.05)
                draw_scene(stdscr, grid, platforms, px, py, int(cam_x), int(cam_y), 60, "DEAD!", current_level_time, level_num, level_title, True)
                time.sleep(0.05)
            px, py = checkpoint[0], checkpoint[1] - 0.1
            vx, vy = 0, 0
            active_platform = None

        elif tile == TILE_CHECKPOINT:
            if (cx+0.5, cy+0.5) != checkpoint:
                checkpoint = (cx+0.5, cy+0.5)
                msg = "CHECKPOINT SAVED"; msg_end = time.time() + 1.5

        elif tile == TILE_GOAL:
            return "NEXT_LEVEL", current_level_time

        # --- CAMERA ---
        h, w = stdscr.getmaxyx()
        cam_x += (int(px) - w//2 - cam_x) * 0.1
        cam_y += (int(py) - h//2 - cam_y) * 0.1

        fps = 1.0/dt if dt > 0 else 60
        fps_hist.append(fps)
        if time.time() > msg_end: msg = None

        # --- VISUAL CORRECTION (THE LAG FIX) ---
        render_px, render_py = px, py
        if active_platform:
            # Force render Y to be exactly one tile above the Platform's render Y
            render_py = float(int(active_platform.y)) - 0.5

        inp.clear()

        draw_scene(stdscr, grid, platforms, render_px, render_py, int(cam_x), int(cam_y), sum(fps_hist)/len(fps_hist), msg, timer_offset + current_level_time, level_num, level_title)
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
            try:
                if mode == "SINGLE":
                    path = specific_file
                    if not os.path.exists(path):
                        if os.path.exists(os.path.join(LEVELS_DIR, path)):
                            path = os.path.join(LEVELS_DIR, path)
                else:
                    path = os.path.join(CAMPAIGN_DIR, f"level{current_lvl}.txt")

                res, elapsed = play_level(stdscr, path, inp, current_lvl, total_campaign_time)

                if res == "QUIT":
                    return "MENU"

                if res == "NO_FILE":
                    if mode == "CAMPAIGN" and current_lvl > 1:
                        save_score("campaign", total_campaign_time)
                        stdscr.clear()
                        msg = f"CAMPAIGN FINISHED! TIME: {total_campaign_time:.2f}s"
                        stdscr.addstr(curses.LINES//2, (curses.COLS - len(msg))//2, msg, curses.A_BOLD)
                        stdscr.refresh()
                        time.sleep(3)
                    return "MENU"

                if res == "NEXT_LEVEL":
                    stdscr.clear()
                    msg = f"LEVEL COMPLETE! TIME: {elapsed:.2f}s"
                    stdscr.addstr(curses.LINES//2 - 1, (curses.COLS - len(msg))//2, msg, curses.A_BOLD)
                    stdscr.refresh()
                    curses.flushinp()
                    time.sleep(0.5)
                    while True:
                        inp.update(stdscr)
                        if inp.was_pressed('CONTINUE') or inp.was_pressed('JUMP'):
                            inp.clear(); break
                        time.sleep(0.05)

                    if mode == "SINGLE":
                        fname = os.path.basename(specific_file)
                        save_score(fname, elapsed)
                        return "MENU"
                    else:
                        total_campaign_time += elapsed
                        current_lvl += 1

            except KeyboardInterrupt:
                return "MENU"

    finally:
        inp.stop()

if __name__ == "__main__":
    if not os.path.exists(LEVELS_DIR): os.makedirs(LEVELS_DIR, exist_ok=True)
    if not os.path.exists(CAMPAIGN_DIR): os.makedirs(CAMPAIGN_DIR, exist_ok=True)

    try:
        res = curses.wrapper(main_wrapper)
    except KeyboardInterrupt:
        res = "MENU"

    if res == "MENU":
        game_dir = os.path.dirname(os.path.abspath(__file__))
        menu_path = os.path.join(game_dir, "menu.py")
        if os.path.exists(menu_path):
            time.sleep(0.1)
            os.execl(sys.executable, sys.executable, menu_path)
