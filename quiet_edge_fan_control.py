#!/usr/bin/env python3
"""
quiet-edge - Dell PowerEdge 13G IPMI Fan Controller Utility
"""

import subprocess
import json
import re
import sys
import os
import logging
from datetime import datetime

CONFIG_PATH = '/etc/quiet-edge/config.json'
STATE_PATH = '/etc/quiet-edge/state.json'
LOG_PATH = '/var/log/quiet-edge.log'

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log(msg, level='info'):
    print(msg)
    if level == 'info':
        logging.info(msg)
    elif level == 'warning':
        logging.warning(msg)
    elif level == 'error':
        logging.error(msg)

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r') as f:
        try:
            return json.load(f)
        except:
            return default

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f)

def run_cmd(cmd, check_errors=True):
    try:
        result = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if check_errors and result.returncode != 0 and "nvidia-smi" not in cmd:
            log(f"Command failed (Code {result.returncode}): {cmd}", "error")
            if result.stderr:
                log(f"  Stderr: {result.stderr.strip()}", "error")
        return result.stdout
    except Exception as e:
        if check_errors:
            log(f"Command exception: {cmd} - {str(e)}", "error")
        return ""

def enable_manual_fan_control():
    run_cmd("ipmitool raw 0x30 0x30 0x01 0x00")

def set_fan_speed(pct):
    pct = max(0, min(100, pct))
    hex_speed = hex(pct)
    run_cmd(f"ipmitool raw 0x30 0x30 0x02 0xff {hex_speed}")

def get_temperatures():
    temps = {'cpu': 0, 'gpu': 0, 'drive': 0}
    
    # 1. CPU / Motherboard (IPMI)
    # Ignore ambient/inlet temperatures, fallback to general 'Temp'
    ipmi_out = run_cmd("ipmitool sdr type temperature")
    cpu_vals = []
    for line in ipmi_out.split('\n'):
        line = line.lower()
        if 'inlet' in line or 'ambient' in line: continue
        match = re.search(r'\|.*?(\d+)\s*degrees c', line)
        if match:
            cpu_vals.append(int(match.group(1)))
    if cpu_vals: temps['cpu'] = max(cpu_vals)

    # 2. GPU (NVIDIA OS-Level)
    smi_out = run_cmd("nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader", check_errors=False)
    gpu_vals = []
    for line in smi_out.split('\n'):
        if line.strip().isdigit():
            gpu_vals.append(int(line.strip()))
    if gpu_vals: temps['gpu'] = max(gpu_vals)

    # 3. Storage Drives (smartctl OS-Level)
    scan_out = run_cmd("smartctl --scan")
    drive_vals = []
    drive_details = {}
    for line in scan_out.split('\n'):
        if line.startswith('/dev/'):
            dev_args = line.split('#')[0].strip()
            dev_path = dev_args.split()[0]
            smart_out = run_cmd(f"smartctl -j -A {dev_args}", check_errors=False)
            val = None
            try:
                data = json.loads(smart_out)
                if 'temperature' in data and 'current' in data['temperature']:
                    val = int(data['temperature']['current'])
            except:
                # RegEx Fallback for older smartmontools compatibility
                raw_out = run_cmd(f"smartctl -A {dev_args}", check_errors=False)
                m = re.search(r'(?:Temperature_Celsius.*?-\s+|Current Drive Temperature:\s+|Temperature:\s+)(\d+)', raw_out, re.IGNORECASE)
                if m: val = int(m.group(1))
            
            if val is not None:
                drive_vals.append(val)
                short_name = dev_path.split('/')[-1]
                drive_details[short_name] = val
    if drive_vals: temps['drive'] = max(drive_vals)
    temps['drive_details'] = drive_details

    return temps

def main():
    if os.geteuid() != 0:
        log("Must run as root", "error")
        sys.exit(1)
        
    config = load_json(CONFIG_PATH, {})
    if not config:
        log("Config not found or invalid.", "error")
        sys.exit(1)
        
    enable_manual_fan_control()
    
    poll_interval = config.get('poll_interval_sec', 30)
    min_speed = config.get('min_fan_speed_pct', 20)
    target_temps = config.get('target_temps', {})
    
    log(f"Starting quiet-edge PID Service. Polling interval: {poll_interval}s")
    
    # PI Constants
    Kp_up = 4.0
    Kp_down = 1.0
    Ki = 0.1
    
    while True:
        try:
            state = load_json(STATE_PATH, {})
            temps = get_temperatures()
            rpm_str = get_fan_rpms()
            
            state['current_temps'] = temps
            state['rpm_str'] = rpm_str
            
            last_speed = state.get('last_speed', min_speed)
            pid_state = state.get('pid_state', {})
            smoothed_temps = state.get('smoothed_temps', {})
            
            max_requested_speed = min_speed
            
            # Apply EMA smoothing to temperatures
            ema_alpha = 0.4
            for comp, t in temps.items():
                if isinstance(t, dict): continue
                if comp in smoothed_temps:
                    smoothed_temps[comp] = int((ema_alpha * t) + ((1 - ema_alpha) * smoothed_temps[comp]))
                else:
                    smoothed_temps[comp] = t
            state['smoothed_temps'] = smoothed_temps
            
            for component, tgt in target_temps.items():
                if component in smoothed_temps:
                    current_temp = smoothed_temps[component]
                    error = current_temp - tgt
                    
                    c_state = pid_state.get(component, {'integral': last_speed / Ki})
                    
                    # Accumulate integral
                    c_state['integral'] += error * poll_interval
                    
                    # Anti-windup
                    max_integral = 100 / Ki
                    if c_state['integral'] > max_integral: c_state['integral'] = max_integral
                    if c_state['integral'] < 0: c_state['integral'] = 0
                    
                    p_term = (Kp_up if error > 0 else Kp_down) * error
                    i_term = Ki * c_state['integral']
                    
                    comp_speed = p_term + i_term
                    
                    pid_state[component] = c_state
                    
                    if comp_speed > max_requested_speed:
                        max_requested_speed = comp_speed
                        
            state['pid_state'] = pid_state
            
            current_target = max(min_speed, min(100, int(max_requested_speed)))
            
            log(f"Raw Temps -> CPU:{temps.get('cpu',0)}C GPU:{temps.get('gpu',0)}C Drive:{temps.get('drive',0)}C ({temps.get('drive_details', {})})")
            log(f"Smoothed  -> CPU:{smoothed_temps.get('cpu',0)}C GPU:{smoothed_temps.get('gpu',0)}C Drive:{smoothed_temps.get('drive',0)}C")
            
            if current_target != last_speed:
                log(f"Adjusting fan speed to {current_target}% (was {last_speed}%) based on PID Targets")
                set_fan_speed(current_target)
                state['last_speed'] = current_target
            else:
                log(f"Fan speed maintaining at {current_target}%")
                set_fan_speed(current_target)
                state['last_speed'] = current_target
                
            save_json(STATE_PATH, state)
            
            import time
            time.sleep(poll_interval)
            
        except Exception as e:
            log(f"Error in execution block: {e}", "error")
            import time
            time.sleep(poll_interval)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("Service stopped via KeyboardInterrupt", "warning")
        pass