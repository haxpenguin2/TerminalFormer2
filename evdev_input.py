class InputEngine:
    def __init__(self, honor_env=True, hold_timeout=0.6):
        self.keys = {k: False for k in ['LEFT','RIGHT','UP','DOWN','JUMP','RESET','QUIT','CONTINUE','MENU']}
        self.pressed = set()
        self.ev_state = {k: False for k in self.keys}
        self._last_seen = {}
        self._hold_timeout = float(hold_timeout)

        env = os.environ.get("TF2_PREFER_EVDEV")
        self.prefer_evdev = True if env is None else (env == "1") if honor_env else True

        # try wrapper first
        self.wrapper = None
        try:
            import evdev_input as evw
            self.wrapper = evw.EvdevInput()
        except Exception:
            self.wrapper = None

        # native evdev if wrapper not present
        self.native_fd_map = {}
        self.native_map = {}
        if self.wrapper is None and self.prefer_evdev:
            try:
                from evdev import InputDevice, list_devices, ecodes
                CODE_TO_TOKEN = {
                    ecodes.KEY_LEFT:'LEFT', ecodes.KEY_RIGHT:'RIGHT',
                    ecodes.KEY_UP:'UP', ecodes.KEY_DOWN:'DOWN',
                    ecodes.KEY_Z:'Z', ecodes.KEY_SPACE:'SPACE',
                    ecodes.KEY_R:'R', ecodes.KEY_Q:'Q',
                    ecodes.KEY_A:'A', ecodes.KEY_D:'D', ecodes.KEY_H:'H',
                    ecodes.KEY_ENTER:'CONTINUE', getattr(ecodes,'KEY_M',None):'M'
                }
                CODE_TO_TOKEN = {k:v for k,v in CODE_TO_TOKEN.items() if k is not None}
                devs=[]
                for p in list_devices():
                    try:
                        d = InputDevice(p)
                        caps=d.capabilities()
                        if hasattr(caps,'__contains__') and ecodes.EV_KEY in caps:
                            devs.append(d)
                    except Exception:
                        pass
                self.native_fd_map = {d.fd:d for d in devs}
                self.native_map = CODE_TO_TOKEN
            except Exception:
                self.native_fd_map = {}; self.native_map = {}

        # termios fallback
        self.term_mode = False; self.stdin_fd = None; self._term_saved = None
        if not self.wrapper and not self.native_fd_map:
            try:
                import tty, termios
                self.stdin_fd = None
                # Termios driver uses evdev_input.TermiosInput via import when game asks wrapper — but keep flag here
                self.term_mode = True
            except Exception:
                self.term_mode = False

        # canonical token map
        self.token_map = {'LEFT':'LEFT','RIGHT':'RIGHT','UP':'JUMP','DOWN':'DOWN',
                          'SPACE':'JUMP','ENTER':'CONTINUE','CONTINUE':'CONTINUE',
                          'R':'RESET','Q':'QUIT','M':'MENU','A':'LEFT','D':'RIGHT','Z':'JUMP','H':'LEFT'}

    def _poll_native(self, timeout=0.0):
        if not self.native_fd_map: return []
        try:
            r,_,_ = select.select(list(self.native_fd_map.keys()), [], [], timeout)
        except Exception:
            return []
        out=[]
        for fd in r:
            d=self.native_fd_map.get(fd)
            if not d: continue
            try:
                for ev in d.read():
                    if ev.type == 1:
                        token=self.native_map.get(ev.code)
                        if token: out.append((token,int(ev.value)))
            except (BlockingIOError, InterruptedError):
                continue
            except Exception:
                continue
        return out

    def _poll_wrapper(self, timeout=0.0):
        try:
            if self.wrapper: return self.wrapper.poll(timeout)
        except Exception:
            pass
        return []

    def _poll_term(self, timeout=0.0):
        # call into wrapper's TermiosInput if it's present, else nothing
        try:
            import evdev_input
            # evdev_input.open_input will pick termios or evdev depending on env; but we already tried wrapper earlier.
            # If there's no wrapper object, create a temporary TermiosInput and poll it.
            if hasattr(evdev_input, "TermiosInput"):
                t = evdev_input.TermiosInput()
                evs = t.poll(timeout)
                t.close()
                return evs
        except Exception:
            pass
        return []

    def update(self, stdscr):
        evs=[]
        if self.wrapper:
            evs += self._poll_wrapper(0.0)
        elif self.native_fd_map:
            evs += self._poll_native(0.0)
        elif self.term_mode:
            evs += self._poll_term(0.0)

        now = time.time()
        for t,v in evs:
            mapped = self.token_map.get(t) or self.token_map.get(str(t).upper())
            if not mapped: continue
            if v == 1:
                self.pressed.add(mapped); self.ev_state[mapped] = True; self._last_seen[mapped] = now
            elif v == 0:
                self.ev_state[mapped] = False
                if mapped in self._last_seen: del self._last_seen[mapped]
            elif v == 2:
                self.pressed.add(mapped); self.ev_state[mapped] = True; self._last_seen[mapped] = now

        # For termios fallback: synthesize per-frame pressed events for held keys so was('JUMP') fires every frame
        if self.term_mode or (self.wrapper is None and not self.native_fd_map):
            for k,held in list(self.ev_state.items()):
                if held:
                    self.pressed.add(k)
                    self._last_seen[k] = now

        # decay holds when we haven't seen a press (only for term-style input)
        if self.term_mode:
            cutoff = now - self._hold_timeout
            stale = [k for k,t in self._last_seen.items() if t < cutoff]
            for k in stale:
                self.ev_state[k] = False
                del self._last_seen[k]

        # always consume curses getch to allow menu keys to work
        curses_keys = {k: False for k in self.keys}
        try:
            while True:
                k = stdscr.getch()
                if k == -1: break
                n = {curses.KEY_LEFT:'LEFT', curses.KEY_RIGHT:'RIGHT', ord(' '):'JUMP',
                     ord('r'):'RESET', ord('R'):'RESET', ord('q'):'QUIT', ord('Q'):'QUIT',
                     ord('m'):'MENU', ord('M'):'MENU', ord('\n'):'CONTINUE', 10:'CONTINUE', 13:'CONTINUE'}.get(k)
                if n:
                    curses_keys[n] = True
                    self.pressed.add(n)
                    if n == 'JUMP':
                        curses_keys['CONTINUE'] = True; self.pressed.add('CONTINUE')
        except Exception:
            pass

        # finalize combined state
        for k in self.keys:
            self.keys[k] = self.ev_state.get(k, False) or curses_keys.get(k, False)

    def was(self,k): return k in self.pressed
    def down(self,k): return bool(self.keys.get(k, False))
    def clear(self): self.pressed.clear()
    def reset(self):
        for kk in self.keys: self.keys[kk]=False; self.ev_state[kk]=False
        self.pressed.clear(); self._last_seen.clear()
    def stop(self):
        try:
            if self.wrapper:
                try: self.wrapper.close()
                except: pass
            if getattr(self, "native_fd_map", None):
                for d in list(self.native_fd_map.values()):
                    try: d.close()
                    except: pass
        except Exception:
            pass
        # termios cleanup handled by TermiosInput.close() if used via wrapper
