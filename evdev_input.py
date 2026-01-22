#!/usr/bin/env python3
"""
evdev_input.py
Small wrapper around python-evdev to provide key down / key up events.
- Finds all devices that advertise EV_KEY
- Polls them with select() to avoid blocking
- Returns events as tuples: (token, value) where value is 1=down, 0=up, 2=hold
Tokens are strings like: 'LEFT','RIGHT','UP','DOWN','Z','SPACE','R','Q','A','D'
"""

from evdev import InputDevice, list_devices, ecodes
import select
import os

# mapping evdev keycodes to tokens used by the game
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
}

class EvdevInput:
    def __init__(self, device_paths=None):
        """
        device_paths: optional list of /dev/input/eventX paths to open.
                      If None, we auto-discover devices with EV_KEY capability.
        """
        self.devices = []
        if device_paths:
            for p in device_paths:
                try:
                    self.devices.append(InputDevice(p))
                except Exception:
                    pass
        else:
            for dev_path in list_devices():
                try:
                    d = InputDevice(dev_path)
                    caps = d.capabilities()
                    # We look for EV_KEY capability in capabilities dict
                    if ecodes.EV_KEY in caps:
                        self.devices.append(d)
                except Exception:
                    # ignore devices we can't open
                    pass

        # map fd -> device for select
        self.fd_map = {d.fd: d for d in self.devices}

        # option: if you want exclusive capture uncomment the grab() below (requires permissions)
        # for d in self.devices:
        #     try:
        #         d.grab()
        #     except Exception:
        #         pass

    def poll(self, timeout=0.0):
        """
        Poll devices and return list of (token, value) events.
        value: 1 = key down, 0 = key up, 2 = hold.
        """
        if not self.fd_map:
            return []

        r, _, _ = select.select(list(self.fd_map.keys()), [], [], timeout)
        events = []
        for fd in r:
            dev = self.fd_map[fd]
            try:
                for ev in dev.read():
                    if ev.type == ecodes.EV_KEY:
                        token = _ECODE_TO_TOKEN.get(ev.code)
                        if token:
                            events.append((token, ev.value))
            except BlockingIOError:
                continue
            except Exception:
                # device might have been removed - ignore
                continue
        return events

    def close(self):
        for d in self.devices:
            try:
                d.close()
            except Exception:
                pass
