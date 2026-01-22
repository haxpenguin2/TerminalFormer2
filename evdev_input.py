#!/usr/bin/env python3
"""
evdev_input.py - Wrapper for low-latency input
"""
from evdev import InputDevice, list_devices, ecodes
import select
import os

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
}

class EvdevInput:
    def __init__(self, device_paths=None):
        self.devices = []
        if device_paths:
            for p in device_paths:
                try: self.devices.append(InputDevice(p))
                except: pass
        else:
            for dev_path in list_devices():
                try:
                    d = InputDevice(dev_path)
                    if ecodes.EV_KEY in d.capabilities():
                        self.devices.append(d)
                except: pass

        self.fd_map = {d.fd: d for d in self.devices}

    def poll(self, timeout=0.0):
        if not self.fd_map: return []
        r, _, _ = select.select(list(self.fd_map.keys()), [], [], timeout)
        events = []
        for fd in r:
            dev = self.fd_map[fd]
            try:
                for ev in dev.read():
                    if ev.type == ecodes.EV_KEY:
                        token = _ECODE_TO_TOKEN.get(ev.code)
                        if token: events.append((token, ev.value))
            except: continue
        return events

    def close(self):
        for d in self.devices:
            try: d.close()
            except: pass
