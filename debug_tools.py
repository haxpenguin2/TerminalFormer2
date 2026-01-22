#!/usr/bin/env python3
"""
debug_tools.py
Small debug scripts for TerminalFormer2.
Run from menu -> Debug tools.
"""

import curses
import time
import os
from game import load_level

def show_level_info(stdscr, path):
    stdscr.clear()
    stdscr.addstr(0, 0, f"Level info: {path}")
    if not os.path.exists(path):
        stdscr.addstr(1, 0, "Not found.")
        stdscr.getch()
        return
    grid = load_level(path)
    h = len(grid)
    w = len(grid[0]) if h else 0
    spawns = 0
    goals = 0
    spikes = 0
    solids = 0
    for row in grid:
        for ch in row:
            if ch == 'S':
                spawns += 1
            elif ch == 'G':
                goals += 1
            elif ch == '^':
                spikes += 1
            elif ch == '#':
                solids += 1
    stdscr.addstr(2, 0, f"size: {w} x {h}")
    stdscr.addstr(3, 0, f"spawns: {spawns}, goals: {goals}, spikes: {spikes}, solids: {solids}")
    stdscr.addstr(5, 0, "Press any key.")
    stdscr.getch()

def run_debug_menu(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    path = os.path.join("levels", "level1.txt")
    while True:
        stdscr.clear()
        stdscr.addstr(0,0,"Debug tools")
        stdscr.addstr(2,0,"1) Show level info")
        stdscr.addstr(3,0,"q) Back")
        stdscr.refresh()
        k = stdscr.getch()
        if k == ord('1'):
            show_level_info(stdscr, path)
        elif k == ord('q'):
            return
