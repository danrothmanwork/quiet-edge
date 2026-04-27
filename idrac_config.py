import os, sys, subprocess, json

def run_cmd(cmd):
    try: return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
    except: return ""

print("\n" + "="*50)
print(" Thermal Dynamics - Configuration Wizard ")
print("="*50)

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

config_path = '/etc/idrac_fan_control/config.json'
config = {"min_fan_speed_pct": 15, "poll_interval_sec": 30, "target_temps": {}}

if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            existing = json.load(f)
            config.update(existing)
    except: pass

poll_int = config.get("poll_interval_sec", 30)
try:
    ans = input(f"\nBase polling interval (seconds) [{poll_int}]: ")
    config["poll_interval_sec"] = int(ans) if ans.strip().isdigit() else poll_int
    
    min_speed = config.get("min_fan_speed_pct", 15)
    ans = input(f"Minimum Fan Speed % [{min_speed}]: ")
    config["min_fan_speed_pct"] = int(ans) if ans.strip().isdigit() else min_speed
    
    print("\n>> Target Temperatures")
    print("The system will automatically adjust fans with a PID controller to maintain these temperatures.")
    
    target_temps = config.get("target_temps", {})
    
    # CPU
    if temps['cpu']:
        curr = target_temps.get("cpu", 50)
        ans = input(f"  Target CPU Temp (C) [{curr}]: ")
        target_temps["cpu"] = int(ans) if ans.strip().isdigit() else curr
    # GPU
    if temps['gpu']:
        curr = target_temps.get("gpu", 60)
        ans = input(f"  Target GPU Temp (C) [{curr}]: ")
        target_temps["gpu"] = int(ans) if ans.strip().isdigit() else curr
    # Drive
    if temps['drive']:
        curr = target_temps.get("drive", 45)
        ans = input(f"  Target Drive Temp (C) [{curr}]: ")
        target_temps["drive"] = int(ans) if ans.strip().isdigit() else curr
        
    config["target_temps"] = target_temps
            
except (EOFError, KeyboardInterrupt):
    print("\nSetup cancelled.")
    sys.exit(1)

os.makedirs('/etc/idrac_fan_control', exist_ok=True)
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print("\nConfiguration saved!")