#!/usr/bin/env python3
# game.py - TerminalFormer2 (Chromebook-friendly input + small optimizations)
import curses
import time
import os
import math
import sys
import json
import glob
import importlib.util
import select
import ctypes
import locale
from collections import deque
from ctypes import c_void_p, c_char_p, c_uint, create_string_buffer, c_ubyte

# --- CONFIG ---
GRAVITY = 90.0
JUMP_V = -28.0
MOVE_SPEED = 24.0
FPS = 60.0
MAX_SUBSTEP = 0.02
DT = 1.0 / FPS

DIRS = {
    'LEVELS': "levels",
    'CAMP': "campaignlevels",
    'SCORES': "scores.json",
    'PLUGINS': "plugins"
}

TILES = {
    'SOLID': '█',
    'SPIKE': '▲',
    'SPIKE_DN': '▼',
    'CP': 'C',
    'SPAWN': 'S',
    'GOAL': 'G',
    'PLAYER': '#'
}

PHYS = {
    'HW': 0.4,
    'HH': 0.5,
    'TOL': 0.001
}

# Ensure directories exist
for d in [DIRS['LEVELS'], DIRS['CAMP'], DIRS['PLUGINS']]:
    os.makedirs(d, exist_ok=True)

# --- PLUGIN LOADER ---
REGISTRY = {}
PLUGINS = []

def load_plugins():
    for path in glob.glob(os.path.join(DIRS['PLUGINS'], "*.py")):
        try:
            name = os.path.splitext(os.path.basename(path))[0]
            spec = importlib.util.spec_from_file_location(f"plugins.{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "register"):
                meta = mod.register()
                metas = meta if isinstance(meta, list) else [meta]
                for m in metas:
                    if not isinstance(m, dict): continue
                    ch = m.get("char") or m.get("id")
                    PLUGINS.append(m)
                    if isinstance(ch, str) and len(ch) == 1:
                        REGISTRY[ch] = m
        except Exception:
            pass

load_plugins()

def get_plugin(ch):
    return REGISTRY.get(ch)

# --- SCORES ---
def save_score(cat, val, name="Player"):
    data = {}
    try:
        if os.path.exists(DIRS['SCORES']):
            with open(DIRS['SCORES'], 'r') as f:
                data = json.load(f)
    except:
        pass

    entries = data.get(cat, [])
    entries = [{"name": "UNK", "time": x} if isinstance(x, (int, float)) else x for x in entries]
    entries.append({"name": name, "time": val})
    entries.sort(key=lambda x: x["time"])
    data[cat] = entries[:10]

    try:
        with open(DIRS['SCORES'], 'w') as f:
            json.dump(data, f)
    except:
        pass

# --- SAVE SLOT HELPERS ---
SAVE_SLOT_PATH = None
RESUME_FLAG = False
SPEEDRUN_MODE = False

def save_game_state_to(path, state):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except:
        pass

def load_saved_game_from(path):
    try:
        if path and os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except:
        pass
    return None

def clear_slot(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except:
        pass

# --- X11 INPUT HELPER (robust) ---
class X11Input:
    """Directly queries X11 server for key state. Zero delay, no repeat lag."""
    def __init__(self):
        self.lib = None
        self.display = None
        self.keycodes = {}
        try:
            self.lib = ctypes.CDLL('libX11.so.6')
            # prototypes
            self.lib.XOpenDisplay.argtypes = [c_char_p]
            self.lib.XOpenDisplay.restype = c_void_p
            self.lib.XQueryKeymap.argtypes = [c_void_p, c_char_p]
            self.lib.XKeysymToKeycode.argtypes = [c_void_p, c_uint]
            self.lib.XKeysymToKeycode.restype = c_uint
            self.lib.XCloseDisplay.argtypes = [c_void_p]

            self.display = self.lib.XOpenDisplay(None)
            if not self.display:
                raise Exception("No X11 Display")

            # Use common keysyms (hex constants) and map to readable tokens
            syms = {
                'LEFT': 0xFF51, 'RIGHT': 0xFF53, 'UP': 0xFF52, 'DOWN': 0xFF54,
                'SPACE': 0x0020, 'Q': 0x0071, 'R': 0x0072, 'M': 0x006D,
                'CONTINUE': 0xFF0D, # Return
                'W': 0x0077, 'A': 0x0061, 'S': 0x0073, 'D': 0x0064, 'Z': 0x007a
            }
            for name, sym in syms.items():
                try:
                    code = self.lib.XKeysymToKeycode(self.display, sym)
                except Exception:
                    code = 0
                if code:
                    # store numeric keycode (uses X keycode space)
                    self.keycodes[name] = int(code)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.display and self.lib:
            try:
                self.lib.XCloseDisplay(self.display)
            except:
                pass
        self.display = None

    def get_pressed(self):
        """Return set of token names currently down according to XQueryKeymap."""
        if not self.display:
            return set()
        # c_ubyte array yields ints when indexed (py3-friendly)
        KeysArray = c_ubyte * 32
        keys = KeysArray()
        # call XQueryKeymap with pointer to our array
        try:
            self.lib.XQueryKeymap(self.display, ctypes.cast(keys, c_char_p))
        except Exception:
            # fallback to create_string_buffer if casting fails
            buf = create_string_buffer(32)
            try:
                self.lib.XQueryKeymap(self.display, buf)
            except Exception:
                return set()
            # interpret buf as bytes
            pressed = set()
            for name, code in self.keycodes.items():
                byte_idx = code // 8
                bit_idx = code % 8
                if byte_idx < 32:
                    if (buf[byte_idx] & (1 << bit_idx)) != 0:
                        pressed.add(name)
            return pressed

        pressed = set()
        for name, code in self.keycodes.items():
            byte_idx = code // 8
            bit_idx = code % 8
            if byte_idx < 32:
                if (keys[byte_idx] & (1 << bit_idx)) != 0:
                    pressed.add(name)
        return pressed

# --- PygameInput & updated InputEngine ---
class PygameInput:
    """Tiny hidden pygame window that captures KEYDOWN/KEYUP reliably.
    Creates a 1x1 NOFRAME window, grabs keyboard, and re-grabs if focus is lost.
    Produces raw tokens (strings) like 'LEFT','RIGHT','SPACE','W', etc.
    """
    def __init__(self):
        self.active = False
        self._last_focus_check = 0.0
        self._focus_check_interval = 0.25
        self._held = set()
        try:
            # Import locally so pygame becomes optional
            import os as _os
            _os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "-100,-100")
            import pygame as _pygame
            self.pygame = _pygame
            _pygame.init()
            # Use NOFRAME so it's borderless; 1x1 so it's effectively invisible
            flags = _pygame.NOFRAME
            try:
                # attempt to create the window
                self.screen = _pygame.display.set_mode((1, 1), flags)
            except Exception:
                # fallback to normal tiny window if NOFRAME fails
                self.screen = _pygame.display.set_mode((1, 1))
            _pygame.display.set_caption("tf2-input-shim")
            # grab the input so keyboard events are routed to us even if cursor leaves
            try:
                _pygame.event.set_grab(True)
            except Exception:
                pass
            # hide mouse cursor so user doesn't see weirdness
            try:
                _pygame.mouse.set_visible(False)
            except Exception:
                pass

            # map pygame key constants -> raw tokens we use in InputEngine
            pg = _pygame
            self.map = {
                pg.K_LEFT: "LEFT", pg.K_RIGHT: "RIGHT", pg.K_UP: "UP", pg.K_DOWN: "DOWN",
                pg.K_SPACE: "SPACE", pg.K_RETURN: "CONTINUE", pg.K_KP_ENTER: "CONTINUE",
                pg.K_q: "Q", pg.K_r: "R", pg.K_m: "M",
                pg.K_w: "W", pg.K_a: "A", pg.K_s: "S", pg.K_d: "D", pg.K_z: "Z",
                pg.K_h: "H"
            }
            self.active = True
        except Exception:
            self.active = False

    def close(self):
        if not getattr(self, "active", False):
            return
        try:
            self.pygame.event.set_grab(False)
        except Exception:
            pass
        try:
            self.pygame.quit()
        except Exception:
            pass
        self.active = False

    def poll(self, timeout=0.0):
        """Return list of (raw_token, value) like evdev events. value:1=down,0=up"""
        if not self.active:
            return []
        evs = []
        pg = self.pygame

        try:
            for e in pg.event.get():
                if e.type == pg.QUIT:
                    continue
                if e.type == pg.KEYDOWN:
                    raw = self.map.get(e.key)
                    if raw:
                        if raw not in self._held:
                            self._held.add(raw)
                            evs.append((raw, 1))
                elif e.type == pg.KEYUP:
                    raw = self.map.get(e.key)
                    if raw and raw in self._held:
                        try:
                            self._held.remove(raw)
                        except Exception:
                            pass
                        evs.append((raw, 0))
                elif e.type == pg.ACTIVEEVENT:
                    pass
        except Exception:
            try:
                pg.event.pump()
            except Exception:
                pass

        now = time.time()
        if now - self._last_focus_check > self._focus_check_interval:
            self._last_focus_check = now
            try:
                focused = pg.key.get_focused()
                if not focused:
                    try:
                        pg.event.set_grab(True)
                    except Exception:
                        pass
                    try:
                        pg.display.flip()
                    except Exception:
                        pass
            except Exception:
                pass

        return evs

    def get_pressed_state(self):
        """Return set of raw tokens currently held (similar to X11.get_pressed)"""
        return set(self._held)


class InputEngine:
    def __init__(self, honor_env=True, hold_timeout=0.6):
        self.keys = {k: False for k in ['LEFT','RIGHT','UP','DOWN','JUMP','RESET','QUIT','CONTINUE','MENU']}
        self.pressed = set()
        self.ev_state = {k: False for k in self.keys}
        self._last_seen = {}
        self._hold_timeout = float(hold_timeout)

        # 1) wrapper (if provided)
        self.wrapper = None
        try:
            import evdev_input as evw
            self.wrapper = evw.EvdevInput()
        except Exception:
            self.wrapper = None

        # 2) native evdev
        self.native_fd_map = {}
        self.native_map = {}
        if not self.wrapper:
            try:
                from evdev import InputDevice, list_devices, ecodes
                devs = [InputDevice(p) for p in list_devices()]
                self.native_fd_map = {d.fd: d for d in devs if ecodes.EV_KEY in d.capabilities()}
                if self.native_fd_map:
                    self.native_map = {
                        ecodes.KEY_LEFT: 'LEFT', ecodes.KEY_RIGHT: 'RIGHT',
                        ecodes.KEY_UP: 'UP', ecodes.KEY_DOWN: 'DOWN',
                        ecodes.KEY_W: 'W', ecodes.KEY_A: 'A', ecodes.KEY_S: 'S', ecodes.KEY_D: 'D',
                        ecodes.KEY_Z: 'Z', ecodes.KEY_SPACE: 'SPACE',
                        ecodes.KEY_R: 'R', ecodes.KEY_Q: 'Q',
                        ecodes.KEY_H: 'H', ecodes.KEY_ENTER: 'CONTINUE',
                        ecodes.KEY_M: 'M'
                    }
            except Exception:
                self.native_fd_map = {}

        # 3) pygame shim (only if evdev not available)
        self.pygame_input = None
        if not self.wrapper and not self.native_fd_map:
            try:
                pgi = PygameInput()
                if pgi.active:
                    self.pygame_input = pgi
            except Exception:
                self.pygame_input = None

        # 4) X11 polling
        self.x11 = None
        self.x11_prev = set()
        if not self.wrapper and not self.native_fd_map and not self.pygame_input:
            try:
                self.x11 = X11Input()
            except Exception:
                self.x11 = None

        # 5) termios fallback
        self.term_mode = False
        self.stdin_fd = None
        self._term_saved = None
        if not self.wrapper and not self.native_fd_map and not self.pygame_input and not self.x11:
            try:
                import tty, termios
                self.stdin_fd = sys.stdin.fileno()
                self._term_saved = termios.tcgetattr(self.stdin_fd)
                tty.setcbreak(self.stdin_fd)
                self.term_mode = True
            except Exception:
                self.term_mode = False

        # mapping raw tokens -> in-game tokens
        self.token_map = {
            'LEFT':'LEFT','RIGHT':'RIGHT','UP':'JUMP','DOWN':'DOWN',
            'SPACE':'JUMP','ENTER':'CONTINUE','CONTINUE':'CONTINUE',
            'R':'RESET','Q':'QUIT','M':'MENU','A':'LEFT','D':'RIGHT',
            'W':'JUMP','S':'DOWN','Z':'JUMP','H':'LEFT'
        }

        # debug print which backend we are using
        try:
            if self.wrapper:
                print("InputEngine: using wrapper/evdev_input", file=sys.stderr)
            elif self.native_fd_map:
                print("InputEngine: using native evdev (/dev/input)", file=sys.stderr)
            elif self.pygame_input:
                print("InputEngine: using pygame input shim", file=sys.stderr)
            elif self.x11:
                print("InputEngine: using X11 polling (XQueryKeymap)", file=sys.stderr)
            elif self.term_mode:
                print("InputEngine: using termios fallback", file=sys.stderr)
            else:
                print("InputEngine: no usable input backend found", file=sys.stderr)
        except Exception:
            pass

    def _apply_event(self, raw_token, value):
        mapped = self.token_map.get(raw_token)
        if not mapped:
            return
        prev = bool(self.ev_state.get(mapped, False))
        if value == 1:
            if not prev:
                self.pressed.add(mapped)
            self.ev_state[mapped] = True
            self._last_seen[mapped] = time.time()
        else:
            self.ev_state[mapped] = False
            if mapped in self._last_seen:
                try: del self._last_seen[mapped]
                except: pass

    def update(self, stdscr):
        # Wrapper (evdev_input)
        if self.wrapper:
            try:
                evs = self.wrapper.poll(0.0)
            except Exception:
                evs = []
            for t, v in evs:
                v2 = 1 if v == 1 else 0
                self._apply_event(t, v2)

        # Native evdev
        elif self.native_fd_map:
            try:
                r, _, _ = select.select(list(self.native_fd_map.keys()), [], [], 0.0)
                for fd in r:
                    dev = self.native_fd_map.get(fd)
                    for ev in dev.read():
                        if ev.type == 1:
                            raw = self.native_map.get(ev.code)
                            if raw:
                                v2 = 1 if ev.value == 1 else 0
                                self._apply_event(raw, v2)
            except Exception:
                pass

        # Pygame shim
        elif self.pygame_input:
            try:
                evs = self.pygame_input.poll(0.0)
                for raw, v in evs:
                    self._apply_event(raw, v)
                # maintain current held state for continuous reads
                curr = self.pygame_input.get_pressed_state()
                for k in list(self.ev_state.keys()):
                    self.ev_state[k] = False
                for raw in curr:
                    mapped = self.token_map.get(raw)
                    if mapped:
                        self.ev_state[mapped] = True
                        self._last_seen[mapped] = time.time()
            except Exception:
                pass

        # X11 polling
        elif self.x11:
            try:
                curr = self.x11.get_pressed()
                for raw in (curr - self.x11_prev):
                    self._apply_event(raw, 1)
                for raw in (self.x11_prev - curr):
                    self._apply_event(raw, 0)
                self.x11_prev = curr
            except Exception:
                pass

        # Termios fallback
        elif self.term_mode:
            try:
                r, _, _ = select.select([self.stdin_fd], [], [], 0.0)
            except Exception:
                r = []
            if r:
                try:
                    data = os.read(self.stdin_fd, 512).decode(errors='ignore')
                except Exception:
                    data = ""
                i = 0
                while i < len(data):
                    ch = data[i]
                    raw = None
                    if ch == '\x1b':
                        seq = data[i:i+3]
                        if seq.startswith("\x1b[A"):
                            raw = "UP"; i += 3
                        elif seq.startswith("\x1b[B"):
                            raw = "DOWN"; i += 3
                        elif seq.startswith("\x1b[C"):
                            raw = "RIGHT"; i += 3
                        elif seq.startswith("\x1b[D"):
                            raw = "LEFT"; i += 3
                        else:
                            i += 1; continue
                    else:
                        if ch == ' ':
                            raw = 'SPACE'
                        elif ch in '\r\n':
                            raw = 'CONTINUE'
                        else:
                            uc = ch.upper()
                            if uc in ('A','D','W','S','Z','R','Q','M','H'):
                                raw = uc
                        i += 1
                    if raw:
                        self._apply_event(raw, 1)
            now = time.time()
            to_release = [k for k, ts in self._last_seen.items() if now - ts > self._hold_timeout]
            for k in to_release:
                raw_equiv = None
                for raw, mapped in self.token_map.items():
                    if mapped == k:
                        raw_equiv = raw; break
                if raw_equiv:
                    self._apply_event(raw_equiv, 0)

        # curses nav fallback
        curses_keys = {k: False for k in self.keys}
        try:
            while True:
                k = stdscr.getch()
                if k == -1:
                    break
                n = {
                    curses.KEY_LEFT: 'LEFT', curses.KEY_RIGHT: 'RIGHT',
                    ord(' '): 'JUMP', ord('r'): 'RESET', ord('R'): 'RESET',
                    ord('q'): 'QUIT', ord('Q'): 'QUIT', ord('m'): 'MENU',
                    ord('M'): 'MENU', 10: 'CONTINUE', 13: 'CONTINUE'
                }.get(k)
                if n:
                    curses_keys[n] = True
                    self._apply_event(n, 1)
        except Exception:
            pass

        # publish continuous keys[] (movement logic reads these)
        for k in self.keys:
            self.keys[k] = bool(self.ev_state.get(k, False)) or curses_keys.get(k, False)

    # API
    def was(self, k): return k in self.pressed
    def down(self, k): return bool(self.keys.get(k, False))
    def clear(self): self.pressed.clear()
    def reset(self):
        for kk in self.keys:
            self.keys[kk] = False
            self.ev_state[kk] = False
        self.pressed.clear()
        self._last_seen.clear()
        self.x11_prev.clear()

    def stop(self):
        # cleanup backends
        if hasattr(self, "wrapper") and self.wrapper:
            try: self.wrapper.close()
            except: pass
        if getattr(self, "pygame_input", None):
            try: self.pygame_input.close()
            except: pass
        if self.x11:
            try: self.x11.close()
            except: pass
        if self.term_mode and self._term_saved:
            try:
                import termios
                termios.tcsetattr(self.stdin_fd, termios.TCSANOW, self._term_saved)
            except Exception:
                pass

# --- PHYSICS OBJECTS ---
class Platform:
    def __init__(self, d, start_t=0.0):
        self.ox, self.oy, self.w = d['x'], d['y'], d['w']
        self.lx = d.get('lx', 0)
        self.ly = d.get('ly', 0)
        self.spd = d.get('spd', 1.0)
        self.ease = d.get('ease', 'SINE')
        self.x, self.y, self.t = self.ox, self.oy, start_t
        self.update(0)

    def update(self, dt):
        self.t += dt * self.spd
        if self.ease == 'SINE':
            off = math.sin(self.t)
        else:
            norm = (self.t / math.pi) % 2
            off = norm - 1 if norm > 1 else 1 - norm
        self.x = self.ox + (off * (self.lx / 2))
        self.y = self.oy + (off * (self.ly / 2))

    def rect(self):
        return (self.x, self.y, self.x + self.w, self.y + 1)

# --- LEVEL MANAGEMENT ---
def load_level(path, platform_timers=None):
    if not os.path.exists(path):
        return None, [], "UNKNOWN", {}
    with open(path) as f:
        parts = f.read().split("__METADATA__")
    lines = [l.rstrip("\r\n") for l in parts[0].strip().split('\n') if l != ""]
    w = max(len(l) for l in lines) if lines else 0
    grid = [list(l.ljust(w, ' ')) for l in lines]
    plats = []
    title = os.path.splitext(os.path.basename(path))[0]
    meta = {}
    if len(parts) > 1:
        try:
            d = json.loads(parts[1])
            if isinstance(d, dict):
                meta = d
                title = str(d.get("title", title)).replace('"', '')
                pdata = d.get("platforms", [])
                for i, p in enumerate(pdata):
                    t_start = platform_timers[i] if platform_timers and i < len(platform_timers) else 0.0
                    mp = Platform(p, t_start)
                    plats.append(mp)
                    for j in range(p['w']):
                        gy, gx = int(p['y']), int(p['x']) + j
                        if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]):
                            grid[gy][gx] = ' '
        except:
            pass
    return grid, plats, title, meta

def is_solid(grid, x, y):
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        ch = grid[int(y)][int(x)]
        if ch in ('C', 'S', 'G', ' '):
            return False
        p = get_plugin(ch)
        if p and 'runtime' in p:
            s = p['runtime'].get('solid')
            if callable(s):
                return bool(s(grid, x, y))
            return bool(s)
        return ch == TILES['SOLID']
    return True

def check_rect(grid, l, t, r, b):
    for y in range(int(math.floor(t)), int(math.floor(b)) + 1):
        for x in range(int(math.floor(l)), int(math.floor(r)) + 1):
            if is_solid(grid, x, y):
                return True
    return False

def check_plat(plats, l, t, r, b):
    for p in plats:
        pl, pt, pr, pb = p.rect()
        if l < pr and r > pl and t < pb and b > pt:
            return p
    return None

def resolve_char(grid, plats, cx, cy, title, default):
    p = get_plugin(default)
    if p:
        rt, ed = p.get('runtime', {}), p.get('editor', {})
        if callable(rt.get('get_display_char')):
            try:
                return rt['get_display_char'](grid, plats, cx, cy, title) or default
            except:
                pass
        return ed.get('display_char') or rt.get('display_char') or default
    return default

# --- RENDERER ---
def draw_scene(stdscr, grid, plats, px, py, cx, cy, fps, msg, time_val, lnum, ltitle, vis=True):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    gh, gw = len(grid), len(grid[0]) if grid else 0
    ox = (w - gw) // 2 if gw < w else 0
    oy = (h - gh) // 2 if gh < h else 0
    sx = int(max(0, min(cx, max(0, gw - w)))) if gw >= w else 0
    sy = int(max(0, min(cy, max(0, gh - h)))) if gh >= h else 0

    # Draw Grid
    for scr_y in range(h):
        my = scr_y - oy + sy
        if 0 <= my < gh:
            row = grid[my]
            sl = min(sx + w, len(row))
            if sx < sl:
                ln = "".join([str(resolve_char(grid, plats, x, my, ltitle, row[x])) for x in range(sx, sl)])
                try:
                    stdscr.addstr(scr_y, max(0, ox), ln)
                except:
                    pass

    # Draw Platforms
    for p in plats:
        spx, spy = int(p.x - sx) + ox, int(p.y - sy) + oy
        if 0 <= spy < h:
            dl = min(w - spx, p.w + (spx if spx < 0 else 0))
            if dl > 0:
                try:
                    stdscr.addstr(spy, max(0, spx), TILES['SOLID'] * int(dl), curses.A_BOLD)
                except:
                    pass

    # Draw Player
    spx, spy = int(px - sx) + ox, int(py - sy) + oy
    if vis and 0 <= spx < w and 0 <= spy < h:
        try:
            stdscr.addch(spy, spx, TILES['PLAYER'], curses.A_BOLD)
        except:
            pass

    # HUD
    try:
        t_str = f"SPEEDRUN" if SPEEDRUN_MODE else f"LEVEL {lnum}"
        if not msg:
            stdscr.addstr(0, 0, f"{t_str} \"{ltitle}\"", curses.A_BOLD)
        else:
            stdscr.addstr(0, 1, msg, curses.A_REVERSE | curses.A_BOLD)
        t_txt = f"TIME: {time_val:.2f}s"
        stdscr.addstr(0, max(0, w - len(t_txt) - 1), t_txt, curses.A_BOLD)
    except:
        pass
    stdscr.refresh()

# --- MENUS / UI (unchanged aside from minor tidy) ---
def draw_centered_menu(stdscr, title, opts, selected_idx):
    h, w = stdscr.getmaxyx()
    box_w = max(40, min(60, max(len(title) + 4, max((len(o) + 6) for o in opts))))
    box_h = len(opts) + 4
    bx = (w - box_w) // 2
    by = (h - box_h) // 2
    try:
        for y in range(by, by + box_h):
            stdscr.addstr(y, bx, " " * box_w)
        stdscr.attron(curses.A_BOLD | curses.A_UNDERLINE)
        stdscr.addstr(by, bx + 2, title)
        stdscr.attroff(curses.A_BOLD | curses.A_UNDERLINE)
        for i, it in enumerate(opts):
            txt = f"> {it} <" if i == selected_idx else f"   {it}   "
            attr = curses.A_REVERSE if i == selected_idx else curses.A_NORMAL
            stdscr.addstr(by + 2 + i, bx + 2, txt, attr)
        stdscr.addstr(by + box_h - 1, bx + 2, "UP/DOWN: Navigate  ENTER: Select  M: Close", curses.A_DIM)
        stdscr.refresh()
    except:
        pass

def show_in_game_menu(stdscr, allow_save=True):
    opts = ["Resume"]
    if allow_save:
        opts.extend(["Save & Quit to Menu", "Save Position (Slot)", "Clear Slot Data"])
    quit_txt = "Quit (Progress Lost)" if SPEEDRUN_MODE else "Quit to Menu (No Save)"
    opts.extend([quit_txt, "Cancel"])
    idx = 0
    stdscr.nodelay(False)
    while True:
        draw_centered_menu(stdscr, "PAUSE MENU", opts, idx)
        k = stdscr.getch()
        if k == curses.KEY_UP:
            idx = (idx - 1) % len(opts)
        elif k == curses.KEY_DOWN:
            idx = (idx + 1) % len(opts)
        elif k in (10, 13):
            sel = opts[idx]
            stdscr.nodelay(True)
            if sel == "Resume": return "RESUME"
            if sel == "Save & Quit to Menu": return "SAVE_QUIT"
            if sel == quit_txt: return "QUIT_NO_SAVE"
            if sel == "Save Position (Slot)": return "SAVE_ONLY"
            if sel == "Clear Slot Data": return "CLEAR_SLOT"
            return "CANCEL"
        elif k in (ord('m'), ord('M'), ord('q'), ord('Q')):
            stdscr.nodelay(True)
            return "RESUME"

def arcade_name_entry(stdscr, total_time):
    stdscr.nodelay(False)
    name = ""
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        cy, cx = h // 2, w // 2
        title = "★ CONGRATULATIONS! ★"
        stdscr.addstr(cy - 5, cx - len(title) // 2, title, curses.A_BOLD)
        time_str = f"FINAL TIME: {total_time:.2f}s"
        stdscr.addstr(cy - 3, cx - len(time_str) // 2, time_str)
        prompt = "ENTER INITIALS:"
        stdscr.addstr(cy - 1, cx - len(prompt) // 2, prompt, curses.A_UNDERLINE)
        field_disp = f" {name} " + ("█" if (int(time.time() * 2) % 2) == 0 else " ")
        stdscr.addstr(cy + 1, cx - len(field_disp) // 2, field_disp, curses.A_REVERSE)
        stdscr.addstr(cy + 3, cx - 13, "TYPE NAME - ENTER TO SUBMIT", curses.A_DIM)
        stdscr.refresh()
        k = stdscr.getch()
        if k in (10, 13):
            return name if len(name) > 0 else "AAA"
        elif k in (curses.KEY_BACKSPACE, 127, 8):
            name = name[:-1]
        elif 32 <= k <= 126 and len(name) < 10:
            name += chr(k).upper()

# --- MAIN GAME LOGIC (unchanged aside from using improved input) ---
def play_level(stdscr, level_file, inp, level_num, t_offset=0.0, resume_state=None, allow_save=True):
    global SAVE_SLOT_PATH
    p_timers = []
    plugin_data = {}
    if resume_state:
         p_timers = resume_state.get("platform_timers", [])
         plugin_data = resume_state.get("plugin_state", {})
    grid, plats, title, meta = load_level(level_file, p_timers)
    if not grid:
        return "NO_FILE", 0.0

    px, py = 1.5, 1.5
    start_cp = None
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == TILES['SPAWN']:
                px, py = x + 0.5, y + 0.5
                start_cp = (x + 0.5, y + 0.5)
                grid[y][x] = ' '
    if start_cp is None:
        start_cp = (px, py)
    vx, vy = 0.0, 0.0
    cp = start_cp
    if resume_state:
        try:
            saved_f = resume_state.get("level_file", "")
            if saved_f and (os.path.basename(saved_f) == os.path.basename(level_file)):
                r_px, r_py = float(resume_state.get("px", -1)), float(resume_state.get("py", -1))
                if r_px > 0 and r_py > 0:
                    px, py = r_px, r_py
                    vx = float(resume_state.get("vx", 0.0))
                    vy = float(resume_state.get("vy", 0.0))
                    if "cp" in resume_state:
                        cp = tuple(resume_state["cp"])
        except:
            pass

    cx, cy = 0, 0
    fps_h = deque(maxlen=30)
    start = time.time()
    last = time.time()
    cur_t = 0.0
    msg = None
    mend = 0
    ap = None
    ap_off = 0.0
    stdscr.nodelay(True)

    def make_game_state():
        return {"grid": grid, "platforms": plats, "level": title, "meta": meta}

    while True:
        inp.update(stdscr)

        # Pause Handling
        if inp.was('MENU') or inp.was('QUIT'):
            draw_scene(stdscr, grid, plats, px, py, cx, cy, 0, "PAUSED (M:MENU)", t_offset + cur_t, level_num, title)
            choice = show_in_game_menu(stdscr, allow_save=allow_save)
            if choice in ("RESUME", "CANCEL"):
                inp.clear()
                last = time.time()
            elif choice == "SAVE_ONLY":
                if SAVE_SLOT_PATH:
                    save = {
                        "level_file": os.path.abspath(level_file), "level_num": level_num,
                        "px": px, "py": py, "vx": vx, "vy": vy, "cp": cp,
                        "tot_time": t_offset + cur_t,
                        "platform_timers": [p.t for p in plats], "plugin_state": plugin_data
                    }
                    save_game_state_to(SAVE_SLOT_PATH, save)
                    msg = "SAVED"
                    mend = time.time() + 1.5
                else:
                    msg = "NO SLOT"
                    mend = time.time() + 1.5
                inp.clear()
                last = time.time()
            elif choice == "CLEAR_SLOT":
                if SAVE_SLOT_PATH:
                    clear_slot(SAVE_SLOT_PATH)
                    msg = "SLOT CLEARED"
                    mend = time.time() + 1.5
                else:
                    msg = "NO SLOT"
                    mend = time.time() + 1.5
                inp.clear()
                last = time.time()
            elif choice == "SAVE_QUIT":
                if SAVE_SLOT_PATH:
                    save = {
                        "level_file": os.path.abspath(level_file), "level_num": level_num,
                        "px": px, "py": py, "vx": vx, "vy": vy, "cp": cp,
                        "tot_time": t_offset + cur_t,
                        "platform_timers": [p.t for p in plats], "plugin_state": plugin_data
                    }
                    save_game_state_to(SAVE_SLOT_PATH, save)
                return "QUIT", 0.0
            elif choice == "QUIT_NO_SAVE":
                return "QUIT", 0.0

        # Time Step
        now = time.time()
        dt = min(now - last, 0.1)
        last = now
        dt = DT if dt < 0 else dt
        cur_t = now - start

        for p in plats:
            p.update(dt)

        if inp.was('RESET'):
            px, py, vx, vy, ap = cp[0], cp[1] - 0.1, 0, 0, None
            for m in PLUGINS:
                if callable(f := m.get('runtime', {}).get('on_player_death')):
                    try: f(make_game_state(), plugin_data)
                    except: pass

        ground = check_rect(grid, px - PHYS['HW'], py + PHYS['HH'], px + PHYS['HW'], py + PHYS['HH'] + 0.05)
        idir = (inp.down('RIGHT') - inp.down('LEFT'))

        # Platform Attachment Logic
        if ap:
            if inp.was('JUMP'):
                vy = JUMP_V
                px = ap.x + ap_off
                ap = None
            else:
                rem, cur = dt, ap_off
                while rem > 0:
                    step = min(rem, MAX_SUBSTEP)
                    rem -= step
                    nxt = cur + (idir * MOVE_SPEED) * step
                    wx, wy = ap.x + nxt, ap.y - PHYS['HH'] - PHYS['TOL']
                    if check_rect(grid, wx - PHYS['HW'], wy - PHYS['HH'] + 0.1, wx + PHYS['HW'], wy + PHYS['HH'] - 0.1):
                        break
                    cur = nxt
                ap_off = cur
                px = ap.x + cur
                py = ap.y - PHYS['HH'] - PHYS['TOL']
                vy = 0
                if ap_off + PHYS['HW'] <= 0 or ap_off - PHYS['HW'] >= ap.w:
                    ap = None

                sy = int(py + PHYS['HH'] + 0.05)
                for lx in {int(px), int(px - PHYS['HW'] + 0.1), int(px + PHYS['HW'] - 0.1)}:
                    if 0 <= sy < len(grid) and 0 <= lx < len(grid[0]):
                        pmeta = get_plugin(grid[sy][lx])
                        if pmeta and callable(f := pmeta.get('runtime', {}).get('on_player_supported')):
                            try:
                                pstate = {"px": px, "py": py, "vx": vx, "vy": vy}
                                f({"dt": dt, "grid": grid, "level": title, "meta": meta}, pstate, lx, sy, plugin_data)
                                vx = float(pstate.get("vx", vx))
                                vy = float(pstate.get("vy", vy))
                            except: pass
        else:
            # Free Movement
            if inp.was('JUMP') and ground:
                vy = JUMP_V
            else:
                vy += GRAVITY * dt
            vx = idir * MOVE_SPEED

            # X Axis
            rem = dt
            while rem > 0:
                step = min(rem, MAX_SUBSTEP)
                rem -= step
                npx = px + vx * step
                if check_rect(grid, npx - PHYS['HW'], py - PHYS['HH'] + 0.01, npx + PHYS['HW'], py + PHYS['HH'] - 0.01):
                    vx = 0
                elif check_plat(plats, npx - PHYS['HW'], py - PHYS['HH'] + 0.1, npx + PHYS['HW'], py + PHYS['HH'] - 0.1):
                    vx = 0
                else:
                    px = npx

            # Y Axis
            rem = dt
            while rem > 0:
                step = min(rem, MAX_SUBSTEP)
                rem -= step
                npy = py + vy * step
                if check_rect(grid, px - PHYS['HW'], npy - PHYS['HH'], px + PHYS['HW'], npy + PHYS['HH']):
                    if vy > 0: # Landing
                        ly = int(math.floor(npy + PHYS['HH']))
                        py, vy = ly - PHYS['HH'] - 0.001, 0
                        for lx in {int(px), int(px - PHYS['HW'] + 0.01), int(px + PHYS['HW'] - 0.01)}:
                            if 0 <= ly < len(grid) and 0 <= lx < len(grid[0]):
                                pmeta = get_plugin(grid[ly][lx])
                                if pmeta and callable(f := pmeta.get('runtime', {}).get('on_player_supported')):
                                    try:
                                        pstate = {"px": px, "py": py, "vx": vx, "vy": vy}
                                        f({"dt": step, "grid": grid, "level": title, "meta": meta}, pstate, lx, ly, plugin_data)
                                        vx = float(pstate.get("vx", vx))
                                        vy = float(pstate.get("vy", vy))
                                    except: pass
                    elif vy < 0: # Hitting head
                        py, vy = math.floor(npy - PHYS['HH']) + PHYS['HH'] + 1.001, 0
                else:
                    hit = check_plat(plats, px - PHYS['HW'], npy - PHYS['HH'], px + PHYS['HW'], npy + PHYS['HH'])
                    if hit:
                        if vy > 0:
                            ap = hit
                            ap_off = px - hit.x
                            py = hit.y - PHYS['HH'] - PHYS['TOL']
                            vy = 0
                        elif vy < 0:
                            py, vy = hit.y + 1.0 + PHYS['HH'] + PHYS['TOL'], 0
                    else:
                        py = npy

        # Interaction & Collision
        icx, icy = int(px), int(py)
        crush = is_solid(grid, px, py)
        dist_to_cp = math.sqrt((px - cp[0])**2 + (py - cp[1])**2)
        is_safe = (dist_to_cp < 1.0)
        tile = grid[icy][icx] if (0 <= icy < len(grid) and 0 <= icx < len(grid[0])) else ' '

        if tile == TILES['GOAL']:
            return "NEXT_LEVEL", cur_t

        tp = get_plugin(tile)
        if tp and 'runtime' in tp:
            touch = tp['runtime'].get('on_player_touch')
            if callable(touch):
                try:
                    pstate = {"px": px, "py": py, "vx": vx, "vy": vy}
                    ret = touch({"grid":grid, "platforms":plats, "player":{"px":px,"py":py,"vx":vx,"vy":vy}, "level":title, "meta":meta}, pstate, icx, icy, plugin_data)
                    vx = float(pstate.get("vx", vx))
                    vy = float(pstate.get("vy", vy))
                    if isinstance(ret, dict):
                        if "vx" in ret: vx = float(ret["vx"])
                        if "vy" in ret: vy = float(ret["vy"])
                except: pass

        tp = get_plugin(tile)
        deadly = bool(tp['runtime'].get('deadly', False)) if tp and 'runtime' in tp else False
        if tp and 'runtime' in tp and callable(f := tp['runtime'].get('on_player_collide')):
             try: f({"grid":grid, "platforms":plats, "player":{"px":px,"py":py,"vx":vx,"vy":vy}, "level":title, "meta":meta}, {"px":px,"py":py,"vx":vx,"vy":vy}, icx, icy, plugin_data)
             except: pass

        should_die, reason = False, ""
        if crush and not is_safe: should_die, reason = True, "CRUSH"
        if tile in (TILES['SPIKE'], TILES['SPIKE_DN']): should_die, reason = True, "SPIKE"
        if deadly: should_die, reason = True, f"PLUGIN [{tile}]"

        if should_die:
            for i in range(10):
                draw_scene(stdscr, grid, plats, px, py, int(cx), int(cy), 60, f"DEAD! ({reason})", cur_t, level_num, title, i % 2 != 0)
                time.sleep(0.05)
            inp.reset()
            curses.flushinp()
            for m in PLUGINS:
                if callable(f := m.get('runtime', {}).get('on_player_death')):
                    try: f({"grid":grid, "level":title, "meta":meta}, plugin_data)
                    except: pass
            px, py, vx, vy, ap = cp[0], cp[1] - 0.1, 0, 0, None

        elif tile == TILES['CP']:
            if (icx + 0.5, icy + 0.5) != cp:
                cp = (icx + 0.5, icy + 0.5)
                msg = "CHECKPOINT"
                mend = time.time() + 1.5

        # Camera
        h, w = stdscr.getmaxyx()
        cx += (int(px) - w // 2 - cx) * 0.1
        cy += (int(py) - h // 2 - cy) * 0.1

        # Draw
        fps_h.append(1.0 / dt if dt > 0 else 60)
        if time.time() > mend: msg = None
        inp.clear()

        rpy = (float(int(ap.y)) - 0.5) if ap else py
        draw_scene(stdscr, grid, plats, px, rpy, int(cx), int(cy), sum(fps_h) / len(fps_h), msg, t_offset + cur_t, level_num, title)
        time.sleep(0.005)

# --- ENTRY POINT ---
def main(stdscr):
    global SAVE_SLOT_PATH, RESUME_FLAG, SPEEDRUN_MODE
    locale.setlocale(locale.LC_ALL, '')
    curses.curs_set(0)
    hold_timeout = 0.6
    inp = None
    mode, path, tot_t, lvl = "CAMP", "", 0.0, 1
    resume_state = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--slot" and i + 1 < len(args):
            SAVE_SLOT_PATH = args[i + 1]; i += 2
        elif a == "--resume":
            RESUME_FLAG = True; i += 1
        elif a == "--speedrun":
            SPEEDRUN_MODE = True; i += 1
        elif a == "--hold-timeout" and i + 1 < len(args):
            try: hold_timeout = float(args[i+1])
            except: hold_timeout = 0.6
            i += 2
        else:
            mode, path = "SNGL", a
            i += 1

    if RESUME_FLAG and SAVE_SLOT_PATH:
        resume_state = load_saved_game_from(SAVE_SLOT_PATH)
        if resume_state:
            saved_lvl = int(resume_state.get("level_num", 1))
            check_path = os.path.join(DIRS['CAMP'], f"level{saved_lvl}.txt")
            if resume_state.get("completed", False) or not os.path.exists(check_path):
                resume_state = None
                lvl = 1
                tot_t = 0.0
            else:
                lvl = saved_lvl
                if "tot_time" in resume_state:
                    tot_t = float(resume_state["tot_time"])

    try:
        inp = InputEngine(honor_env=True, hold_timeout=hold_timeout)
        while True:
            if mode == "CAMP":
                if resume_state and "level_file" in resume_state:
                    fpath = resume_state["level_file"]
                else:
                    fpath = os.path.join(DIRS['CAMP'], f"level{lvl}.txt")
            else:
                fpath = path if os.path.exists(path) else os.path.join(DIRS['LEVELS'], path)

            if not os.path.exists(fpath):
                if mode == "CAMP" and lvl > 1:
                    if SAVE_SLOT_PATH:
                        if SPEEDRUN_MODE:
                            clear_slot(SAVE_SLOT_PATH)
                        else:
                            save_game_state_to(SAVE_SLOT_PATH, {"level_num": 1, "completed": True})
                    if SPEEDRUN_MODE:
                        player_name = arcade_name_entry(stdscr, tot_t)
                        save_score("speedrun_camp", tot_t, player_name)
                    else:
                        save_score("campaign", tot_t, "Player")
                    stdscr.erase()
                    stdscr.addstr(curses.LINES // 2, (curses.COLS - 20) // 2, f"DONE! TIME: {tot_t:.2f}s", curses.A_BOLD)
                    stdscr.refresh()
                    time.sleep(3)
                elif mode == "CAMP":
                    stdscr.addstr(0, 0, "Error: No Campaign Levels found in 'campaignlevels/'")
                    stdscr.refresh()
                    time.sleep(2)
                return

            can_save_in_menu = (mode == "CAMP" and not SPEEDRUN_MODE)
            res, el = play_level(stdscr, fpath, inp, lvl, tot_t, resume_state=resume_state, allow_save=can_save_in_menu)
            resume_state = None
            if res == "QUIT":
                return
            if res == "NEXT_LEVEL":
                stdscr.erase()
                stdscr.addstr(curses.LINES // 2, (curses.COLS - 20) // 2, "LEVEL COMPLETE!", curses.A_BOLD)
                stdscr.refresh()
                time.sleep(0.6)
                tot_t += el
                lvl += 1
    except KeyboardInterrupt:
        pass
    finally:
        if inp:
            inp.stop()

if __name__ == "__main__":
    curses.wrapper(main)

