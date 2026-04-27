#!/usr/bin/env python3
"""
Thermal Dynamics - Ncurses TUI Monitor
Shows real-time temperature and fan speed graphs.
"""

import curses
import time
import json
import os
import sys
from collections import deque

STATE_PATH = '/etc/idrac_fan_control/state.json'

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

def draw_graph(win, title, history, height, width, color, details_str=""):
    win.erase()
    win.box()
    
    curr_val = history[-1] if history else 0
    if details_str:
        if "Drive" in title:
            header_text = f" {title} | Max: {curr_val}C {details_str} "
        elif "Fan" in title:
            header_text = f" {title} | Current: {curr_val}% {details_str} "
        else:
            header_text = f" {title} | Current: {curr_val} {details_str} "
    else:
        if "Fan" in title:
            header_text = f" {title} | Current: {curr_val}% "
        else:
            header_text = f" {title} | Current: {curr_val}C "
        
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
    if history: max_val = max(100, max(history))

    inner_h = height - 2
    inner_w = width - 2

    # Draw Y axis labels safely
    try:
        win.addstr(1, 1, f"{max_val}")
        win.addstr(inner_h, 1, "0")
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

def draw_multi_graph(win, title, histories_dict, height, width):
    win.erase()
    win.box()
    if not histories_dict:
        win.noutrefresh()
        return

    legend_parts = []
    symbols = ['*', 'o', '+', 'x', '.', '~', '-', '^']
    color_keys = [4, 2, 1, 3, 5, 6, 7] # 5 is magenta, 6 is cyan, etc. 
    
    for idx, (k, v) in enumerate(histories_dict.items()):
        if v:
            sym = symbols[idx % len(symbols)]
            legend_parts.append(f"{sym} {k}: {v[-1]}C")
            
    legend = " | ".join(legend_parts)
    header_text = f" Drives Multi-Temp | {legend} "
    
    if len(header_text) > width - 4:
        header_text = header_text[:width - 7] + "... "
        
    try:
        win.addstr(0, 2, header_text)
    except curses.error:
        pass

    max_val = 100
    all_vals = [val for hist in histories_dict.values() for val in hist]
    if all_vals:
        max_val = max(100, max(all_vals))

    inner_h = height - 2
    inner_w = width - 2

    try:
        win.addstr(1, 1, f"{max_val}")
        win.addstr(inner_h, 1, "0")
    except curses.error:
        pass

    for drive_idx, (drive_name, history) in enumerate(histories_dict.items()):
        symbol = symbols[drive_idx % len(symbols)]
        col_color = curses.color_pair(color_keys[drive_idx % len(color_keys)])
        
        data = list(history)[-inner_w+4:]
        for i, val in enumerate(data):
            col = width - len(data) + i - 1
            if col < 5: continue
            
            # map row
            row = height - 2 - int((val / max_val) * (inner_h - 1))
            if 0 < row < height - 1 and 0 < col < width - 1:
                try:
                    win.addstr(row, col, symbol, col_color)
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
    history_drive_details = {}
    history_fan = deque(maxlen=300)

    last_poll = 0
    last_y, last_x = 0, 0
    force_redraw = True
    last_fan_details_str = ""
    
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
                
                history_cpu.append(temps.get('cpu', 0))
                history_gpu.append(temps.get('gpu', 0))
                history_fan.append(fan_pct)
                
                details = temps.get('drive_details', {})
                for k, v in details.items():
                    if k not in history_drive_details:
                        history_drive_details[k] = deque(maxlen=300)
                    history_drive_details[k].append(v)
                    
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
            header = f" Thermal Dynamics Monitor | 'q' to quit | Updating from Controller "
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
            
            draw_graph(win_cpu, "CPU Temp", history_cpu, graph_h, max_x, curses.color_pair(1))
            draw_graph(win_gpu, "GPU Temp", history_gpu, graph_h, max_x, curses.color_pair(2))
            draw_multi_graph(win_drive, "Drive Temp", history_drive_details, graph_h, max_x)
            draw_graph(win_fan, "Fan Speed (%)", history_fan, graph_h, max_x, curses.color_pair(3), last_fan_details_str)
            
            curses.doupdate()

if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass