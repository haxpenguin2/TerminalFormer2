#!/usr/bin/env python3
# TerminalFormer2 - single-file input (evdev else pygame+XQueryKeymap) + game logic
import curses, time, os, math, sys, json, glob, importlib.util, select
import ctypes, locale
from collections import deque
from ctypes import c_void_p, c_char_p, c_ubyte, create_string_buffer

# --- CONFIG ---
GRAVITY, JUMP_V, MOVE_SPEED = 90.0, -28.0, 24.0
FPS, MAX_SUBSTEP, DT = 60.0, 0.02, 1.0 / 60.0
DIRS = {'LEVELS': "levels", 'CAMP': "campaignlevels", 'SCORES': "scores.json", 'PLUGINS': "plugins"}
TILES = {'SOLID': '█', 'SPIKE': '▲', 'SPIKE_DN': '▼', 'CP': 'C', 'SPAWN': 'S', 'GOAL': 'G', 'PLAYER': '#'}
PHYS = {'HW': 0.4, 'HH': 0.5, 'TOL': 0.001}
for d in [DIRS['LEVELS'], DIRS['CAMP'], DIRS['PLUGINS']]:
    os.makedirs(d, exist_ok=True)

# --- plugin loader (compact) ---
REGISTRY = {}; PLUGINS = []
def load_plugins():
    for p in glob.glob(os.path.join(DIRS['PLUGINS'], "*.py")):
        try:
            name = os.path.splitext(os.path.basename(p))[0]
            spec = importlib.util.spec_from_file_location(f"plugins.{name}", p)
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            if hasattr(m, "register"):
                meta = m.register(); metas = meta if isinstance(meta, list) else [meta]
                for mm in metas:
                    if not isinstance(mm, dict): continue
                    ch = mm.get("char") or mm.get("id")
                    PLUGINS.append(mm)
                    if isinstance(ch, str) and len(ch) == 1:
                        REGISTRY[ch] = mm
        except Exception:
            pass
load_plugins()

# --- scores / save helpers ---
SAVE_SLOT_PATH = None; RESUME_FLAG = False; SPEEDRUN_MODE = False
def save_score(cat, val, name="Player"):
    data = {}
    try:
        if os.path.exists(DIRS['SCORES']):
            with open(DIRS['SCORES'], 'r') as f: data = json.load(f)
    except: data = {}
    entries = data.get(cat, [])
    entries = [{"name":"UNK","time":x} if isinstance(x,(int,float)) else x for x in entries]
    entries.append({"name":name,"time":val}); entries.sort(key=lambda x:x["time"]); data[cat]=entries[:10]
    try:
        with open(DIRS['SCORES'],"w") as f: json.dump(data, f)
    except: pass

def save_game_state_to(path, state):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f: json.dump(state, f)
        os.replace(tmp, path)
    except: pass

def load_saved_game_from(path):
    try:
        if path and os.path.exists(path):
            return json.load(open(path))
    except: pass
    return None

def clear_slot(path):
    try:
        if path and os.path.exists(path): os.remove(path)
    except: pass

# --- EVDEV BACKEND (native) ---
class EvdevBackend:
    def __init__(self):
        try:
            from evdev import InputDevice, list_devices, ecodes
            devs = [InputDevice(p) for p in list_devices()]
            self.devices = [d for d in devs if ecodes.EV_KEY in d.capabilities()]
            self.fd_map = {d.fd: d for d in self.devices}
            self.ecodes = ecodes
            self.code_map = {
                ecodes.KEY_LEFT:'LEFT', ecodes.KEY_RIGHT:'RIGHT',
                ecodes.KEY_UP:'UP', ecodes.KEY_DOWN:'DOWN',
                ecodes.KEY_W:'W', ecodes.KEY_A:'A', ecodes.KEY_S:'S', ecodes.KEY_D:'D',
                ecodes.KEY_Z:'Z', ecodes.KEY_SPACE:'SPACE', ecodes.KEY_R:'R',
                ecodes.KEY_Q:'Q', ecodes.KEY_H:'H', ecodes.KEY_ENTER:'CONTINUE',
                ecodes.KEY_M:'M'
            }
            if not self.devices:
                raise Exception("no evdev devices")
        except Exception:
            raise

    def poll(self, timeout=0.0):
        evs=[]
        try:
            r,_,_ = select.select(list(self.fd_map.keys()), [], [], timeout)
            for fd in r:
                dev = self.fd_map.get(fd)
                for ev in dev.read():
                    if ev.type == self.ecodes.EV_KEY:
                        tok = self.code_map.get(ev.code)
                        if tok and ev.value in (0,1):
                            evs.append((tok, 1 if ev.value==1 else 0))
        except Exception:
            pass
        return evs

    def close(self):
        for d in getattr(self,"devices",[]):
            try: d.close()
            except: pass

# --- PYGAME+X11 BACKEND (works in Crostini even if curses is focused) ---
class PygameBackend:
    """
    Hidden tiny pygame window + XQueryKeymap polling.
    Recreates display when focus looks lost to avoid clicking requirement.
    """
    def __init__(self):
        self.active = False
        self._held = set()
        self._last = set()
        self._last_focus = 0
        self._focus_interval = 0.25
        self._use_x11 = False
        self._display = None
        self._x11 = None
        self._keycodes = {}
        self._syms = {
            'LEFT': 0xFF51, 'RIGHT': 0xFF53, 'UP': 0xFF52, 'DOWN': 0xFF54,
            'SPACE': 0x0020, 'Q': 0x0071, 'R': 0x0072, 'M': 0x006D,
            'CONTINUE': 0xFF0D, 'W': 0x0077, 'A': 0x0061, 'S': 0x0073, 'D': 0x0064, 'Z': 0x007A, 'H': 0x0068
        }
        try:
            import os as _os
            _os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "-100,-100")
            import pygame as pg
            self.pg = pg
            pg.init()
            flags = pg.NOFRAME if hasattr(pg, 'NOFRAME') else 0
            try:
                self.screen = pg.display.set_mode((1,1), flags)
            except:
                self.screen = pg.display.set_mode((1,1))
            pg.display.set_caption("tf-input")
            try: pg.event.set_grab(True)
            except: pass
            try: pg.mouse.set_visible(False)
            except: pass

            # try X11 for keymap polling
            try:
                x11 = ctypes.CDLL("libX11.so.6")
                x11.XOpenDisplay.argtypes = [c_char_p]; x11.XOpenDisplay.restype = c_void_p
                disp = x11.XOpenDisplay(None)
                if disp:
                    x11.XKeysymToKeycode.argtypes = [c_void_p, ctypes.c_ulong]; x11.XKeysymToKeycode.restype = ctypes.c_uint
                    x11.XQueryKeymap.argtypes = [c_void_p, c_char_p]
                    keycodes = {}
                    for name, sym in self._syms.items():
                        try:
                            code = x11.XKeysymToKeycode(disp, sym)
                        except Exception:
                            code = 0
                        if code:
                            keycodes[name] = int(code)
                    if keycodes.get('LEFT') and keycodes.get('RIGHT'):
                        self._use_x11 = True
                        self._display = disp
                        self._x11 = x11
                        self._keycodes = keycodes
            except Exception:
                self._use_x11 = False

            self.active = True
        except Exception:
            self.active = False

    def _recreate_display(self):
        """Recreate the pygame display (useful when SDL/window lost focus on Crostini)."""
        try:
            pg = self.pg
            try: pg.display.quit()
            except: pass
            try: pg.display.init()
            except: pass
            flags = pg.NOFRAME if hasattr(pg, 'NOFRAME') else 0
            try:
                self.screen = pg.display.set_mode((1,1), flags)
            except:
                self.screen = pg.display.set_mode((1,1))
            try: pg.display.set_caption("tf-input")
            except: pass
            try: pg.event.set_grab(True)
            except: pass
            try: pg.mouse.set_visible(False)
            except: pass
            self._held.clear(); self._last.clear()
        except Exception:
            pass

    def poll(self, timeout=0.0):
        if not self.active:
            return []
        evs = []
        # XQueryKeymap path (state-based, focus-agnostic)
        if self._use_x11 and self._display and self._x11:
            try:
                KeysArray = c_ubyte * 32
                keys = KeysArray()
                self._x11.XQueryKeymap(self._display, ctypes.cast(keys, c_char_p))
                curr = set()
                for name, code in self._keycodes.items():
                    byte_idx = code // 8
                    bit_idx = code % 8
                    if byte_idx < 32:
                        try:
                            if (keys[byte_idx] & (1 << bit_idx)) != 0:
                                curr.add(name)
                        except Exception:
                            pass
                for down in (curr - self._last):
                    evs.append((down, 1))
                for up in (self._last - curr):
                    evs.append((up, 0))
                self._last = curr
                self._held = set(curr)
            except Exception:
                pass

        # always consume pygame events to keep SDL internal state sane
        try:
            for e in self.pg.event.get():
                if e.type == self.pg.KEYDOWN:
                    mapped = {
                        self.pg.K_LEFT:"LEFT", self.pg.K_RIGHT:"RIGHT", self.pg.K_UP:"UP", self.pg.K_DOWN:"DOWN",
                        self.pg.K_SPACE:"SPACE", self.pg.K_RETURN:"CONTINUE", self.pg.K_KP_ENTER:"CONTINUE",
                        self.pg.K_q:"Q", self.pg.K_r:"R", self.pg.K_m:"M",
                        self.pg.K_w:"W", self.pg.K_a:"A", self.pg.K_s:"S", self.pg.K_d:"D", self.pg.K_z:"Z",
                        self.pg.K_h:"H"
                    }.get(e.key)
                    if mapped and mapped not in self._held:
                        self._held.add(mapped); evs.append((mapped, 1))
                elif e.type == self.pg.KEYUP:
                    mapped = {
                        self.pg.K_LEFT:"LEFT", self.pg.K_RIGHT:"RIGHT", self.pg.K_UP:"UP", self.pg.K_DOWN:"DOWN",
                        self.pg.K_SPACE:"SPACE", self.pg.K_RETURN:"CONTINUE", self.pg.K_KP_ENTER:"CONTINUE",
                        self.pg.K_q:"Q", self.pg.K_r:"R", self.pg.K_m:"M",
                        self.pg.K_w:"W", self.pg.K_a:"A", self.pg.K_s:"S", self.pg.K_d:"D", self.pg.K_z:"Z",
                        self.pg.K_h:"H"
                    }.get(e.key)
                    if mapped and mapped in self._held:
                        try: self._held.remove(mapped)
                        except: pass
                        evs.append((mapped, 0))
        except Exception:
            try: self.pg.event.pump()
            except: pass

        # if SDL window lost focus, try to re-create display and regrab
        try:
            focused = True
            try:
                focused = bool(self.pg.key.get_focused())
            except Exception:
                focused = True
            if not focused:
                # recreate display once to recover focus reliably on Crostini/Wayland combos
                self._recreate_display()
        except Exception:
            pass

        # periodic reassert grab/flip to keep SDL responsive
        now = time.time()
        if now - self._last_focus > self._focus_interval:
            self._last_focus = now
            try:
                try: self.pg.event.set_grab(True)
                except: pass
                try: self.pg.display.flip()
                except: pass
            except: pass

        return evs

    def get_pressed_state(self):
        return set(self._held)

    def force_focus(self, timeout=0.2, step=0.01):
        """Try to reassert grab/flip and recreate display to coax SDL back."""
        if not getattr(self, "active", False): return
        pg = self.pg
        end = time.time() + timeout
        while time.time() < end:
            try: pg.event.pump()
            except: pass
            try: pg.event.set_grab(True)
            except: pass
            try: pg.display.flip()
            except: pass
            time.sleep(step)
        try: self._recreate_display()
        except: pass

    def close(self):
        try:
            if getattr(self, "_use_x11", False) and getattr(self, "_x11", None) and getattr(self, "_display", None):
                try: self._x11.XCloseDisplay(self._display)
                except: pass
                self._display = None; self._x11 = None; self._use_x11 = False
        except:
            pass
        if not getattr(self, "active", False): return
        try: self.pg.event.set_grab(False)
        except: pass
        try: self.pg.quit()
        except: pass
        self.active = False

# --- INPUT ENGINE (only evdev or pygame-backed XQueryKeymap) ---
class InputEngine:
    def __init__(self, hold_timeout=0.6):
        self.keys = {k: False for k in ['LEFT','RIGHT','UP','DOWN','JUMP','RESET','QUIT','CONTINUE','MENU']}
        self.pressed = set()
        self.ev_state = {k: False for k in self.keys}
        self._last_seen = {}
        self._hold_timeout = float(hold_timeout)
        self.backend = None
        self.backend_type = None
        self._raw_evs = []   # store last raw backend events for menus

        # try evdev if event devices exist and import works
        try:
            has_events = False
            if os.path.isdir("/dev/input"):
                for fn in os.listdir("/dev/input"):
                    if fn.startswith("event"): has_events = True; break
            if has_events:
                try:
                    self.backend = EvdevBackend(); self.backend_type = "evdev"
                except Exception:
                    self.backend = None
            if not self.backend:
                p = PygameBackend()
                if p.active:
                    self.backend = p; self.backend_type = "pygame-x11" if getattr(p, "_use_x11", False) else "pygame"
                else:
                    self.backend = None
        except Exception:
            self.backend = None

        self.token_map = {
            'LEFT':'LEFT','RIGHT':'RIGHT','UP':'JUMP','DOWN':'DOWN',
            'SPACE':'JUMP','ENTER':'CONTINUE','CONTINUE':'CONTINUE',
            'R':'RESET','Q':'QUIT','M':'MENU','A':'LEFT','D':'RIGHT',
            'W':'JUMP','S':'DOWN','Z':'JUMP','H':'LEFT'
        }
        try: print(f"InputEngine: backend={self.backend_type}", file=sys.stderr)
        except: pass

    def force_focus(self):
        try:
            if getattr(self, "backend", None) and hasattr(self.backend, "force_focus"):
                self.backend.force_focus()
        except Exception:
            pass

    def _apply_event(self, raw, value):
        mapped = self.token_map.get(raw)
        if not mapped: return
        prev = bool(self.ev_state.get(mapped, False))
        if value == 1:
            if not prev: self.pressed.add(mapped)
            self.ev_state[mapped] = True
            self._last_seen[mapped] = time.time()
        else:
            self.ev_state[mapped] = False
            self._last_seen.pop(mapped, None)

    def update(self, stdscr):
        evs = []
        try:
            if self.backend:
                evs = self.backend.poll(0.0)
        except Exception:
            evs = []
        # expose raw events for menu usage
        self._raw_evs = list(evs)

        for raw, v in evs:
            self._apply_event(raw, v)

        # sync pygame backend held-set to ev_state to ensure continuous down() works
        if self.backend_type and self.backend_type.startswith("pygame"):
            try:
                held = self.backend.get_pressed_state()
                for k in list(self.ev_state.keys()): self.ev_state[k] = False
                for raw in held:
                    m = self.token_map.get(raw)
                    if m:
                        self.ev_state[m] = True
                        self._last_seen[m] = time.time()
            except Exception:
                pass

        # release by timeout
        now = time.time()
        to_rel = [k for k, ts in list(self._last_seen.items()) if now - ts > self._hold_timeout]
        for k in to_rel:
            raw_equiv = None
            for raw, mapped in self.token_map.items():
                if mapped == k:
                    raw_equiv = raw; break
            if raw_equiv:
                self._apply_event(raw_equiv, 0)

        # curses fallback for menu input (still check it so terminals without X still work)
        curses_keys = {k: False for k in self.keys}
        try:
            while True:
                k = stdscr.getch()
                if k == -1: break
                n = {
                    curses.KEY_LEFT: 'LEFT', curses.KEY_RIGHT: 'RIGHT',
                    ord(' '): 'JUMP', ord('r'): 'RESET', ord('R'): 'RESET',
                    ord('q'): 'QUIT', ord('Q'): 'QUIT', ord('m'): 'MENU',
                    ord('M'): 'MENU', 10: 'CONTINUE', 13: 'CONTINUE',
                    curses.KEY_UP: 'UP', curses.KEY_DOWN: 'DOWN'
                }.get(k)
                if n:
                    curses_keys[n] = True
                    self._apply_event(n, 1)
        except Exception:
            pass

        for k in self.keys:
            self.keys[k] = bool(self.ev_state.get(k, False)) or curses_keys.get(k, False)

    # helper for menu: read raw backend events (useful when curses isn't focused)
    def raw_events(self):
        return list(self._raw_evs)

    def was(self, k): return k in self.pressed
    def down(self, k): return bool(self.keys.get(k, False))
    def clear(self): self.pressed.clear()
    def reset(self):
        for kk in self.keys:
            self.keys[kk] = False; self.ev_state[kk] = False
        self.pressed.clear(); self._last_seen.clear()
    def stop(self):
        try:
            if getattr(self, "backend", None):
                try: self.backend.close()
                except: pass
        except: pass

# --- game objects & helpers (condensed) ---
class Platform:
    def __init__(self, d, start_t=0.0):
        self.ox, self.oy, self.w = d['x'], d['y'], d['w']
        self.lx = d.get('lx', 0); self.ly = d.get('ly', 0)
        self.spd = d.get('spd', 1.0); self.ease = d.get('ease', 'SINE')
        self.x, self.y, self.t = self.ox, self.oy, start_t
        self.update(0)
    def update(self, dt):
        self.t += dt * self.spd
        if self.ease == 'SINE': off = math.sin(self.t)
        else:
            norm = (self.t / math.pi) % 2; off = norm - 1 if norm > 1 else 1 - norm
        self.x = self.ox + (off * (self.lx / 2)); self.y = self.oy + (off * (self.ly / 2))
    def rect(self): return (self.x, self.y, self.x + self.w, self.y + 1)

def load_level(path, platform_timers=None):
    if not os.path.exists(path): return None, [], "UNKNOWN", {}
    with open(path) as f: parts = f.read().split("__METADATA__")
    lines = [l.rstrip("\r\n") for l in parts[0].strip().split('\n') if l != ""]
    w = max((len(l) for l in lines), default=0); grid = [list(l.ljust(w,' ')) for l in lines]
    plats = []; title = os.path.splitext(os.path.basename(path))[0]; meta = {}
    if len(parts) > 1:
        try:
            d = json.loads(parts[1])
            if isinstance(d, dict):
                meta = d; title = str(d.get("title", title)).replace('"','')
                for i,p in enumerate(d.get("platforms", [])):
                    t_start = platform_timers[i] if platform_timers and i < len(platform_timers) else 0.0
                    mp = Platform(p, t_start); plats.append(mp)
                    for j in range(p['w']):
                        gy,gx = int(p['y']), int(p['x'])+j
                        if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]): grid[gy][gx] = ' '
        except: pass
    return grid, plats, title, meta

def get_plugin(ch): return REGISTRY.get(ch)
def is_solid(grid,x,y):
    if 0<=y<len(grid) and 0<=x<len(grid[0]):
        ch = grid[int(y)][int(x)]
        if ch in ('C','S','G',' '): return False
        p = get_plugin(ch)
        if p and 'runtime' in p:
            s = p['runtime'].get('solid')
            if callable(s): return bool(s(grid,x,y))
            return bool(s)
        return ch == TILES['SOLID']
    return True

def check_rect(grid,l,t,r,b):
    for yy in range(int(math.floor(t)), int(math.floor(b))+1):
        for xx in range(int(math.floor(l)), int(math.floor(r))+1):
            if is_solid(grid, xx, yy): return True
    return False

def check_plat(plats,l,t,r,b):
    for p in plats:
        pl,pt,pr,pb = p.rect()
        if l<pr and r>pl and t<pb and b>pt: return p
    return None

def resolve_char(grid,plats,cx,cy,title,default):
    p = get_plugin(default)
    if p:
        rt,ed = p.get('runtime',{}), p.get('editor',{})
        if callable(rt.get('get_display_char')):
            try: return rt['get_display_char'](grid,plats,cx,cy,title) or default
            except: pass
        return ed.get('display_char') or rt.get('display_char') or default
    return default

def draw_scene(stdscr, grid, plats, px, py, cx, cy, fps, msg, time_val, lnum, ltitle, vis=True):
    h,w = stdscr.getmaxyx(); stdscr.erase()
    gh,gw = len(grid), len(grid[0]) if grid else 0
    ox = (w-gw)//2 if gw < w else 0; oy = (h-gh)//2 if gh < h else 0
    sx = int(max(0,min(cx,max(0,gw-w)))) if gw >= w else 0
    sy = int(max(0,min(cy,max(0,gh-h)))) if gh >= h else 0
    for scr_y in range(h):
        my = scr_y - oy + sy
        if 0 <= my < gh:
            row = grid[my]; sl = min(sx+w, len(row))
            if sx < sl:
                ln = "".join([str(resolve_char(grid,plats,x,my,ltitle,row[x])) for x in range(sx,sl)])
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
        t_str = "SPEEDRUN" if SPEEDRUN_MODE else f"LEVEL {lnum}"
        if not msg: stdscr.addstr(0,0,f'{t_str} "{ltitle}"', curses.A_BOLD)
        else: stdscr.addstr(0,1,msg, curses.A_REVERSE | curses.A_BOLD)
        t_txt = f"TIME: {time_val:.2f}s"; stdscr.addstr(0, max(0, w-len(t_txt)-1), t_txt, curses.A_BOLD)
    except: pass
    stdscr.refresh()

def draw_centered_menu(stdscr,title,opts,sel):
    h,w = stdscr.getmaxyx(); box_w = max(40, min(60, max(len(title)+4, max((len(o)+6) for o in opts))))
    box_h = len(opts)+4; bx=(w-box_w)//2; by=(h-box_h)//2
    try:
        for y in range(by, by+box_h): stdscr.addstr(y, bx, " "*box_w)
        stdscr.attron(curses.A_BOLD|curses.A_UNDERLINE); stdscr.addstr(by, bx+2, title); stdscr.attroff(curses.A_BOLD|curses.A_UNDERLINE)
        for i,it in enumerate(opts):
            txt = f"> {it} <" if i==sel else f"   {it}   "; attr = curses.A_REVERSE if i==sel else curses.A_NORMAL
            stdscr.addstr(by+2+i, bx+2, txt, attr)
        stdscr.addstr(by+box_h-1, bx+2, "UP/DOWN: Navigate  ENTER: Select  M: Close", curses.A_DIM); stdscr.refresh()
    except: pass

# ---- MENU: now accepts `inp` and uses raw backend events so clicking is NOT required ----
def show_in_game_menu(stdscr, inp, allow_save=True):
    opts=["Resume"]
    if allow_save: opts.extend(["Save & Quit to Menu","Save Position (Slot)","Clear Slot Data"])
    quit_txt = "Quit (Progress Lost)" if SPEEDRUN_MODE else "Quit to Menu (No Save)"; opts.extend([quit_txt,"Cancel"])
    idx=0; stdscr.nodelay(False)
    # ensure backend focus for duration of menu
    try:
        if hasattr(inp, "force_focus"): inp.force_focus()
    except: pass

    last_nav_time = 0
    nav_delay = 0.12  # debounce
    while True:
        # keep backend updated so raw events arrive even if curses isn't focused
        inp.update(stdscr)
        # reassert focus regularly to avoid SDL losing grab while menu displayed
        try:
            if hasattr(inp, "force_focus"): inp.force_focus()
        except: pass

        # draw menu frame
        draw_centered_menu(stdscr,"PAUSE MENU",opts,idx)

        # 1) read raw backend presses first (works when terminal isn't focused)
        raw = inp.raw_events()
        handled = False
        now = time.time()
        if raw:
            for r,v in raw:
                if v != 1: continue
                # navigation keys: UP / DOWN / W / S / LEFT / RIGHT
                if r in ('UP','W'):
                    if now - last_nav_time > nav_delay:
                        idx = (idx - 1) % len(opts); last_nav_time = now; handled = True
                elif r in ('DOWN','S'):
                    if now - last_nav_time > nav_delay:
                        idx = (idx + 1) % len(opts); last_nav_time = now; handled = True
                elif r in ('LEFT',):
                    if now - last_nav_time > nav_delay:
                        idx = (idx - 1) % len(opts); last_nav_time = now; handled = True
                elif r in ('RIGHT',):
                    if now - last_nav_time > nav_delay:
                        idx = (idx + 1) % len(opts); last_nav_time = now; handled = True
                elif r in ('CONTINUE','ENTER','SPACE','Q'):  # accept/enter or Q as quick select
                    sel = opts[idx]
                    stdscr.nodelay(True)
                    inp.clear()
                    return sel if sel != "Resume" else "RESUME"
        # 2) fallback to curses.getch if backend didn't handle input (keeps arrow keys working in normal terminals)
        try:
            k = stdscr.getch()
            if k != -1:
                if k == curses.KEY_UP:
                    idx = (idx - 1) % len(opts)
                elif k == curses.KEY_DOWN:
                    idx = (idx + 1) % len(opts)
                elif k in (10,13):
                    sel = opts[idx]; stdscr.nodelay(True); return sel if sel != "Resume" else "RESUME"
                elif k in (ord('m'), ord('M'), ord('q'), ord('Q')):
                    stdscr.nodelay(True); return "RESUME"
        except Exception:
            pass

# (arcade_name_entry and remaining game code unchanged)
def arcade_name_entry(stdscr,total_time):
    stdscr.nodelay(False); name=""
    while True:
        stdscr.erase(); h,w=stdscr.getmaxyx(); cy,cx = h//2, w//2
        stdscr.addstr(cy-5, cx-len("★ CONGRATULATIONS! ★")//2, "★ CONGRATULATIONS! ★", curses.A_BOLD)
        stdscr.addstr(cy-3, cx-len(f"FINAL TIME: {total_time:.2f}s")//2, f"FINAL TIME: {total_time:.2f}s")
        stdscr.addstr(cy-1, cx-len("ENTER INITIALS:")//2, "ENTER INITIALS:", curses.A_UNDERLINE)
        field = f" {name} " + ("█" if (int(time.time()*2)%2)==0 else " "); stdscr.addstr(cy+1, cx-len(field)//2, field, curses.A_REVERSE)
        stdscr.addstr(cy+3, cx-13, "TYPE NAME - ENTER TO SUBMIT", curses.A_DIM); stdscr.refresh()
        k=stdscr.getch()
        if k in (10,13): return name if len(name)>0 else "AAA"
        if k in (curses.KEY_BACKSPACE,127,8): name=name[:-1]
        elif 32<=k<=126 and len(name)<10: name += chr(k).upper()

# --- main play loop (same as before, but calls show_in_game_menu(stdscr, inp, ...) ) ---
def play_level(stdscr, level_file, inp, level_num, t_offset=0.0, resume_state=None, allow_save=True):
    global SAVE_SLOT_PATH
    p_timers=[]; plugin_data={}
    if resume_state: p_timers=resume_state.get("platform_timers",[]); plugin_data=resume_state.get("plugin_state",{})
    grid, plats, title, meta = load_level(level_file, p_timers)
    if not grid: return "NO_FILE", 0.0
    px,py=1.5,1.5; start_cp=None
    for y,row in enumerate(grid):
        for x,cell in enumerate(row):
            if cell==TILES['SPAWN']: px,py=x+0.5,y+0.5; start_cp=(x+0.5,y+0.5); grid[y][x]=' '
    if start_cp is None: start_cp=(px,py)
    vx,vy=0.0,0.0; cp=start_cp
    if resume_state:
        try:
            saved_f=resume_state.get("level_file","")
            if saved_f and (os.path.basename(saved_f)==os.path.basename(level_file)):
                r_px,r_py=float(resume_state.get("px",-1)),float(resume_state.get("py",-1))
                if r_px>0 and r_py>0:
                    px,py=r_px,r_py; vx=float(resume_state.get("vx",0.0)); vy=float(resume_state.get("vy",0.0))
                    if "cp" in resume_state: cp=tuple(resume_state["cp"])
        except: pass
    cx,cy=0,0; fps_h=deque(maxlen=30); start=time.time(); last=time.time(); cur_t=0.0; msg=None; mend=0
    ap=None; ap_off=0.0; stdscr.nodelay(True)

    # ensure focus while we play
    try:
        if hasattr(inp, "force_focus"): inp.force_focus()
    except: pass

    def make_game_state(): return {"grid":grid,"platforms":plats,"level":title,"meta":meta}
    while True:
        inp.update(stdscr)
        if inp.was('MENU') or inp.was('QUIT'):
            draw_scene(stdscr, grid, plats, px, py, cx, cy, 0, "PAUSED (M:MENU)", t_offset+cur_t, level_num, title)
            choice = show_in_game_menu(stdscr, inp, allow_save=allow_save)

            if choice in ("RESUME","CANCEL"):
                inp.clear(); last=time.time()
                try:
                    if hasattr(inp, "force_focus"): inp.force_focus()
                except: pass

            elif choice == "SAVE_ONLY":
                if SAVE_SLOT_PATH:
                    save={"level_file":os.path.abspath(level_file),"level_num":level_num,"px":px,"py":py,"vx":vx,"vy":vy,"cp":cp,
                          "tot_time":t_offset+cur_t,"platform_timers":[p.t for p in plats],"plugin_state":plugin_data}
                    save_game_state_to(SAVE_SLOT_PATH, save); msg="SAVED"; mend=time.time()+1.5
                else: msg="NO SLOT"; mend=time.time()+1.5
                inp.clear(); last=time.time()
                try:
                    if hasattr(inp, "force_focus"): inp.force_focus()
                except: pass

            elif choice == "CLEAR_SLOT":
                if SAVE_SLOT_PATH: clear_slot(SAVE_SLOT_PATH); msg="SLOT CLEARED"; mend=time.time()+1.5
                else: msg="NO SLOT"; mend=time.time()+1.5
                inp.clear(); last=time.time()
                try:
                    if hasattr(inp, "force_focus"): inp.force_focus()
                except: pass

            elif choice == "SAVE_QUIT":
                if SAVE_SLOT_PATH:
                    save={"level_file":os.path.abspath(level_file),"level_num":level_num,"px":px,"py":py,"vx":vx,"vy":vy,"cp":cp,
                          "tot_time":t_offset+cur_t,"platform_timers":[p.t for p in plats],"plugin_state":plugin_data}
                    save_game_state_to(SAVE_SLOT_PATH, save)
                return "QUIT", 0.0
            elif choice == "QUIT_NO_SAVE": return "QUIT", 0.0

        now=time.time(); dt=min(now-last,0.1); last=now; dt=DT if dt<0 else dt; cur_t=now-start
        for p in plats: p.update(dt)
        if inp.was('RESET'):
            px,py,vx,vy,ap = cp[0],cp[1]-0.1,0,0,None
            for m in PLUGINS:
                if callable(f:=m.get('runtime',{}).get('on_player_death')):
                    try: f(make_game_state(), plugin_data)
                    except: pass

        ground = check_rect(grid, px-PHYS['HW'], py+PHYS['HH'], px+PHYS['HW'], py+PHYS['HH']+0.05)
        idir = (inp.down('RIGHT') - inp.down('LEFT'))

        if ap:
            if inp.was('JUMP'):
                vy = JUMP_V; px = ap.x + ap_off; ap = None
            else:
                rem, cur = dt, ap_off
                while rem>0:
                    step=min(rem,MAX_SUBSTEP); rem-=step
                    nxt = cur + (idir*MOVE_SPEED)*step
                    wx,wy = ap.x + nxt, ap.y - PHYS['HH'] - PHYS['TOL']
                    if check_rect(grid, wx-PHYS['HW'], wy-PHYS['HH']+0.1, wx+PHYS['HW'], wy+PHYS['HH']-0.1): break
                    cur = nxt
                ap_off = cur; px = ap.x + cur; py = ap.y - PHYS['HH'] - PHYS['TOL']; vy = 0
                if ap_off + PHYS['HW'] <= 0 or ap_off - PHYS['HW'] >= ap.w: ap=None
                sy = int(py + PHYS['HH'] + 0.05)
                for lx in {int(px), int(px-PHYS['HW']+0.1), int(px+PHYS['HW']-0.1)}:
                    if 0<=sy<len(grid) and 0<=lx<len(grid[0]):
                        pmeta = get_plugin(grid[sy][lx])
                        if pmeta and callable(f:=pmeta.get('runtime',{}).get('on_player_supported')):
                            try:
                                pstate={"px":px,"py":py,"vx":vx,"vy":vy}
                                f({"dt":dt,"grid":grid,"level":title,"meta":meta}, pstate, lx, sy, plugin_data)
                                vx=float(pstate.get("vx",vx)); vy=float(pstate.get("vy",vy))
                            except: pass
        else:
            if inp.was('JUMP') and ground: vy = JUMP_V
            else: vy += GRAVITY * dt
            vx = idir * MOVE_SPEED
            rem = dt
            while rem>0:
                step=min(rem,MAX_SUBSTEP); rem-=step
                npx = px + vx*step
                if check_rect(grid, npx-PHYS['HW'], py-PHYS['HH']+0.01, npx+PHYS['HW'], py+PHYS['HH']-0.01): vx=0
                elif check_plat(plats, npx-PHYS['HW'], py-PHYS['HH']+0.1, npx+PHYS['HW'], py+PHYS['HH']-0.1): vx=0
                else: px=npx
            rem = dt
            while rem>0:
                step=min(rem,MAX_SUBSTEP); rem-=step
                npy = py + vy*step
                if check_rect(grid, px-PHYS['HW'], npy-PHYS['HH'], px+PHYS['HW'], npy+PHYS['HH']):
                    if vy>0:
                        ly=int(math.floor(npy+PHYS['HH'])); py,vy = ly-PHYS['HH']-0.001,0
                        for lx in {int(px), int(px-PHYS['HW']+0.01), int(px+PHYS['HW']-0.01)}:
                            if 0<=ly<len(grid) and 0<=lx<len(grid[0]):
                                pmeta=get_plugin(grid[ly][lx])
                                if pmeta and callable(f:=pmeta.get('runtime',{}).get('on_player_supported')):
                                    try:
                                        pstate={"px":px,"py":py,"vx":vx,"vy":vy}
                                        f({"dt":step,"grid":grid,"level":title,"meta":meta}, pstate, lx, ly, plugin_data)
                                        vx=float(pstate.get("vx",vx)); vy=float(pstate.get("vy",vy))
                                    except: pass
                    elif vy<0: py,vy = math.floor(npy-PHYS['HH'])+PHYS['HH']+1.001, 0
                else:
                    hit = check_plat(plats, px-PHYS['HW'], npy-PHYS['HH'], px+PHYS['HW'], npy+PHYS['HH'])
                    if hit:
                        if vy>0:
                            ap=hit; ap_off = px - hit.x; py = hit.y - PHYS['HH'] - PHYS['TOL']; vy=0
                        elif vy<0: py,vy = hit.y + 1.0 + PHYS['HH'] + PHYS['TOL'], 0
                    else: py = npy

        icx,icy = int(px), int(py)
        crush = is_solid(grid, px, py)
        dist_to_cp = math.hypot(px-cp[0], py-cp[1]); is_safe=(dist_to_cp<1.0)
        tile = grid[icy][icx] if (0<=icy<len(grid) and 0<=icx<len(grid[0])) else ' '
        if tile==TILES['GOAL']: return "NEXT_LEVEL", cur_t

        tp=get_plugin(tile)
        if tp and 'runtime' in tp and callable(t:=tp['runtime'].get('on_player_touch')):
            try:
                pstate={"px":px,"py":py,"vx":vx,"vy":vy}
                ret = t({"grid":grid,"platforms":plats,"player":pstate,"level":title,"meta":meta}, pstate, icx, icy, plugin_data)
                vx=float(pstate.get("vx",vx)); vy=float(pstate.get("vy",vy))
                if isinstance(ret, dict):
                    if "vx" in ret: vx=float(ret["vx"])
                    if "vy" in ret: vy=float(ret["vy"])
            except: pass

        tp=get_plugin(tile); deadly = bool(tp['runtime'].get('deadly',False)) if tp and 'runtime' in tp else False
        if tp and 'runtime' in tp and callable(f:=tp['runtime'].get('on_player_collide')):
            try: f({"grid":grid,"platforms":plats,"player":{"px":px,"py":py,"vx":vx,"vy":vy},"level":title,"meta":meta},{"px":px,"py":py,"vx":vx,"vy":vy}, icx, icy, plugin_data)
            except: pass

        should_die, reason = False, ""
        if crush and not is_safe: should_die, reason = True, "CRUSH"
        if tile in (TILES['SPIKE'], TILES['SPIKE_DN']): should_die, reason = True, "SPIKE"
        if deadly: should_die, reason = True, f"PLUGIN [{tile}]"

        if should_die:
            for i in range(10):
                draw_scene(stdscr, grid, plats, px, py, int(cx), int(cy), 60, f"DEAD! ({reason})", cur_t, level_num, title, i%2!=0)
                time.sleep(0.05)
            inp.reset(); curses.flushinp()
            for m in PLUGINS:
                if callable(f:=m.get('runtime',{}).get('on_player_death')):
                    try: f({"grid":grid,"level":title,"meta":meta}, plugin_data)
                    except: pass
            px,py,vx,vy,ap = cp[0],cp[1]-0.1,0,0,None
        elif tile==TILES['CP']:
            if (icx+0.5, icy+0.5)!=cp: cp=(icx+0.5, icy+0.5); msg="CHECKPOINT"; mend=time.time()+1.5

        h,w = stdscr.getmaxyx(); cx += (int(px)-w//2-cx)*0.1; cy += (int(py)-h//2-cy)*0.1
        fps_h.append(1.0/dt if dt>0 else 60)
        if time.time()>mend: msg=None
        inp.clear()
        rpy = (float(int(ap.y)) - 0.5) if ap else py
        draw_scene(stdscr, grid, plats, px, rpy, int(cx), int(cy), sum(fps_h)/len(fps_h), msg, t_offset+cur_t, level_num, title)
        time.sleep(0.005)

# --- entry / args (compact) ---
def main(stdscr):
    global SAVE_SLOT_PATH, RESUME_FLAG, SPEEDRUN_MODE
    locale.setlocale(locale.LC_ALL, '')
    try: curses.curs_set(0)
    except: pass
    hold_timeout = 0.6; inp=None; mode, path, tot_t, lvl = "CAMP","",0.0,1; resume_state=None
    args = sys.argv[1:]; i=0
    while i<len(args):
        a=args[i]
        if a=="--slot" and i+1<len(args): SAVE_SLOT_PATH=args[i+1]; i+=2
        elif a=="--resume": RESUME_FLAG=True; i+=1
        elif a=="--speedrun": SPEEDRUN_MODE=True; i+=1
        elif a=="--hold-timeout" and i+1<len(args):
            try: hold_timeout=float(args[i+1])
            except: hold_timeout=0.6
            i+=2
        else: mode, path="SNGL", a; i+=1

    if RESUME_FLAG and SAVE_SLOT_PATH:
        resume_state = load_saved_game_from(SAVE_SLOT_PATH)
        if resume_state:
            saved_lvl=int(resume_state.get("level_num",1)); check_path=os.path.join(DIRS['CAMP'], f"level{saved_lvl}.txt")
            if resume_state.get("completed", False) or not os.path.exists(check_path):
                resume_state=None; lvl=1; tot_t=0.0
            else:
                lvl=saved_lvl
                if "tot_time" in resume_state: tot_t=float(resume_state["tot_time"])

    try:
        inp = InputEngine(hold_timeout)
        while True:
            if mode=="CAMP":
                if resume_state and "level_file" in resume_state: fpath=resume_state["level_file"]
                else: fpath=os.path.join(DIRS['CAMP'], f"level{lvl}.txt")
            else: fpath = path if os.path.exists(path) else os.path.join(DIRS['LEVELS'], path)
            if not os.path.exists(fpath):
                if mode=="CAMP" and lvl>1:
                    if SAVE_SLOT_PATH:
                        if SPEEDRUN_MODE: clear_slot(SAVE_SLOT_PATH)
                        else: save_game_state_to(SAVE_SLOT_PATH, {"level_num":1,"completed":True})
                    if SPEEDRUN_MODE: player_name=arcade_name_entry(stdscr, tot_t); save_score("speedrun_camp", tot_t, player_name)
                    else: save_score("campaign", tot_t, "Player")
                    stdscr.erase(); stdscr.addstr(curses.LINES//2, (curses.COLS-20)//2, f"DONE! TIME: {tot_t:.2f}s", curses.A_BOLD); stdscr.refresh(); time.sleep(3)
                elif mode=="CAMP":
                    stdscr.addstr(0,0,"Error: No Campaign Levels found in 'campaignlevels/'"); stdscr.refresh(); time.sleep(2)
                return
            can_save_in_menu = (mode=="CAMP" and not SPEEDRUN_MODE)
            res, el = play_level(stdscr, fpath, inp, lvl, tot_t, resume_state=resume_state, allow_save=can_save_in_menu)
            resume_state=None
            if res=="QUIT": return
            if res=="NEXT_LEVEL":
                stdscr.erase(); stdscr.addstr(curses.LINES//2, (curses.COLS-20)//2, "LEVEL COMPLETE!", curses.A_BOLD); stdscr.refresh(); time.sleep(0.6)
                tot_t += el; lvl += 1
    except KeyboardInterrupt:
        pass
    finally:
        if inp: inp.stop()

if __name__ == "__main__":
    curses.wrapper(main)
