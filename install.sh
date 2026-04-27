#!/bin/bash
# quiet-edge - Automated Setup
# Usage: ./install.sh [install|reconfigure|uninstall]

# --- Configuration ---
BIN_DIR="/usr/local/bin"
SYSTEMD_DIR="/etc/systemd/system"
CONF_DIR="/etc/quiet-edge"
LOG_FILE="/var/log/quiet-edge.log"

# --- Colors ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Helper Functions ---
print_info() { echo -e "${YELLOW}>> $1${NC}"; }
print_success() { echo -e "${GREEN}>> $1${NC}"; }
print_error() { echo -e "${RED}Error: $1${NC}"; }

install_file() {
    local src="$1"
    local dest="$2"
    local make_exec="${3:-false}"

    if [ ! -f "$src" ]; then
        print_error "$src not found in current directory."
        exit 1
    fi
    
    cp "$src" "$dest"
    
    if [ "$make_exec" = true ]; then
        chmod +x "$dest"
    fi
}

# --- Privilege Check ---
if [ "$EUID" -ne 0 ]; then 
  print_info "Elevating privileges. Please enter your password if prompted."
  exec sudo bash "$0" "$@"
fi

ACTION="${1:-install}"

# --- Main Logic ---
case "$ACTION" in
    uninstall)
        print_info "Stopping and disabling service..."
        systemctl stop quiet-edge.service 2>/dev/null
        systemctl disable quiet-edge.service 2>/dev/null
        rm -f "${SYSTEMD_DIR}/quiet-edge.service"
        systemctl daemon-reload
        
        print_info "Removing scripts..."
        rm -f "${BIN_DIR}/quiet_edge_fan_control.py"
        rm -f "${BIN_DIR}/quiet_edge_monitor.py"
        rm -f "${BIN_DIR}/quiet_edge_config.py"
        
        print_info "Restoring Dell Auto Fan Control..."
        ipmitool raw 0x30 0x30 0x01 0x01 2>/dev/null
        
        read -p "Remove configuration and logs? ($CONF_DIR, $LOG_FILE) [y/N]: " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$CONF_DIR"
            rm -f "$LOG_FILE"
            print_success "Configuration removed."
        fi
        
        print_success "Uninstall complete!"
        exit 0
        ;;
        
    reconfigure)
        if [ ! -f "${BIN_DIR}/quiet_edge_config.py" ]; then
            print_error "Configuration tool not found. Please run full install first."
            exit 1
        fi
        "${BIN_DIR}/quiet_edge_config.py"
        if [ $? -eq 0 ]; then
            print_success "Reconfiguration complete!"
        fi
        exit 0
        ;;
        
    install)
        print_info "Checking prerequisites..."
        if ! command -v ipmitool >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1 || ! command -v smartctl >/dev/null 2>&1; then
            print_info "Installing prerequisites..."
            apt-get update -qq && apt-get install -y ipmitool python3 smartmontools
        else
            print_info "All prerequisites (ipmitool, python3, smartmontools) are already installed."
        fi

        print_info "Loading IPMI kernel modules..."
        modprobe ipmi_devintf
        modprobe ipmi_si
        if ! grep -q "ipmi_devintf" /etc/modules; then echo "ipmi_devintf" >> /etc/modules; fi
        if ! grep -q "ipmi_si" /etc/modules; then echo "ipmi_si" >> /etc/modules; fi

        print_info "Installing Configuration Wizard..."
        install_file "quiet_edge_config.py" "${BIN_DIR}/quiet_edge_config.py" true

        print_info "Starting Interactive Setup Wizard..."
        "${BIN_DIR}/quiet_edge_config.py"
        SETUP_EXIT=$?

        if [ $SETUP_EXIT -ne 0 ]; then
            print_error "Installer aborted."
            exit 1
        fi

        print_info "Installing python utility..."
        install_file "quiet_edge_fan_control.py" "${BIN_DIR}/quiet_edge_fan_control.py" true

        print_info "Installing Ncurses Monitor..."
        install_file "quiet_edge_monitor.py" "${BIN_DIR}/quiet_edge_monitor.py" true

        print_info "Setting up System Service..."
        install_file "quiet-edge.service" "${SYSTEMD_DIR}/quiet-edge.service" false

        systemctl daemon-reload
        systemctl enable --now quiet-edge.service

        print_success "Installation complete! Service started."
        print_info "Monitor status with: systemctl status quiet-edge"
        exit 0
        ;;
        
    *)
        echo "Usage: $0 [install|reconfigure|uninstall]"
        exit 1
        ;;
esac