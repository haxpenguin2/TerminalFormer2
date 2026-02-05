#!/usr/bin/env python3
# menu.py - Fixed High Scores (Shows all levels)
import curses, os, sys, json, subprocess, random, time, math, re

# --- CONFIG ---
DIRS = {"lvl": "levels", "cmp": "campaignlevels", "plg": "plugins", "sav": "saves"}
SCORES_FILE = "scores.json"
BG_SPD = (1, 0)
PLUGIN_VISUALS = {}

# --- CORE CLASSES & UTILS ---
class MovingPlatform:
    def __init__(self, d, start_timer=0.0):
        self.x=d['x']; self.y=d['y']; self.w=d['w']; self.lx=d.get('lx',0); self.ly=d.get('ly',0)
        self.spd=d.get('spd',1.0); self.ease=d.get('ease','SINE')
        self.tm=start_timer; self.xo=self.x; self.yo=self.y
        self.update(0) # Init position immediately

    def update(self, dt):
        self.tm += dt * self.spd
        off = math.sin(self.tm) if self.ease == 'SINE' else ((self.tm/math.pi)%2-1 if (self.tm/math.pi)%2>1 else 1-(self.tm/math.pi)%2)
        self.x = self.xo + (off * (self.lx/2)); self.y = self.yo + (off * (self.ly/2))

def ensure_dirs(): [os.makedirs(d, exist_ok=True) for d in DIRS.values()]
def strip_ansi(t): return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', t)
def draw_center(stdscr, y, text, attr=0):
    h, w = stdscr.getmaxyx()
    if 0 <= y < h: stdscr.addstr(y, max(0, (w - len(text)) // 2), text, attr)

# --- DATA LOADING ---
def load_plugins():
    if not os.path.exists(DIRS["plg"]): return
    sys.path.append(DIRS["plg"])
    for f in os.listdir(DIRS["plg"]):
        if f.endswith(".py") and f != "__init__.py":
            try:
                mod = __import__(f[:-3])
                if hasattr(mod, "register"):
                    d = mod.register()
                    vis = d.get("runtime", {}).get("display_char") or d.get("editor", {}).get("display_char") or d.get("char")
                    if vis: PLUGIN_VISUALS[d["char"]] = strip_ansi(str(vis))
            except: pass

def load_level(path, platform_timers=None):
    if not os.path.exists(path): return None, [], "Unknown"
    try:
        with open(path,'r') as f: parts = f.read().split("__METADATA__")
        lines = [l.rstrip() for l in parts[0].strip().split('\n')]
        if not lines: return None, [], "Empty"
        w = max(len(l) for l in lines); grid = [list(l.ljust(w)) for l in lines]; plats = []; title = os.path.basename(path)
        if len(parts)>1:
            try:
                meta = json.loads(parts[1])
                pdata = meta if isinstance(meta, list) else meta.get('platforms', [])
                title = str(meta.get('title', title)).replace('"','') if isinstance(meta, dict) else title
                for i, p in enumerate(pdata):
                    t_start = platform_timers[i] if platform_timers and i < len(platform_timers) else 0.0
                    mp = MovingPlatform(p, t_start); plats.append(mp)
                    for k in range(mp.w):
                        gy, gx = int(mp.yo), int(mp.xo)+k
                        if 0<=gy<len(grid) and 0<=gx<len(grid[0]): grid[gy][gx] = ' '
            except: pass
        return ["".join(row) for row in grid], plats, title
    except: return None, [], "Error"

def get_bg():
    ensure_dirs()
    cands = [os.path.join(d, f) for d in [DIRS["lvl"], DIRS["cmp"]] if os.path.exists(d) for f in os.listdir(d) if f.endswith(".txt")]
    return load_level(random.choice(cands)) if cands else (["#"*40, "#"+" "*38+"#", "#  TerminalFormer2  #", "#"+" "*38+"#", "#"*40]*5, [], "Menu")

def get_slots():
    ensure_dirs(); s = set()
    files = [os.path.join(DIRS["sav"], f) for f in os.listdir(DIRS["sav"]) if f.endswith(".json")]
    files += [f for f in os.listdir(".") if f.endswith(".json") and ("slot_" in f or "save" in f.lower())]
    return sorted([f for f in files if os.path.abspath(f) not in s and not s.add(os.path.abspath(f))])

def load_json(path):
    try: return json.load(open(path)) if os.path.exists(path) else {}
    except: return {}

# --- ACTIONS ---
def launch(slot=None, resume=False, path=None, speedrun=False):
    curses.endwin()
    cmd = [sys.executable, "game.py"] + ([path] if path else []) + (["--slot", slot] if slot else [])
    if resume: cmd.append("--resume")
    if speedrun: cmd.append("--speedrun")
    subprocess.run(cmd)

def text_input(stdscr, p):
    curses.echo(); curses.curs_set(1); stdscr.nodelay(False); stdscr.clear()
    draw_center(stdscr, stdscr.getmaxyx()[0]//2 - 2, f" {p} ", curses.A_BOLD)
    stdscr.refresh(); inp = stdscr.getstr(stdscr.getmaxyx()[0]//2, stdscr.getmaxyx()[1]//2 - 10, 30).decode()
    curses.noecho(); curses.curs_set(0); stdscr.nodelay(True)
    return inp.strip()

# --- DRAWING ---
def draw_bg_frame(stdscr, data, cx, cy):
    if not data or not data[0]: return
    grid, plats = data[0], data[1]
    h, w = stdscr.getmaxyx(); gh, gw = len(grid), len(grid[0])
    stdscr.attron(curses.A_DIM)
    for y in range(h):
        row = grid[int(y + cy) % gh]; sx = int(cx) % gw; cur_x = sx; d_len = 0; buf = ""
        while d_len < w:
            chk = min(gw - cur_x, w - d_len)
            buf += "".join(PLUGIN_VISUALS.get(c, c) for c in row[cur_x:cur_x+chk])
            d_len += chk; cur_x = 0
        try: stdscr.addstr(y, 0, buf)
        except: pass
    ox, oy = -int(cx % gw), -int(cy % gh)
    for p in plats:
        py = oy
        while py < h:
            px = ox
            while px < w:
                sx, sy = int(px + p.x), int(py + p.y)
                if -p.w < sx < w and 0 <= sy < h:
                    s, l = max(0, -sx), min(p.w, w - sx) - max(0, -sx)
                    if l > 0: stdscr.addstr(sy, sx + s, '█' * l)
                px += gw
            py += gh
    stdscr.attroff(curses.A_DIM)

def draw_menu(stdscr, data, cx, cy, title, items, sel):
    stdscr.erase(); h, w = stdscr.getmaxyx()
    lvl = data if len(data) < 4 else data[:3]
    draw_bg_frame(stdscr, lvl, cx, cy)
    if len(data) == 4 and lvl[0]:
        gh, gw = len(lvl[0]), len(lvl[0][0])
        p_info = data[3]
        raw_px, raw_py = p_info[0], p_info[1]
        cur_px, cur_py = raw_px, raw_py
        if len(p_info) == 5 and p_info[2] is not None:
            plat = lvl[1][p_info[2]]
            cur_px = plat.x + p_info[3]
            cur_py = plat.y + p_info[4]
        scr_x = int(cur_px - cx) % gw; scr_y = int(cur_py - cy) % gh
        if 0 <= scr_y < h and 0 <= scr_x < w: stdscr.addch(scr_y, scr_x, '#', curses.A_DIM)
    vis_h = min(len(items), max(1, (h-6)//2)) * 2
    sy = max(4, (h//2) - (vis_h//2))
    win_sz = max(1, (h-6)//2); top = max(0, min(sel - win_sz//2, len(items) - win_sz))
    draw_center(stdscr, max(0, sy-3), title, curses.A_BOLD | curses.A_UNDERLINE)
    if top > 0: draw_center(stdscr, sy-1, "^", curses.A_DIM)
    for i in range(top, min(len(items), top + win_sz)):
        lbl = items[i]; y = sy + (i - top)*2
        if i == sel: draw_center(stdscr, y, f"> {lbl} <", curses.A_BOLD)
        else: draw_center(stdscr, y, f"   {lbl}   ")
    if top + win_sz < len(items): draw_center(stdscr, sy + (min(len(items), top+win_sz)-top)*2, "v", curses.A_DIM)
    draw_center(stdscr, h-2, "UP/DOWN: Navigate  |  ENTER: Select  |  Q: Back/Quit", curses.A_DIM)
    stdscr.refresh()

# --- LOOPS ---
def run_loop(stdscr, bg, title, items, datas):
    sel = 0; cx, cy = 0.0, 0.0; stdscr.nodelay(True); stdscr.timeout(30)
    while True:
        cx += BG_SPD[0]; cy += BG_SPD[1]
        active = datas[sel] if datas and datas[sel] else bg
        for obj in (bg[1] + (active[1] if active!=bg and active else [])): obj.update(0.05)
        draw_menu(stdscr, active, cx, cy, title, items, sel)
        k = stdscr.getch()
        if k == curses.KEY_UP: sel = (sel - 1) % len(items)
        elif k == curses.KEY_DOWN: sel = (sel + 1) % len(items)
        elif k in (10, 13, 32): return items[sel], sel
        elif k in (ord('q'), ord('Q')): return "BACK", -1

def show_scores(stdscr, bg, cx, cy):
    stdscr.nodelay(True)
    while stdscr.getch() == -1:
        cx += BG_SPD[0]; cy += BG_SPD[1]; [p.update(0.05) for p in bg[1]]
        stdscr.erase(); draw_bg_frame(stdscr, bg, cx, cy)
        sc = load_json(SCORES_FILE); h = stdscr.getmaxyx()[0]
        draw_center(stdscr, 3, "--- SPEEDRUN RECORDS ---", curses.A_BOLD | curses.A_UNDERLINE)

        # 1. CAMPAIGN (Speedrun Only)
        r = 6; draw_center(stdscr, r, "CAMPAIGN (Speedrun Mode):", curses.A_BOLD)
        camp_scores = sc.get("speedrun_camp", []) # Specifically get speedrun_camp
        camp_scores = [s if isinstance(s, dict) else {"name":"UNK", "time":s} for s in camp_scores]

        for i, t in enumerate(camp_scores[:10]):
            draw_center(stdscr, r+1+i, f"{i+1}. {t.get('name','AAA')} - {t.get('time',0):.2f}s")
        if not camp_scores: draw_center(stdscr, r+1, "No validated speedruns.")

        # 2. INDIVIDUAL LEVELS (Normal & Speedrun)
        r += len(camp_scores[:10]) + 3; draw_center(stdscr, r, "LEVEL RECORDS:", curses.A_BOLD)

        # Filter: Exclude campaign main keys, allow everything else (level1.txt, speedrun_level1.txt)
        custom_keys = sorted([k for k in sc if k not in ("campaign", "speedrun_camp")])

        count = 0
        for i, k in enumerate(custom_keys):
            if r+1+count >= h-4: break
            level_scores = sc[k]
            if level_scores:
                best = level_scores[0]
                # Nice formatting
                if k.startswith("speedrun_"):
                    disp_name = k.replace("speedrun_", "") + " (Speedrun)"
                else:
                    disp_name = k

                if isinstance(best, dict):
                    draw_center(stdscr, r+1+count, f"{disp_name}: {best['name']} - {best['time']:.2f}s")
                else:
                    draw_center(stdscr, r+1+count, f"{disp_name}: {best:.2f}s")
                count += 1

        draw_center(stdscr, h-3, "Press ANY KEY to return", curses.A_BOLD)
        stdscr.refresh(); time.sleep(0.03)

# --- MENUS ---
def menu_custom(stdscr, bg):
    fs = sorted([f for f in os.listdir(DIRS["lvl"]) if f.endswith(".txt")])
    ds = [load_level(os.path.join(DIRS["lvl"], f)) for f in fs]
    l, i = run_loop(stdscr, bg, "SELECT CUSTOM LEVEL", [f"{d[2]} ({f})" for f,d in zip(fs, ds)] + ["BACK"], ds + [bg])
    if l != "BACK": launch(path=os.path.join(DIRS["lvl"], fs[i]))

def menu_editor(stdscr, bg):
    while True:
        fs = sorted([f for f in os.listdir(DIRS["lvl"]) if f.endswith(".txt")])
        ds = [load_level(os.path.join(DIRS["lvl"], f)) for f in fs]
        items = ["CREATE NEW LEVEL"] + [f"EDIT: {d[2]} ({f})" for f,d in zip(fs, ds)] + ["BACK"]
        l, i = run_loop(stdscr, bg, "LEVEL EDITOR", items, [bg] + ds + [bg])
        if l == "BACK": break
        if i == 0:
            n = text_input(stdscr, "New Level Name:"); n += "" if n.endswith(".txt") else ".txt"
            if n != ".txt": curses.endwin(); subprocess.run([sys.executable, "editor.py", n])
        elif i <= len(fs): curses.endwin(); subprocess.run([sys.executable, "editor.py", fs[i-1]])

def menu_speedrun(stdscr, bg):
    # Instant start!
    temp_path = os.path.join(DIRS["sav"], "speedrun_temp.json")
    json.dump({}, open(temp_path, 'w'))
    launch(slot=temp_path, speedrun=True)
    if os.path.exists(temp_path):
        try: os.remove(temp_path)
        except: pass

def menu_slots(stdscr, bg):
    while True:
        sl = get_slots()
        def get_prev(p):
            d = load_json(p)
            if d.get("campaign_complete", False) or d.get("completed", False):
                d = {}; json.dump({}, open(p, 'w'))

            lf = d.get("level_file")
            if lf and os.path.exists(lf):
                p_timers = d.get("platform_timers", [])
                lvl_data = load_level(lf, p_timers)
                px, py = d.get("px", 0), d.get("py", 0)
                att_idx, rel_x, rel_y = None, 0, 0
                for i, plat in enumerate(lvl_data[1]):
                    pl_y, pl_x = int(plat.y), int(plat.x)
                    if int(py) == pl_y - 1 and pl_x <= int(px) < pl_x + plat.w:
                        att_idx = i; rel_x = px - plat.x; rel_y = py - plat.y; break
                return (lvl_data[0], lvl_data[1], lvl_data[2], (px, py, att_idx, rel_x, rel_y))
            return bg

        ds = [get_prev(s) for s in sl]
        l, i = run_loop(stdscr, bg, "CAMPAIGN SLOTS", [os.path.basename(s) for s in sl] + ["NEW SLOT", "BACK"], ds + [bg, bg])
        if l == "BACK": break
        if l == "NEW SLOT":
            n = text_input(stdscr, "Slot Name:"); n += "" if n.endswith(".json") else ".json"
            if n != ".json":
                p = os.path.join(DIRS["sav"], n); json.dump({}, open(p, 'w')); launch(slot=p)
                return
        else:
            sp = sl[i]; d = load_json(sp); has_sv = "level_file" in d
            opts = (["Resume"] if has_sv else []) + ["New Game", "Delete", "Back"]
            l2, i2 = run_loop(stdscr, bg, f"SLOT: {os.path.basename(sp)}", opts, [ds[i] if has_sv else bg]*len(opts))
            if l2 == "Resume": launch(slot=sp, resume=True); return
            if l2 == "New Game": json.dump({}, open(sp, 'w')); launch(slot=sp); return
            if l2 == "Delete": os.remove(sp)

def main(stdscr):
    curses.curs_set(0); ensure_dirs(); load_plugins()
    bg = get_bg(); cx = cy = 0
    ops = [("PLAY CAMPAIGN", lambda: menu_slots(stdscr, bg)),
           ("SPEEDRUN MODE", lambda: menu_speedrun(stdscr, bg)),
           ("CUSTOM LEVELS", lambda: menu_custom(stdscr, bg)),
           ("LEVEL EDITOR", lambda: menu_editor(stdscr, bg)),
           ("HIGH SCORES", lambda: show_scores(stdscr, bg, cx, cy)),
           ("QUIT GAME", lambda: sys.exit(0))]
    while True:
        l, i = run_loop(stdscr, bg, "TerminalFormer2", [o[0] for o in ops], [bg]*len(ops))
        if l != "BACK": ops[i][1](); load_plugins(); bg = get_bg()
        else: sys.exit(0)

if __name__ == "__main__": curses.wrapper(main)
