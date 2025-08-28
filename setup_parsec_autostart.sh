#!/bin/bash
# Script to install Parsec and configure it to launch automatically as server
# Compatible with Ubuntu/Debian systems

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Parsec Auto-Start Setup Script${NC}"
echo "=============================="

# Function to check if running as root
check_root() {
    if [ "$EUID" -eq 0 ]; then
        echo -e "${RED}Please do not run this script as root${NC}"
        echo -e "${YELLOW}Run as the user who will use Parsec${NC}"
        exit 1
    fi
}

# Function to install Parsec
install_parsec() {
    echo -e "${BLUE}Installing Parsec...${NC}"
    
    # Check if Parsec is already installed
    if command -v parsecd >/dev/null 2>&1; then
        echo -e "${GREEN}Parsec is already installed${NC}"
        return 0
    fi
    
    # Create temporary directory
    local temp_dir=$(mktemp -d)
    cd "$temp_dir"
    
    # Download Parsec for Linux
    echo "Downloading Parsec for Linux..."
    wget -O parsec-linux.deb "https://builds.parsecgaming.com/package/parsec-linux.deb"
    
    # Install Parsec
    echo "Installing Parsec package..."
    sudo dpkg -i parsec-linux.deb || true
    
    # Fix any dependency issues
    sudo apt-get install -f -y
    
    # Cleanup
    cd - >/dev/null
    rm -rf "$temp_dir"
    
    # Verify installation
    if command -v parsecd >/dev/null 2>&1; then
        echo -e "${GREEN}Parsec installed successfully${NC}"
    else
        echo -e "${RED}Parsec installation failed${NC}"
        exit 1
    fi
}

# Function to create Parsec configuration
create_parsec_config() {
    echo -e "${BLUE}Creating Parsec configuration...${NC}"
    
    local config_dir="$HOME/.parsec"
    local config_file="$config_dir/config.txt"
    
    # Create config directory
    mkdir -p "$config_dir"
    
    # Create basic configuration for server mode
    cat > "$config_file" << EOF
# Parsec Configuration
# This file configures Parsec to run as a server

# Server configuration
server_enabled = 1
server_auto_start = 1

# Display settings
encoder_bitrate = 50
encoder_fps = 60
encoder_resolution_x = 1920
encoder_resolution_y = 1080

# Audio settings
audio_enabled = 1

# Network settings
port = 8000

# Host settings
host_enabled = 1
host_allow_guests = 1

# Security settings
# Note: You should configure authentication in the Parsec app
EOF
    
    echo -e "${GREEN}Parsec configuration created at $config_file${NC}"
}

# Function to create systemd service for Parsec
create_systemd_service() {
    echo -e "${BLUE}Creating systemd service for Parsec auto-start...${NC}"
    
    local service_file="$HOME/.config/systemd/user/parsec.service"
    local service_dir="$(dirname "$service_file")"
    
    # Create systemd user directory
    mkdir -p "$service_dir"
    
    # Create systemd service file
    cat > "$service_file" << EOF
[Unit]
Description=Parsec Gaming Service
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/parsecd
Restart=always
RestartSec=5
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/%i

# Ensure service runs in user context
User=%i
Group=%i

# Set working directory
WorkingDirectory=%h

# Logging
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF
    
    echo -e "${GREEN}Systemd service created at $service_file${NC}"
}

# Function to create desktop autostart entry
create_desktop_autostart() {
    echo -e "${BLUE}Creating desktop autostart entry...${NC}"
    
    local autostart_dir="$HOME/.config/autostart"
    local autostart_file="$autostart_dir/parsec.desktop"
    
    # Create autostart directory
    mkdir -p "$autostart_dir"
    
    # Create desktop autostart entry
    cat > "$autostart_file" << EOF
[Desktop Entry]
Type=Application
Name=Parsec
Comment=Parsec Gaming Service
Exec=/usr/bin/parsecd
Icon=parsec
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
StartupNotify=false
Categories=Network;Game;
EOF
    
    chmod +x "$autostart_file"
    echo -e "${GREEN}Desktop autostart entry created at $autostart_file${NC}"
}

# Function to create startup script
create_startup_script() {
    echo -e "${BLUE}Creating Parsec startup script...${NC}"
    
    local script_file="$HOME/.local/bin/start-parsec.sh"
    local script_dir="$(dirname "$script_file")"
    
    # Create bin directory
    mkdir -p "$script_dir"
    
    # Create startup script
    cat > "$script_file" << 'EOF'
#!/bin/bash
# Parsec startup script with logging and error handling

LOG_FILE="$HOME/.parsec/startup.log"
PARSEC_PID_FILE="$HOME/.parsec/parsec.pid"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Function to check if Parsec is running
is_parsec_running() {
    if [ -f "$PARSEC_PID_FILE" ]; then
        local pid=$(cat "$PARSEC_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        else
            rm -f "$PARSEC_PID_FILE"
        fi
    fi
    return 1
}

# Function to start Parsec
start_parsec() {
    log_message "Starting Parsec service"
    
    # Wait for display to be available
    local max_wait=30
    local wait_count=0
    
    while [ -z "$DISPLAY" ] && [ $wait_count -lt $max_wait ]; do
        export DISPLAY=:0
        sleep 1
        wait_count=$((wait_count + 1))
    done
    
    if [ -z "$DISPLAY" ]; then
        log_message "ERROR: Display not available after waiting"
        exit 1
    fi
    
    # Check if already running
    if is_parsec_running; then
        log_message "Parsec is already running"
        exit 0
    fi
    
    # Start Parsec in background
    nohup /usr/bin/parsecd > "$HOME/.parsec/parsec.log" 2>&1 &
    local parsec_pid=$!
    
    # Save PID
    echo "$parsec_pid" > "$PARSEC_PID_FILE"
    
    log_message "Parsec started with PID: $parsec_pid"
    
    # Wait a moment and check if it's still running
    sleep 2
    if is_parsec_running; then
        log_message "Parsec startup successful"
    else
        log_message "ERROR: Parsec failed to start properly"
        exit 1
    fi
}

# Main execution
mkdir -p "$(dirname "$LOG_FILE")"
start_parsec
EOF
    
    chmod +x "$script_file"
    echo -e "${GREEN}Startup script created at $script_file${NC}"
}

# Function to enable auto-start methods
enable_autostart() {
    echo -e "${BLUE}Enabling Parsec auto-start...${NC}"
    
    # Method 1: Enable systemd user service
    echo "Enabling systemd user service..."
    systemctl --user daemon-reload
    systemctl --user enable parsec.service
    
    # Method 2: Desktop autostart is already created
    echo "Desktop autostart entry is ready"
    
    # Method 3: Add to .profile for login execution
    local profile_file="$HOME/.profile"
    local startup_line="$HOME/.local/bin/start-parsec.sh"
    
    if ! grep -q "start-parsec.sh" "$profile_file" 2>/dev/null; then
        echo "" >> "$profile_file"
        echo "# Auto-start Parsec on login" >> "$profile_file"
        echo "$startup_line &" >> "$profile_file"
        echo "Added Parsec startup to .profile"
    fi
    
    echo -e "${GREEN}Auto-start methods enabled${NC}"
}

# Function to test Parsec installation
test_parsec() {
    echo -e "${BLUE}Testing Parsec installation...${NC}"
    
    # Check if Parsec binary exists and is executable
    if [ ! -x "/usr/bin/parsecd" ]; then
        echo -e "${RED}ERROR: Parsec binary not found or not executable${NC}"
        return 1
    fi
    
    # Try to get Parsec version
    local version_output
    if version_output=$(/usr/bin/parsecd --version 2>&1); then
        echo -e "${GREEN}Parsec version: $version_output${NC}"
    else
        echo -e "${YELLOW}Warning: Could not get Parsec version${NC}"
    fi
    
    echo -e "${GREEN}Parsec installation test completed${NC}"
}

# Function to show usage instructions
show_instructions() {
    echo -e "\n${YELLOW}Parsec Setup Complete!${NC}"
    echo "======================"
    echo ""
    echo -e "${GREEN}What was configured:${NC}"
    echo "  ✓ Parsec installed"
    echo "  ✓ Configuration file created"
    echo "  ✓ Systemd user service created"
    echo "  ✓ Desktop autostart entry created"
    echo "  ✓ Startup script created"
    echo "  ✓ Auto-start enabled"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Reboot your system to test auto-start"
    echo "2. Configure Parsec authentication:"
    echo "   - Run: parsecd"
    echo "   - Log in to your Parsec account"
    echo "   - Enable hosting in the app"
    echo ""
    echo -e "${YELLOW}Manual control commands:${NC}"
    echo "  Start:   systemctl --user start parsec"
    echo "  Stop:    systemctl --user stop parsec"
    echo "  Status:  systemctl --user status parsec"
    echo "  Logs:    journalctl --user -u parsec -f"
    echo ""
    echo -e "${YELLOW}Files created:${NC}"
    echo "  Config:     $HOME/.parsec/config.txt"
    echo "  Service:    $HOME/.config/systemd/user/parsec.service"
    echo "  Autostart:  $HOME/.config/autostart/parsec.desktop"
    echo "  Script:     $HOME/.local/bin/start-parsec.sh"
    echo "  Logs:       $HOME/.parsec/startup.log"
}

# Function to check system requirements
check_requirements() {
    echo -e "${BLUE}Checking system requirements...${NC}"
    
    # Check for required packages
    local missing_packages=()
    
    for package in wget curl systemd; do
        if ! command -v "$package" >/dev/null 2>&1; then
            missing_packages+=("$package")
        fi
    done
    
    if [ ${#missing_packages[@]} -gt 0 ]; then
        echo -e "${RED}Missing required packages: ${missing_packages[*]}${NC}"
        echo "Installing missing packages..."
        sudo apt update
        sudo apt install -y "${missing_packages[@]}"
    fi
    
    # Check for desktop environment
    if [ -z "$XDG_CURRENT_DESKTOP" ] && [ -z "$DESKTOP_SESSION" ]; then
        echo -e "${YELLOW}Warning: No desktop environment detected${NC}"
        echo -e "${YELLOW}Parsec requires a graphical desktop environment${NC}"
    fi
    
    echo -e "${GREEN}System requirements check completed${NC}"
}

# Main function
main() {
    check_root
    check_requirements
    install_parsec
    create_parsec_config
    create_systemd_service
    create_desktop_autostart
    create_startup_script
    enable_autostart
    test_parsec
    show_instructions
}

# Handle command line arguments
case "$1" in
    "install")
        main
        ;;
    "start")
        systemctl --user start parsec
        echo -e "${GREEN}Parsec service started${NC}"
        ;;
    "stop")
        systemctl --user stop parsec
        echo -e "${GREEN}Parsec service stopped${NC}"
        ;;
    "status")
        systemctl --user status parsec
        ;;
    "logs")
        journalctl --user -u parsec -f
        ;;
    "uninstall")
        echo -e "${YELLOW}Uninstalling Parsec auto-start...${NC}"
        systemctl --user stop parsec 2>/dev/null || true
        systemctl --user disable parsec 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/parsec.service"
        rm -f "$HOME/.config/autostart/parsec.desktop"
        rm -f "$HOME/.local/bin/start-parsec.sh"
        echo -e "${GREEN}Parsec auto-start uninstalled${NC}"
        ;;
    *)
        echo -e "${YELLOW}Parsec Auto-Start Setup${NC}"
        echo "Usage: $0 {install|start|stop|status|logs|uninstall}"
        echo ""
        echo "Commands:"
        echo "  install    - Install and configure Parsec auto-start"
        echo "  start      - Start Parsec service"
        echo "  stop       - Stop Parsec service"
        echo "  status     - Show Parsec service status"
        echo "  logs       - Show Parsec service logs"
        echo "  uninstall  - Remove Parsec auto-start configuration"
        echo ""
        echo "Run '$0 install' to begin setup"
        ;;
esac