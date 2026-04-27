#!/usr/bin/env python3
"""
quiet-edge - Ncurses TUI Monitor
Shows real-time temperature and fan speed graphs.
"""

import curses
import time
import json
import os
import sys
from collections import deque

STATE_PATH = '/etc/quiet-edge/state.json'
CONFIG_PATH = '/etc/quiet-edge/config.json'

def get_target_temps():
    targets = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
                targets = config.get('target_temps', {})
        except:
            pass
    return targets

def get_state_data():
    temps = {'cpu': 0, 'gpu': 0, 'drive': 0, 'drive_details': {}}
    fan_pct = 0
    rpm_str = ""
    
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r') as f:
                state = json.load(f)
                
                # Retrieve temps
                saved_temps = state.get('current_temps', {})
                temps['cpu'] = saved_temps.get('cpu', 0)
                temps['gpu'] = saved_temps.get('gpu', 0)
                temps['drive'] = saved_temps.get('drive', 0)
                temps['drive_details'] = saved_temps.get('drive_details', {})
                
                # Retrieve fan info
                fan_pct = state.get('last_speed', 0)
                rpm_str = state.get('rpm_str', "")
        except:
            pass
            
    return temps, fan_pct, rpm_str

def draw_graph(win, title, history, height, width, color, details_str="", target_val=None):
    win.erase()
    win.box()
    
    curr_val = history[-1] if history else 0
    target_str = f" | Target: {target_val}C" if target_val else ""
    
    if details_str:
        if "Drive" in title:
            header_text = f" {title} | Max: {curr_val}C {details_str}{target_str} "
        elif "Fan" in title:
            header_text = f" {title} | Current: {curr_val}% {details_str} "
        else:
            header_text = f" {title} | Current: {curr_val} {details_str}{target_str} "
    else:
        if "Fan" in title:
            header_text = f" {title} | Current: {curr_val}% "
        else:
            header_text = f" {title} | Current: {curr_val}C{target_str} "
        
    if len(header_text) > width - 4:
        header_text = header_text[:width - 7] + "... "
        
    try:
        win.addstr(0, 2, header_text)
    except curses.error:
        pass
    
    if not history:
        win.noutrefresh()
        return

    max_val = 100
    if history:
        max_val = max(100, max(history))
        if target_val:
            max_val = max(max_val, target_val)

    inner_h = height - 2
    inner_w = width - 2

    # Draw Y axis labels safely
    try:
        win.addstr(1, 1, f"{max_val}")
        win.addstr(inner_h, 1, "0")
    except curses.error:
        pass

    # Draw Target Line
    if target_val:
        target_bars = int((target_val / max_val) * inner_h)
        if target_bars > 0:
            target_row = height - 1 - target_bars
            if 0 < target_row < height - 1:
                for col in range(5, width - 1):
                    try:
                        win.addstr(target_row, col, "-", curses.A_DIM)
                    except curses.error:
                        pass

    data = list(history)[-inner_w+4:] # Leave room for labels
    
    for i, val in enumerate(data):
        col = width - len(data) + i - 1
        if col < 5: continue # don't overwrite labels
        bars = int((val / max_val) * inner_h)
        for b in range(bars):
            row = height - 2 - b
            if row > 0 and row < height and col > 0 and col < width:
                try:
                    win.addstr(row, col, "█", color)
                except curses.error:
                    pass

    win.noutrefresh()

def main(stdscr):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)   # CPU
    curses.init_pair(2, curses.COLOR_GREEN, -1) # GPU
    curses.init_pair(3, curses.COLOR_CYAN, -1)  # Fan
    curses.init_pair(4, curses.COLOR_YELLOW, -1) # Drive
    
    curses.curs_set(0)
    stdscr.timeout(100) # 100ms
    
    history_cpu = deque(maxlen=300)
    history_gpu = deque(maxlen=300)
    history_drive = deque(maxlen=300)
    history_fan = deque(maxlen=300)

    last_poll = 0
    last_y, last_x = 0, 0
    force_redraw = True
    last_fan_details_str = ""
    target_temps = {}
    
    while True:
        c = stdscr.getch()
        if c == ord('q') or c == 27:
            break
        elif c == curses.KEY_RESIZE:
            force_redraw = True
            
        now = time.time()
        max_y, max_x = stdscr.getmaxyx()
        
        if max_y != last_y or max_x != last_x:
            force_redraw = True
            last_y, last_x = max_y, max_x

        if now - last_poll >= 2.0 or force_redraw:
            if now - last_poll >= 2.0:
                temps, fan_pct, fan_rpms = get_state_data()
                target_temps = get_target_temps()
                
                history_cpu.append(temps.get('cpu', 0))
                history_gpu.append(temps.get('gpu', 0))
                history_fan.append(fan_pct)
                
                details = temps.get('drive_details', {})
                if details:
                    avg_drive = int(sum(details.values()) / len(details))
                else:
                    avg_drive = temps.get('drive', 0)
                history_drive.append(avg_drive)
                    
                last_fan_details_str = fan_rpms
                last_poll = now
            
            force_redraw = False
            
            if max_y < 16 or max_x < 50:
                stdscr.erase()
                try:
                    stdscr.addstr(0,0, "Terminal too small. Enlarge window.")
                except curses.error:
                    pass
                stdscr.noutrefresh()
                curses.doupdate()
                continue
                
            stdscr.erase()
            header = f" quiet-edge Monitor | 'q' to quit | Updating from Controller "
            try:
                stdscr.addstr(0, (max_x - len(header)) // 2, header, curses.A_BOLD | curses.A_REVERSE)
            except curses.error:
                pass
            stdscr.noutrefresh()
            
            graph_h = (max_y - 1) // 4
            
            win_cpu = curses.newwin(graph_h, max_x, 1, 0)
            win_gpu = curses.newwin(graph_h, max_x, 1 + graph_h, 0)
            win_drive = curses.newwin(graph_h, max_x, 1 + graph_h * 2, 0)
            win_fan = curses.newwin(graph_h, max_x, 1 + graph_h * 3, 0)
            
            draw_graph(win_cpu, "CPU Temp", history_cpu, graph_h, max_x, curses.color_pair(1), target_val=target_temps.get('cpu'))
            draw_graph(win_gpu, "GPU Temp", history_gpu, graph_h, max_x, curses.color_pair(2), target_val=target_temps.get('gpu'))
            draw_graph(win_drive, "Avg Drive Temp", history_drive, graph_h, max_x, curses.color_pair(4), target_val=target_temps.get('drive'))
            draw_graph(win_fan, "Fan Speed (%)", history_fan, graph_h, max_x, curses.color_pair(3), details_str=last_fan_details_str)
            
            curses.doupdate()

if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass