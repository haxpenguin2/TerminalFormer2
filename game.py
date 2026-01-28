#!/usr/bin/env python3
# game.py - The "Who is the Killer?" Edition
import curses, time, os, math, sys, json, glob, importlib.util
from collections import deque

# --- CONFIGURATION ---
GRAVITY, JUMP_V, MOVE_SPEED = 90.0, -28.0, 24.0
FPS, MAX_SUBSTEP = 60.0, 0.02
DT = 1.0 / FPS
DIRS = {'LEVELS': "levels", 'CAMP': "campaignlevels", 'SCORES': "scores.json", 'PLUGINS': "plugins"}
TILES = {'SOLID': '█', 'SPIKE': '▲', 'SPIKE_DN': '▼', 'CP': 'C', 'SPAWN': 'S', 'GOAL': 'G', 'PLAYER': '#'}
PHYS = {'HW': 0.4, 'HH': 0.5, 'TOL': 0.001}

# --- PLUGIN LOADER ---
REGISTRY, PLUGINS = {}, []
def load_plugins():
    if not os.path.exists(DIRS['PLUGINS']): os.makedirs(DIRS['PLUGINS'], exist_ok=True)
    print("Loading plugins...")
    for path in glob.glob(os.path.join(DIRS['PLUGINS'], "*.py")):
        try:
            name = os.path.splitext(os.path.basename(path))[0]
            spec = importlib.util.spec_from_file_location(f"plugins.{name}", path)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            if hasattr(mod, "register"):
                meta = mod.register()
                metas = meta if isinstance(meta, list) else [meta]
                for m in metas:
                    if not isinstance(m, dict): continue
                    ch = m.get("char") or m.get("id")
                    PLUGINS.append(m)
                    if isinstance(ch, str) and len(ch) == 1:
                        REGISTRY[ch] = m
                        print(f" - Loaded '{name}' for character [{ch}]")
        except Exception as e: print(f"Failed to load {path}: {e}")

load_plugins()

def get_plugin(ch): return REGISTRY.get(ch)

# --- SCORE MANAGER ---
def save_score(cat, val):
    data = {}
    try:
        if os.path.exists(DIRS['SCORES']):
            with open(DIRS['SCORES'], 'r') as f: data = json.load(f)
    except: pass
    data.setdefault(cat, []).append(val)
    data[cat] = sorted(data[cat])[:5]
    with open(DIRS['SCORES'], 'w') as f: json.dump(data, f)

# --- INPUT ENGINE ---
try: import evdev_input; HAS_EVDEV = True
except ImportError: HAS_EVDEV = False

class InputEngine:
    def __init__(self):
        self.keys = {k: False for k in ['LEFT', 'RIGHT', 'UP', 'DOWN', 'JUMP', 'RESET', 'QUIT', 'CONTINUE']}
        self.pressed = set()
        self.evdev_state = {k: False for k in self.keys}
        self.dev = evdev_input.EvdevInput() if HAS_EVDEV else None

    def update(self, stdscr):
        if self.dev and self.dev.devices:
            for t, v in self.dev.poll(0.0):
                k = {'LEFT':'LEFT','RIGHT':'RIGHT','UP':'JUMP','SPACE':'JUMP','R':'RESET','Q':'QUIT','CONTINUE':'CONTINUE'}.get(t)
                if k:
                    if v == 1: self.pressed.add(k); self.evdev_state[k] = True
                    elif v == 0: self.evdev_state[k] = False

        curses_keys = {k: False for k in self.keys}
        try:
            while (k := stdscr.getch()) != -1:
                n = {curses.KEY_LEFT:'LEFT', curses.KEY_RIGHT:'RIGHT', ord(' '):'JUMP', ord('r'):'RESET', ord('R'):'RESET', ord('q'):'QUIT', ord('Q'):'QUIT'}.get(k)
                if n:
                    curses_keys[n] = True; self.pressed.add(n)
                    if n == 'JUMP': curses_keys['CONTINUE'] = True; self.pressed.add('CONTINUE')
        except: pass

        for k in self.keys: self.keys[k] = self.evdev_state[k] or curses_keys[k]

    def reset(self):
        for k in self.keys: self.keys[k] = False; self.evdev_state[k] = False
        self.pressed.clear()

    def was(self, k): return k in self.pressed
    def down(self, k): return self.keys[k]
    def clear(self): self.pressed.clear()
    def stop(self):
        if self.dev: self.dev.close()

# --- MOVING PLATFORM ---
class Platform:
    def __init__(self, d):
        self.ox, self.oy, self.w = d['x'], d['y'], d['w']
        self.lx, self.ly, self.spd = d.get('lx',0), d.get('ly',0), d.get('spd',1.0)
        self.ease = d.get('ease', 'SINE')
        self.x, self.y, self.t = self.ox, self.oy, 0.0

    def update(self, dt):
        self.t += dt * self.spd
        off = math.sin(self.t) if self.ease == 'SINE' else ((self.t/math.pi)%2 - 1 if (self.t/math.pi)%2 > 1 else 1 - (self.t/math.pi)%2)
        self.x, self.y = self.ox + (off * (self.lx/2)), self.oy + (off * (self.ly/2))

    def rect(self): return (self.x, self.y, self.x + self.w, self.y + 1)

# --- PHYSICS & LOADING ---
def load_level(path):
    if not os.path.exists(path): return None, [], "UNKNOWN", {}
    with open(path) as f: parts = f.read().split("__METADATA__")
    lines = [l.rstrip("\r\n") for l in parts[0].strip().split('\n') if l != ""]
    w = max(len(l) for l in lines) if lines else 0
    grid = [list(l.ljust(w, ' ')) for l in lines]
    plats, title = [], os.path.splitext(os.path.basename(path))[0]
    meta = {}
    if len(parts) > 1:
        try:
            d = json.loads(parts[1])
            if isinstance(d, dict):
                meta = d
                title = str(d.get("title", title)).replace('"', '')
                for p in d.get("platforms", []):
                    plats.append(Platform(p))
                    for i in range(p['w']):
                        gy, gx = int(p['y']), int(p['x']) + i
                        if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]): grid[gy][gx] = ' '
        except: pass
    return grid, plats, title, meta

def is_solid(grid, x, y):
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        ch = grid[int(y)][int(x)]
        if ch in ('C', 'S', 'G', ' '): return False
        p = get_plugin(ch)
        if p and 'runtime' in p:
            s = p['runtime'].get('solid')
            return bool(s(grid, x, y)) if callable(s) else bool(s)
        return ch == TILES['SOLID']
    return True

def check_rect(grid, l, t, r, b):
    # This checks for ANY solid block in the rect
    for y in range(int(math.floor(t)), int(math.floor(b)) + 1):
        for x in range(int(math.floor(l)), int(math.floor(r)) + 1):
            if is_solid(grid, x, y): return True
    return False

def check_plat(plats, l, t, r, b):
    for p in plats:
        pl, pt, pr, pb = p.rect()
        if l < pr and r > pl and t < pb and b > pt: return p
    return None

# --- RENDERING ---
def resolve_char(grid, plats, cx, cy, title, default):
    p = get_plugin(default)
    if p:
        rt, ed = p.get('runtime', {}), p.get('editor', {})
        if callable(rt.get('get_display_char')):
            try: return rt['get_display_char'](grid, plats, cx, cy, title) or default
            except: pass
        return ed.get('display_char') or rt.get('display_char') or default
    return default

def draw_scene(stdscr, grid, plats, px, py, cx, cy, fps, msg, time, lnum, ltitle, vis=True):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    gh, gw = len(grid), len(grid[0]) if grid else 0
    ox = (w - gw) // 2 if gw < w else 0
    oy = (h - gh) // 2 if gh < h else 0
    sx = int(max(0, min(cx, max(0, gw - w)))) if gw >= w else 0
    sy = int(max(0, min(cy, max(0, gh - h)))) if gh >= h else 0

    for scr_y in range(h):
        my = scr_y - oy + sy
        if 0 <= my < gh:
            row = grid[my]
            sl = min(sx + w, len(row))
            if sx < sl:
                ln = "".join([str(resolve_char(grid, plats, x, my, ltitle, row[x])) for x in range(sx, sl)])
                try: stdscr.addstr(scr_y, max(0, ox), ln)
                except: pass

    for p in plats:
        spx, spy = int(p.x - sx) + ox, int(p.y - sy) + oy
        if 0 <= spy < h:
            dl = min(w - spx, p.w + (spx if spx < 0 else 0))
            if dl > 0:
                try: stdscr.addstr(spy, max(0, spx), TILES['SOLID'] * int(dl), curses.A_BOLD)
                except: pass

    spx, spy = int(px - sx) + ox, int(py - sy) + oy
    if vis and 0 <= spx < w and 0 <= spy < h:
        try: stdscr.addch(spy, spx, TILES['PLAYER'], curses.A_BOLD)
        except: pass

    try:
        if not msg: stdscr.addstr(0, 0, f"LEVEL {lnum} \"{ltitle}\"", curses.A_BOLD)
        else: stdscr.addstr(0, 1, msg, curses.A_REVERSE | curses.A_BOLD)
        stdscr.addstr(0, w - 15, f"TIME: {time:.2f}s", curses.A_BOLD)
        stdscr.addstr(h-1, 0, f"Pos: {int(px)},{int(py)} | FPS: {int(fps)}")
    except: pass
    stdscr.refresh()

# --- MAIN LOOP ---
def play_level(stdscr, level_file, inp, level_num, t_offset=0.0):
    grid, plats, title, meta = load_level(level_file)
    if not grid: return "NO_FILE", 0.0

    px, py = 1.5, 1.5
    start_cp = None # Track original spawn point
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == TILES['SPAWN']:
                px, py = x + 0.5, y + 0.5
                start_cp = (x + 0.5, y + 0.5)
                grid[y][x] = ' ' # Clear Spawn, keep CP

    if start_cp is None: start_cp = (px, py)
    cp, vx, vy, cx, cy = start_cp, 0.0, 0.0, 0, 0
    fps_h = deque(maxlen=30)
    start, last, cur_t, msg, mend = time.time(), time.time(), 0.0, None, 0
    ap, ap_off = None, 0.0
    stdscr.nodelay(True)

    def make_game_state():
        return {"grid": grid, "platforms": plats, "level": title, "meta": meta}

    while True:
        inp.update(stdscr)
        if inp.was('QUIT'):
            inp.clear(); curses.flushinp()
            while True:
                draw_scene(stdscr, grid, plats, px, py, cx, cy, 0, "PAUSED (Q:QUIT / SPACE:RESUME)", t_offset+cur_t, level_num, title)
                inp.update(stdscr)
                if inp.was('QUIT'): return "QUIT", 0.0
                if inp.was('JUMP') or inp.was('CONTINUE'): last = time.time(); break
                time.sleep(0.05)
            inp.clear()

        now = time.time()
        dt = min(now - last, 0.1); last = now; dt = DT if dt < 0 else dt
        cur_t = now - start
        for p in plats: p.update(dt)

        if inp.was('RESET'):
            px, py, vx, vy, ap = cp[0], cp[1] - 0.1, 0, 0, None
            for m in PLUGINS:
                if callable(f := m.get('runtime', {}).get('on_player_death')):
                    try: f(make_game_state(), {})
                    except: pass

        ground = check_rect(grid, px - PHYS['HW'], py + PHYS['HH'], px + PHYS['HW'], py + PHYS['HH'] + 0.05)
        idir = (inp.down('RIGHT') - inp.down('LEFT'))

        if ap: # Attached
            if inp.was('JUMP'): vy, px, ap = JUMP_V, ap.x + ap_off, None
            else:
                rem, cur = dt, ap_off
                while rem > 0:
                    step = min(rem, MAX_SUBSTEP); rem -= step
                    nxt = cur + (idir * MOVE_SPEED) * step
                    wx, wy = ap.x + nxt, ap.y - PHYS['HH'] - PHYS['TOL']
                    if check_rect(grid, wx - PHYS['HW'], wy - PHYS['HH'] + 0.1, wx + PHYS['HW'], wy + PHYS['HH'] - 0.1): break
                    cur = nxt
                ap_off, px, py, vy = cur, ap.x + cur, ap.y - PHYS['HH'] - PHYS['TOL'], 0
                if ap_off + PHYS['HW'] <= 0 or ap_off - PHYS['HW'] >= ap.w: ap = None

                sy = int(py + PHYS['HH'] + 0.05)
                for lx in {int(px), int(px - PHYS['HW'] + 0.1), int(px + PHYS['HW'] - 0.1)}:
                    if 0<=sy<len(grid) and 0<=lx<len(grid[0]):
                        pmeta = get_plugin(grid[sy][lx])
                        if pmeta and callable(f := pmeta.get('runtime', {}).get('on_player_supported')):
                            try:
                                pstate = {"px": px, "py": py, "vx": vx, "vy": vy}
                                f({"dt": dt, "grid": grid, "level": title, "meta": meta}, pstate, lx, sy, {})
                                vx = float(pstate.get("vx", vx)); vy = float(pstate.get("vy", vy))
                            except: pass
        else: # Detached
            if inp.was('JUMP') and ground: vy = JUMP_V
            else: vy += GRAVITY * dt
            vx = idir * MOVE_SPEED

            rem = dt
            while rem > 0:
                step = min(rem, MAX_SUBSTEP); rem -= step
                npx = px + vx * step
                if check_rect(grid, npx - PHYS['HW'], py - PHYS['HH'] + 0.01, npx + PHYS['HW'], py + PHYS['HH'] - 0.01): vx = 0
                elif check_plat(plats, npx - PHYS['HW'], py - PHYS['HH'] + 0.1, npx + PHYS['HW'], py + PHYS['HH'] - 0.1): vx = 0
                else: px = npx

            rem = dt
            while rem > 0:
                step = min(rem, MAX_SUBSTEP); rem -= step
                npy = py + vy * step
                if check_rect(grid, px - PHYS['HW'], npy - PHYS['HH'], px + PHYS['HW'], npy + PHYS['HH']):
                    if vy > 0:
                        ly = int(math.floor(npy + PHYS['HH']))
                        py, vy = ly - PHYS['HH'] - 0.001, 0
                        for lx in {int(px), int(px - PHYS['HW'] + 0.01), int(px + PHYS['HW'] - 0.01)}:
                            if 0<=ly<len(grid) and 0<=lx<len(grid[0]):
                                pmeta = get_plugin(grid[ly][lx])
                                if pmeta and callable(f := pmeta.get('runtime', {}).get('on_player_supported')):
                                    try:
                                        pstate = {"px": px, "py": py, "vx": vx, "vy": vy}
                                        f({"dt": step, "grid": grid, "level": title, "meta": meta}, pstate, lx, ly, {})
                                        vx = float(pstate.get("vx", vx)); vy = float(pstate.get("vy", vy))
                                    except: pass
                    elif vy < 0: py, vy = math.floor(npy - PHYS['HH']) + PHYS['HH'] + 1.001, 0
                else:
                    hit = check_plat(plats, px - PHYS['HW'], npy - PHYS['HH'], px + PHYS['HW'], npy + PHYS['HH'])
                    if hit:
                        if vy > 0: ap, ap_off, py, vy = hit, px - hit.x, hit.y - PHYS['HH'] - PHYS['TOL'], 0
                        elif vy < 0: py, vy = hit.y + 1.0 + PHYS['HH'] + PHYS['TOL'], 0
                    else: py = npy

        # Interactions
        icx, icy = int(px), int(py)

        # --- FIXED & DEBUGGED DEATH LOGIC ---
        # 1. Crush: Only if CENTER POINT is in wall.
        crush = is_solid(grid, px, py)

        # 2. Safe Zone: Check strict distance to CP to cover Spawn area too.
        dist_to_cp = math.sqrt((px - cp[0])**2 + (py - cp[1])**2)
        is_safe = (dist_to_cp < 1.0)

        tile = grid[icy][icx] if (0 <= icy < len(grid) and 0 <= icx < len(grid[0])) else ' '

        if tile == TILES['GOAL']: return "NEXT_LEVEL", cur_t

        tp = get_plugin(tile)
        if tp and 'runtime' in tp:
            touch = tp['runtime'].get('on_player_touch')
            if callable(touch):
                try:
                    pstate = {"px": px, "py": py, "vx": vx, "vy": vy}
                    ret = touch({"grid": grid, "platforms": plats, "player": {"px": px, "py": py, "vx": vx, "vy": vy}, "level": title, "meta": meta}, pstate, icx, icy, {})
                    vx = float(pstate.get("vx", vx)); vy = float(pstate.get("vy", vy))
                    if isinstance(ret, dict):
                        if "vx" in ret: vx = float(ret["vx"])
                        if "vy" in ret: vy = float(ret["vy"])
                except: pass

        tp = get_plugin(tile)
        deadly = bool(tp['runtime'].get('deadly', False)) if tp and 'runtime' in tp else False
        if tp and 'runtime' in tp and callable(f := tp['runtime'].get('on_player_collide')):
             try: f({"grid": grid, "platforms": plats, "player": {"px": px, "py": py, "vx": vx, "vy": vy}, "level": title, "meta": meta}, {"px": px, "py": py, "vx": vx, "vy": vy}, icx, icy, {})
             except: pass

        should_die, reason = False, ""

        if crush and not is_safe: should_die, reason = True, "CRUSH"
        if tile in (TILES['SPIKE'], TILES['SPIKE_DN']): should_die, reason = True, "SPIKE"
        if deadly: should_die, reason = True, f"PLUGIN [{tile}]"

        if should_die:
            for i in range(10): # Longer death anim to read message
                draw_scene(stdscr, grid, plats, px, py, int(cx), int(cy), 60, f"DEAD! ({reason})", cur_t, level_num, title, i%2!=0)
                time.sleep(0.05)
            inp.reset(); curses.flushinp()
            for m in PLUGINS:
                if callable(f := m.get('runtime', {}).get('on_player_death')):
                    try: f({"grid": grid, "level": title, "meta": meta}, {})
                    except: pass
            px, py, vx, vy, ap = cp[0], cp[1] - 0.1, 0, 0, None
        elif tile == TILES['CP']:
            if (icx+0.5, icy+0.5) != cp: cp, msg, mend = (icx+0.5, icy+0.5), "CHECKPOINT", time.time() + 1.5

        h, w = stdscr.getmaxyx()
        cx += (int(px) - w//2 - cx) * 0.1; cy += (int(py) - h//2 - cy) * 0.1
        fps_h.append(1.0/dt if dt > 0 else 60)
        if time.time() > mend: msg = None

        inp.clear()
        rpy = (float(int(ap.y)) - 0.5) if ap else py
        draw_scene(stdscr, grid, plats, px, rpy, int(cx), int(cy), sum(fps_h)/len(fps_h), msg, t_offset + cur_t, level_num, title)
        time.sleep(0.005)

def main(stdscr):
    curses.curs_set(0); inp = InputEngine()
    mode, path, tot_t, lvl = "CAMP", "", 0.0, 1
    if len(sys.argv) > 1: mode, path = "SNGL", sys.argv[1]

    try:
        while True:
            fpath = path if mode == "SNGL" else os.path.join(DIRS['CAMP'], f"level{lvl}.txt")
            if mode == "SNGL" and not os.path.exists(fpath): fpath = os.path.join(DIRS['LEVELS'], path)
            if not os.path.exists(fpath):
                if mode == "CAMP" and lvl > 1:
                    save_score("campaign", tot_t)
                    stdscr.erase(); stdscr.addstr(curses.LINES//2, (curses.COLS-30)//2, f"DONE! TIME: {tot_t:.2f}s", curses.A_BOLD)
                    stdscr.refresh(); time.sleep(3)
                elif mode == "CAMP": stdscr.addstr(0,0,"Error: No Campaign Levels"); stdscr.refresh(); time.sleep(2)
                return

            res, el = play_level(stdscr, fpath, inp, lvl, tot_t)
            if res == "QUIT": return
            if res == "NEXT_LEVEL":
                stdscr.erase(); stdscr.addstr(curses.LINES//2, (curses.COLS-20)//2, f"COMPLETED! {el:.2f}s", curses.A_BOLD)
                stdscr.refresh(); curses.flushinp(); time.sleep(0.5)
                while True:
                    inp.update(stdscr)
                    if inp.was('CONTINUE') or inp.was('JUMP'): inp.clear(); break
                    time.sleep(0.05)
                if mode == "SNGL": save_score(os.path.basename(fpath), el); return
                tot_t += el; lvl += 1
    except KeyboardInterrupt: pass
    finally: inp.stop()

if __name__ == "__main__":
    for d in DIRS.values():
        if not d.endswith('.json'): os.makedirs(d, exist_ok=True)
    curses.wrapper(main)
