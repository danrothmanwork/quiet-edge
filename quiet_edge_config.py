#!/usr/bin/env python3
import os, sys, subprocess, json

def run_cmd(cmd):
    try: return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
    except: return ""

def get_valid_int(prompt, default, min_val=0, max_val=None):
    while True:
        ans = input(prompt).strip()
        if not ans:
            return default
        try:
            val = int(ans)
            if val < min_val:
                print(f"  Error: Value must be at least {min_val}.")
                continue
            if max_val is not None and val > max_val:
                print(f"  Error: Value cannot exceed {max_val}.")
                continue
            return val
        except ValueError:
            print("  Error: Please enter a valid number.")

print("\n" + "="*50)
print(" quiet-edge - Configuration Wizard ")
print("="*50)

print("\n>> Verifying IPMI connection...")
if not run_cmd("ipmitool mc info"):
    print("  Error: Could not communicate with iDRAC via IPMI.")
    print("  Please ensure IPMI is enabled in your iDRAC settings,")
    print("  the IPMI kernel modules are loaded, and you are running as root.")
    sys.exit(1)
print("  IPMI connection successful.")

print("\n>> Scanning for sensors...")
temps = {'cpu': False, 'gpu': False, 'drive': False}

# CPU
ipmi_out = run_cmd("ipmitool sdr type temperature")
for line in ipmi_out.split('\n'):
    line = line.lower()
    if 'degrees c' in line and not ('inlet' in line or 'ambient' in line):
        temps['cpu'] = True
        break

# GPU
smi_out = run_cmd("nvidia-smi -L 2>/dev/null")
if smi_out: temps['gpu'] = True

# Drive
scan_out = run_cmd("smartctl --scan 2>/dev/null")
if scan_out: temps['drive'] = True

print(f"  CPU   Detected : {'Yes' if temps['cpu'] else 'No'}")
print(f"  GPU   Detected : {'Yes' if temps['gpu'] else 'No'}")
print(f"  Drive Detected : {'Yes' if temps['drive'] else 'No'}")

config_path = '/etc/quiet-edge/config.json'
config = {"min_fan_speed_pct": 15, "poll_interval_sec": 30, "max_step_up": 8, "max_step_down": 2, "target_temps": {}}

if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            existing = json.load(f)
            config.update(existing)
    except: pass

poll_int = config.get("poll_interval_sec", 30)
try:
    config["poll_interval_sec"] = get_valid_int(f"\nBase polling interval (seconds) [{poll_int}]: ", poll_int, 1)
    
    min_speed = config.get("min_fan_speed_pct", 15)
    config["min_fan_speed_pct"] = get_valid_int(f"Minimum Fan Speed % [{min_speed}]: ", min_speed, 0, 100)
    
    step_up = config.get("max_step_up", 8)
    config["max_step_up"] = get_valid_int(f"Max Fan Speed Increase/Cycle % [{step_up}]: ", step_up, 1, 100)
    
    step_down = config.get("max_step_down", 2)
    config["max_step_down"] = get_valid_int(f"Max Fan Speed Decrease/Cycle % [{step_down}]: ", step_down, 1, 100)
    
    print("\n>> Target Temperatures")
    print("The system will automatically adjust fans with a PID controller to maintain these temperatures.")
    
    target_temps = config.get("target_temps", {})
    
    # CPU
    if temps['cpu']:
        curr = target_temps.get("cpu", 50)
        target_temps["cpu"] = get_valid_int(f"  Target CPU Temp (C) [{curr}]: ", curr, 0, 100)
    # GPU
    if temps['gpu']:
        curr = target_temps.get("gpu", 60)
        target_temps["gpu"] = get_valid_int(f"  Target GPU Temp (C) [{curr}]: ", curr, 0, 100)
    # Drive
    if temps['drive']:
        curr = target_temps.get("drive", 45)
        target_temps["drive"] = get_valid_int(f"  Target Drive Temp (C) [{curr}]: ", curr, 0, 100)
        
    config["target_temps"] = target_temps
            
except (EOFError, KeyboardInterrupt):
    print("\nSetup cancelled.")
    sys.exit(1)

os.makedirs('/etc/quiet-edge', exist_ok=True)
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print("\nConfiguration saved!")

# Restart the service if it is already installed to apply changes immediately
if os.path.exists('/etc/systemd/system/quiet-edge.service'):
    print("\n>> Restarting quiet-edge service to apply changes...")
    os.system("systemctl restart quiet-edge.service")