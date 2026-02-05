#!/usr/bin/env python3
"""
evdev_input.py - Wrapper for low-latency input, with termios fallback for systems
where /dev/input is not available (eg. Chromebooks / Crostini).

API:
    d = EvdevInput(device_paths=None)  # prefer evdev if available, else termios fallback
    events = d.poll(timeout=0.0)       # returns list of (TOKEN, value)
    d.close()
"""
import select, os, sys, time

# Try to import evdev. If available, use it; otherwise we'll provide a termios fallback.
_HAVE_EVDEV = True
try:
    from evdev import InputDevice, list_devices, ecodes
except Exception:
    _HAVE_EVDEV = False

# mapping when evdev is present
_ECODE_TO_TOKEN = {}
if _HAVE_EVDEV:
    _ECODE_TO_TOKEN = {
        ecodes.KEY_LEFT: 'LEFT',
        ecodes.KEY_RIGHT: 'RIGHT',
        ecodes.KEY_UP: 'UP',
        ecodes.KEY_DOWN: 'DOWN',
        ecodes.KEY_Z: 'Z',
        ecodes.KEY_SPACE: 'SPACE',
        ecodes.KEY_R: 'R',
        ecodes.KEY_Q: 'Q',
        ecodes.KEY_A: 'A',
        ecodes.KEY_D: 'D',
        ecodes.KEY_H: 'H',
        ecodes.KEY_ENTER: 'CONTINUE',
        ecodes.KEY_KPENTER: 'CONTINUE',
        # Some keyboards expose KEY_LEFT/RIGHT as KEY_KP4/6 or other codes; add common ones here if needed.
    }

# ---------------- Evdev-backed input driver ----------------
if _HAVE_EVDEV:
    class EvdevInput:
        def __init__(self, device_paths=None):
            self.devices = []
            self.fd_map = {}
            if device_paths:
                for p in device_paths:
                    try:
                        d = InputDevice(p); self.devices.append(d)
                    except Exception:
                        pass
            else:
                for dev_path in list_devices():
                    try:
                        d = InputDevice(dev_path)
                        caps = d.capabilities()
                        if hasattr(caps, '__contains__') and ecodes.EV_KEY in caps:
                            self.devices.append(d)
                    except Exception:
                        pass
            self.fd_map = {d.fd: d for d in self.devices}

        def poll(self, timeout=0.0):
            if not self.fd_map: return []
            try:
                r, _, _ = select.select(list(self.fd_map.keys()), [], [], timeout)
            except Exception:
                return []
            events = []
            for fd in r:
                dev = self.fd_map.get(fd)
                if not dev: continue
                try:
                    for ev in dev.read():
                        # ev.type == ecodes.EV_KEY (integer 1)
                        if ev.type == ecodes.EV_KEY:
                            token = _ECODE_TO_TOKEN.get(ev.code)
                            if token:
                                # ev.value: 1=down, 0=up, 2=hold
                                events.append((token, int(ev.value)))
                except (BlockingIOError, InterruptedError):
                    continue
                except Exception:
                    continue
            return events

        def close(self):
            for d in self.devices:
                try: d.close()
                except: pass

# ---------------- Termios (stdin) fallback driver ----------------
class TermiosInput:
    def __init__(self):
        import tty, termios
        self._fd = sys.stdin.fileno()
        self._termios = termios
        self._old_attrs = termios.tcgetattr(self._fd)
        try:
            tty.setcbreak(self._fd)
        except Exception:
            pass
        self._buf = ""
        self._seq_map = {
            "\x1b[A": "UP", "\x1b[B": "DOWN", "\x1b[C": "RIGHT", "\x1b[D": "LEFT",
        }
        self._char_map = {
            "a":"A","A":"A","d":"D","D":"D","h":"H","H":"H","z":"Z","Z":"Z",
            " ":"SPACE","\r":"CONTINUE","\n":"CONTINUE","\x0d":"CONTINUE",
            "q":"Q","Q":"Q","m":"M","M":"M","r":"R","R":"R",
        }

    def _read_available(self):
        try:
            r,_,_ = select.select([sys.stdin], [], [], 0)
        except Exception:
            return ""
        if not r: return ""
        try:
            return os.read(self._fd, 32).decode("utf-8", errors="ignore")
        except Exception:
            try:
                return sys.stdin.read(1)
            except Exception:
                return ""

    def poll(self, timeout=0.0):
        events = []
        end = time.time() + float(timeout or 0.0)
        s = self._read_available()
        if s: self._buf += s
        while time.time() < end:
            s = self._read_available()
            if not s: break
            self._buf += s
        while self._buf:
            if self._buf.startswith("\x1b[") and len(self._buf) >= 3:
                seq = self._buf[:3]; token = self._seq_map.get(seq)
                if token:
                    events.append((token, 1)); self._buf = self._buf[3:]; continue
            ch = self._buf[0]; self._buf = self._buf[1:]
            token = self._char_map.get(ch)
            if token: events.append((token, 1))
        return events

    def close(self):
        try:
            self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._old_attrs)
        except Exception:
            pass

# ---------------- Helper factory ----------------
def open_input(prefer_evdev=True, device_paths=None):
    """
    Returns an input driver instance.
    prefer_evdev: if True, attempt to use evdev; if unavailable, fall back to termios.
    """
    if _HAVE_EVDEV and prefer_evdev:
        try:
            drv = EvdevInput(device_paths=device_paths)
            if getattr(drv, "devices", None):
                return drv
            # if no devices, fall back to termios
            return TermiosInput()
        except Exception:
            try: return TermiosInput()
            except Exception: raise
    else:
        return TermiosInput()

