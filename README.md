# quiet-edge

**quiet-edge** is a Dell ( PowerEdge 13G | iDRAC 8 ) IPMI Fan Controller Utility that uses an intelligent PID controller to dynamically adjust your server's fan speeds. By monitoring the temperatures of your CPU, GPU, and Storage Drives, it ensures your server stays optimally cooled while keeping noise levels to an absolute minimum.

## Features

- **Intelligent PID Control**: Smoothly manages fan speeds based on your target temperatures instead of relying on Dell's aggressive default fan curves.
- **Slew Rate Limiting**: Prevents aggressive, sudden fan speed spikes by enforcing maximum percentage increases/decreases per polling cycle.
- **Multi-Component Monitoring**: Tracks temperatures for:
  - **CPU/Motherboard**: via standard IPMI sensors.
  - **GPU**: via `nvidia-smi` (if present).
  - **Storage Drives**: via `smartctl` for individual drive monitoring.
- **Interactive Setup Wizard**: Easily configure target temperatures, polling intervals, and ramping limits through a command-line wizard.
- **Real-Time TUI Monitor**: Includes a slick `ncurses` terminal interface to visualize temperature histories and fan speeds in real-time.
- **Failsafe Design**: Automatically restores Dell's default dynamic auto control if the service stops or crashes.

## Prerequisites

- A Dell PowerEdge 13G Server with iDRAC 8 (or similar iDRAC-enabled system).
- **IPMI over LAN** enabled in your iDRAC settings.
- A Linux environment with `root` privileges.

*Note: The installer will automatically attempt to install `ipmitool`, `python3`, and `smartmontools` if they are not already present on your system.*

## Installation

1. Clone or download this repository to your server:
   ```bash
   git clone https://github.com/danrothmanwork/quiet-edge.git
   cd quiet-edge
   ```
2. Make the installer executable:
   ```bash
   chmod +x install.sh
   ```
3. Run the installer script:
   ```bash
   sudo ./install.sh install
   ```
4. Follow the interactive configuration wizard to set your base polling interval, minimum fan speed, max speed limits per cycle, and target temperatures for your detected hardware.

Once the wizard is complete, the `quiet-edge` service will automatically start in the background.

## Configuration

You can easily tweak your fan curve targets and limits at any time without reinstalling. Simply run the reconfigure command:

```bash
sudo ./install.sh reconfigure
```

### Configuration Options:
- **Base polling interval**: How often (in seconds) the script checks temperatures.
- **Minimum Fan Speed %**: The lowest speed percentage the fans are allowed to run at.
- **Max Fan Speed Increase/Decrease per Cycle**: (Slew Rate Limiting) Controls how fast the fans are allowed to ramp up or spin down. Lower values provide a smoother acoustic experience.
- **Target Temperatures**: The exact temperature (°C) you want the PID controller to maintain for your CPU, GPU, and Drives.

All settings are saved to `/etc/quiet-edge/config.json`.

## Usage & Monitoring

### The Ncurses Monitor
To view real-time graphs of your system temperatures and fan speeds, run the included monitor script from your terminal:

```bash
quiet_edge_monitor.py
```
*Press `q` or `ESC` to exit the monitor.*

### Managing the Service
The utility runs as a systemd service. You can manage it using standard `systemctl` commands:

```bash
# Check the status of the fan controller
sudo systemctl status quiet-edge

# Restart the service
sudo systemctl restart quiet-edge

# Stop the service (Restores default Dell iDRAC fan control)
sudo systemctl stop quiet-edge
```

### Logs
To view the fan controller's activity, speed adjustments, and raw temperature readings, check the project log file:
```bash
tail -f /var/log/quiet-edge.log
```

## Uninstallation

If you wish to remove the utility and restore your system to default Dell control, run:

```bash
sudo ./install.sh uninstall
```
You will be prompted on whether you want to retain or delete your configuration files and logs.

## Disclaimer

*This software interacts directly with your server's hardware cooling capabilities. Setting target temperatures too high or minimum fan speeds too low may cause hardware damage or emergency thermal shutdowns. Use this tool at your own risk.*