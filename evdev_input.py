#!/usr/bin/env python3
"""
evdev_input.py - Low-latency input wrapper.
Strategies:
1. Evdev: Direct kernel access (Best, requires root/group permissions).
2. X11: Direct X server polling (Best for Crostini/Desktop Linux, no root needed).
3. Termios: Stdin fallback (Universal, but suffers from OS repeat delay).
"""
import select, os, sys, time, ctypes
from ctypes import cdll, create_string_buffer

# ---------------- 1. Evdev Driver (Native Linux) ----------------
_HAVE_EVDEV = True
try:
    from evdev import InputDevice, list_devices, ecodes
except Exception:
    _HAVE_EVDEV = False

_EVDEV_MAPPING = {}
if _HAVE_EVDEV:
    _EVDEV_MAPPING = {
        ecodes.KEY_LEFT: 'LEFT',   ecodes.KEY_RIGHT: 'RIGHT',
        ecodes.KEY_UP: 'UP',       ecodes.KEY_DOWN: 'DOWN',
        ecodes.KEY_W: 'UP',        ecodes.KEY_A: 'LEFT',
        ecodes.KEY_S: 'DOWN',      ecodes.KEY_D: 'RIGHT',
        ecodes.KEY_Z: 'Z',         ecodes.KEY_SPACE: 'SPACE',
        ecodes.KEY_ENTER: 'ENTER', ecodes.KEY_Q: 'Q',
    }

class EvdevInput:
    def __init__(self, device_paths=None):
        self.devices = []
        self.fd_map = {}
        # Auto-discovery logic
        paths = device_paths if device_paths else list_devices()
        for p in paths:
            try:
                d = InputDevice(p)
                caps = d.capabilities()
                if hasattr(caps, '__contains__') and ecodes.EV_KEY in caps:
                    self.devices.append(d)
            except Exception: pass
        self.fd_map = {d.fd: d for d in self.devices}

    def poll(self, timeout=0.0):
        if not self.fd_map: return []
        events = []
        try:
            r, _, _ = select.select(list(self.fd_map.keys()), [], [], timeout)
            for fd in r:
                dev = self.fd_map.get(fd)
                for ev in dev.read():
                    if ev.type == ecodes.EV_KEY:
                        token = _EVDEV_MAPPING.get(ev.code)
                        if token and ev.value < 2: # 0=Up, 1=Down, 2=Repeat (ignore 2)
                            events.append((token, int(ev.value)))
        except Exception: return []
        return events

    def close(self):
        for d in self.devices:
            try: d.close()
            except: pass

# ---------------- 2. X11 Driver (Crostini / Desktop) ----------------
# This uses ctypes to query the keyboard state directly from X11.
# It bypasses terminal processing and OS repeat delays.
class X11Input:
    def __init__(self):
        try:
            # Load X11 library (standard on almost all Linux/Crostini)
            self.x11 = cdll.LoadLibrary("libX11.so.6")
            # Open default display
            self.disp = self.x11.XOpenDisplay(None)
            if not self.disp: raise Exception("No X Display")
        except Exception as e:
            raise ImportError(f"X11 unavailable: {e}")

        self._last_state = set()
        
        # Hardcoded X11 Keycodes (Works on most Standard US Layouts)
        # Scan code + 8 = X11 Keycode usually.
        self.keymap = {
            111: 'UP',    116: 'DOWN',  113: 'LEFT',  114: 'RIGHT', # Arrows
            25:  'UP',    38:  'LEFT',  39:  'DOWN',  40:  'RIGHT', # WASD
            52:  'Z',     65:  'SPACE', 36:  'ENTER', 24:  'Q',
        }

    def poll(self, timeout=0.0):
        # Prepare a 32-byte buffer for the key vector
        keys_return = create_string_buffer(32)
        # Query the hardware state
        self.x11.XQueryKeymap(self.disp, keys_return)
        
        current_state = set()
        events = []
        
        # Check specific keys we care about
        for code, token in self.keymap.items():
            byte_index = code // 8
            bit_index = code % 8
            # Check if the bit is set
            is_down = (ord(keys_return[byte_index]) & (1 << bit_index)) != 0
            
            if is_down:
                current_state.add(token)

        # Generate events based on state changes
        # Key Down
        for token in current_state - self._last_state:
            events.append((token, 1))
        # Key Up
        for token in self._last_state - current_state:
            events.append((token, 0))
            
        self._last_state = current_state
        
        # Simulate wait if timeout requested (since XQuery is instant)
        if timeout > 0 and not events:
            time.sleep(timeout)
            
        return events

    def close(self):
        if hasattr(self, 'disp') and self.disp:
            self.x11.XCloseDisplay(self.disp)

# ---------------- 3. Termios Driver (Fallback) ----------------
class TermiosInput:
    def __init__(self):
        import tty, termios
        self._fd = sys.stdin.fileno()
        self._termios = termios
        self._old = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        
        self._buf = ""
        self._held_keys = {} # token -> timestamp
        # Timeout to consider a key released (approx 2-3 frames at 60fps)
        self._release_timeout = 0.05 
        
        self.maps = {
            "\x1b[A": "UP", "\x1b[B": "DOWN", "\x1b[C": "RIGHT", "\x1b[D": "LEFT",
            "w": "UP", "a": "LEFT", "s": "DOWN", "d": "RIGHT",
            " ":"SPACE", "\n":"ENTER", "z":"Z", "q":"Q"
        }

    def poll(self, timeout=0.0):
        # 1. Read all pending Input
        events = []
        cur_time = time.time()
        
        try:
            if select.select([sys.stdin], [], [], timeout)[0]:
                self._buf += os.read(self._fd, 1024).decode(errors="ignore")
        except: pass

        # 2. Parse Buffer
        while self._buf:
            matched = False
            for seq, token in self.maps.items():
                if self._buf.startswith(seq):
                    # logic: If key wasn't held, emit DOWN (1). Update timestamp.
                    if token not in self._held_keys:
                        events.append((token, 1))
                    self._held_keys[token] = cur_time
                    self._buf = self._buf[len(seq):]
                    matched = True
                    break
            if not matched:
                self._buf = self._buf[1:] # discard unknown

        # 3. Simulate Key Up events based on timeout
        # If we haven't seen the char in X seconds, assume user let go.
        # Note: This is imperfect. It can't bridge the initial OS delay gap (500ms),
        # but it handles rapid repeat well.
        released = []
        for token, ts in self._held_keys.items():
            if cur_time - ts > self._release_timeout:
                events.append((token, 0))
                released.append(token)
        
        for r in released:
            del self._held_keys[r]

        return events

    def close(self):
        try: self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._old)
        except: pass

# ---------------- Factory ----------------
def open_input():
    # Priority 1: Evdev (Hardware raw)
    if _HAVE_EVDEV:
        try:
            print("Input: Trying Evdev...", file=sys.stderr)
            drv = EvdevInput()
            if drv.devices: return drv
        except: pass

    # Priority 2: X11 Direct (Crostini / Desktop)
    try:
        # Check if DISPLAY env var is set (implies X11/Wayland presence)
        if os.environ.get("DISPLAY"):
            print("Input: Trying X11...", file=sys.stderr)
            return X11Input()
    except Exception as e:
        pass

    # Priority 3: Termios (Stdin fallback)
    print("Input: Fallback to Termios...", file=sys.stderr)
    return TermiosInput()

# ---------------- Test Code ----------------
if __name__ == "__main__":
    inp = open_input()
    print("Running... Press 'Q' to quit.")
    try:
        while True:
            evs = inp.poll(timeout=0.016) # ~60 FPS poll rate
            for t, v in evs:
                state = "DOWN" if v == 1 else "UP"
                print(f"Event: {t} {state}")
                if t == 'Q' and v == 1: raise KeyboardInterrupt
    except KeyboardInterrupt:
        pass
    finally:
        inp.close()
