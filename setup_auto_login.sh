#!/bin/bash
# Script to configure automatic login without password
# Works with GDM3, LightDM, and SDDM display managers

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Auto-Login Setup Script${NC}"
echo "======================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Function to detect display manager
detect_display_manager() {
    if systemctl is-active --quiet gdm3 || systemctl is-enabled --quiet gdm3 2>/dev/null; then
        echo "gdm3"
    elif systemctl is-active --quiet gdm || systemctl is-enabled --quiet gdm 2>/dev/null; then
        echo "gdm"
    elif systemctl is-active --quiet lightdm || systemctl is-enabled --quiet lightdm 2>/dev/null; then
        echo "lightdm"
    elif systemctl is-active --quiet sddm || systemctl is-enabled --quiet sddm 2>/dev/null; then
        echo "sddm"
    elif systemctl is-active --quiet display-manager || systemctl is-enabled --quiet display-manager 2>/dev/null; then
        # Check what display-manager points to
        local dm_service=$(systemctl show -p Id display-manager.service | cut -d= -f2)
        echo "${dm_service%%.service}"
    else
        echo "unknown"
    fi
}

# Function to get current user
get_target_user() {
    local current_user=""
    
    # Try to get the user who called sudo
    if [ -n "$SUDO_USER" ]; then
        current_user="$SUDO_USER"
    else
        # Fallback: get the first non-system user
        current_user=$(awk -F: '$3 >= 1000 && $3 < 65534 { print $1; exit }' /etc/passwd)
    fi
    
    if [ -z "$current_user" ]; then
        echo -e "${RED}Error: Could not determine target user${NC}"
        exit 1
    fi
    
    echo "$current_user"
}

# Function to configure GDM3/GDM auto-login
configure_gdm_autologin() {
    local username="$1"
    local config_file=""
    
    # Determine GDM config file location
    if [ -f "/etc/gdm3/custom.conf" ]; then
        config_file="/etc/gdm3/custom.conf"
    elif [ -f "/etc/gdm/custom.conf" ]; then
        config_file="/etc/gdm/custom.conf"
    else
        echo -e "${RED}Error: GDM configuration file not found${NC}"
        return 1
    fi
    
    echo -e "${BLUE}Configuring GDM auto-login for user: $username${NC}"
    
    # Backup original config
    cp "$config_file" "${config_file}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Check if [daemon] section exists
    if grep -q "^\[daemon\]" "$config_file"; then
        # Section exists, add/modify auto-login settings
        sed -i '/^\[daemon\]/,/^\[/ {
            /^AutomaticLoginEnable=/d
            /^AutomaticLogin=/d
            /^\[daemon\]/a AutomaticLoginEnable=true\nAutomaticLogin='"$username"'
        }' "$config_file"
    else
        # Section doesn't exist, add it
        echo "" >> "$config_file"
        echo "[daemon]" >> "$config_file"
        echo "AutomaticLoginEnable=true" >> "$config_file"
        echo "AutomaticLogin=$username" >> "$config_file"
    fi
    
    echo -e "${GREEN}GDM auto-login configured successfully${NC}"
}

# Function to configure LightDM auto-login
configure_lightdm_autologin() {
    local username="$1"
    local config_file="/etc/lightdm/lightdm.conf"
    
    echo -e "${BLUE}Configuring LightDM auto-login for user: $username${NC}"
    
    # Create config file if it doesn't exist
    if [ ! -f "$config_file" ]; then
        mkdir -p "$(dirname "$config_file")"
        touch "$config_file"
    fi
    
    # Backup original config
    cp "$config_file" "${config_file}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Check if [Seat:*] section exists
    if grep -q "^\[Seat:\*\]" "$config_file"; then
        # Section exists, add/modify auto-login settings
        sed -i '/^\[Seat:\*\]/,/^\[/ {
            /^autologin-user=/d
            /^autologin-user-timeout=/d
            /^\[Seat:\*\]/a autologin-user='"$username"'\nautologin-user-timeout=0
        }' "$config_file"
    else
        # Section doesn't exist, add it
        echo "" >> "$config_file"
        echo "[Seat:*]" >> "$config_file"
        echo "autologin-user=$username" >> "$config_file"
        echo "autologin-user-timeout=0" >> "$config_file"
    fi
    
    echo -e "${GREEN}LightDM auto-login configured successfully${NC}"
}

# Function to configure SDDM auto-login
configure_sddm_autologin() {
    local username="$1"
    local config_file="/etc/sddm.conf"
    
    echo -e "${BLUE}Configuring SDDM auto-login for user: $username${NC}"
    
    # Create config file if it doesn't exist
    if [ ! -f "$config_file" ]; then
        touch "$config_file"
    fi
    
    # Backup original config
    cp "$config_file" "${config_file}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Check if [Autologin] section exists
    if grep -q "^\[Autologin\]" "$config_file"; then
        # Section exists, add/modify auto-login settings
        sed -i '/^\[Autologin\]/,/^\[/ {
            /^User=/d
            /^Session=/d
            /^\[Autologin\]/a User='"$username"'\nSession=plasma.desktop
        }' "$config_file"
    else
        # Section doesn't exist, add it
        echo "" >> "$config_file"
        echo "[Autologin]" >> "$config_file"
        echo "User=$username" >> "$config_file"
        echo "Session=plasma.desktop" >> "$config_file"
    fi
    
    echo -e "${GREEN}SDDM auto-login configured successfully${NC}"
}

# Function to remove password requirement
configure_passwordless_sudo() {
    local username="$1"
    local sudoers_file="/etc/sudoers.d/autologin-$username"
    
    echo -e "${BLUE}Configuring passwordless sudo for user: $username${NC}"
    
    # Create sudoers entry for passwordless sudo
    echo "$username ALL=(ALL) NOPASSWD:ALL" > "$sudoers_file"
    chmod 440 "$sudoers_file"
    
    # Validate sudoers file
    if visudo -c -f "$sudoers_file"; then
        echo -e "${GREEN}Passwordless sudo configured successfully${NC}"
    else
        echo -e "${RED}Error: Invalid sudoers configuration${NC}"
        rm -f "$sudoers_file"
        return 1
    fi
}

# Function to disable password for user account
disable_user_password() {
    local username="$1"
    
    echo -e "${BLUE}Disabling password for user: $username${NC}"
    
    # Remove password but keep account enabled
    passwd -d "$username"
    
    echo -e "${GREEN}Password disabled for user $username${NC}"
}

# Function to configure PAM for passwordless login
configure_pam_passwordless() {
    local username="$1"
    
    echo -e "${BLUE}Configuring PAM for passwordless login${NC}"
    
    # Backup original PAM files
    for pam_file in /etc/pam.d/gdm-password /etc/pam.d/lightdm /etc/pam.d/login; do
        if [ -f "$pam_file" ]; then
            cp "$pam_file" "${pam_file}.backup.$(date +%Y%m%d_%H%M%S)"
        fi
    done
    
    # Note: We're not modifying PAM files as removing passwords via passwd -d is safer
    echo -e "${GREEN}PAM configuration reviewed${NC}"
}

# Main setup function
main() {
    echo -e "${YELLOW}Starting auto-login setup...${NC}"
    
    # Get target user
    local target_user=$(get_target_user)
    echo -e "${BLUE}Target user: $target_user${NC}"
    
    # Detect display manager
    local dm=$(detect_display_manager)
    echo -e "${BLUE}Detected display manager: $dm${NC}"
    
    # Confirm with user
    echo -e "\n${YELLOW}This will configure automatic login for user '$target_user'${NC}"
    echo -e "${YELLOW}and disable password requirements.${NC}"
    echo -e "${RED}WARNING: This reduces system security!${NC}"
    read -p "Continue? (y/N): " confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Setup cancelled${NC}"
        exit 0
    fi
    
    # Configure display manager auto-login
    case "$dm" in
        "gdm3"|"gdm")
            configure_gdm_autologin "$target_user"
            ;;
        "lightdm")
            configure_lightdm_autologin "$target_user"
            ;;
        "sddm")
            configure_sddm_autologin "$target_user"
            ;;
        *)
            echo -e "${YELLOW}Warning: Unsupported or unknown display manager: $dm${NC}"
            echo -e "${YELLOW}Manual configuration may be required${NC}"
            ;;
    esac
    
    # Configure passwordless access
    configure_passwordless_sudo "$target_user"
    disable_user_password "$target_user"
    configure_pam_passwordless "$target_user"
    
    # Create status file
    echo "Auto-login configured on $(date)" > "/home/$target_user/.autologin_configured"
    echo "Display Manager: $dm" >> "/home/$target_user/.autologin_configured"
    echo "User: $target_user" >> "/home/$target_user/.autologin_configured"
    chown "$target_user:$target_user" "/home/$target_user/.autologin_configured"
    
    echo -e "\n${GREEN}Auto-login setup completed successfully!${NC}"
    echo -e "${GREEN}The system will automatically log in as '$target_user' on next reboot.${NC}"
    echo -e "\n${YELLOW}To revert changes, restore the backup files:${NC}"
    echo "  - Display manager config backups in /etc/"
    echo "  - Remove /etc/sudoers.d/autologin-$target_user"
    echo "  - Reset password: sudo passwd $target_user"
    
    echo -e "\n${BLUE}Restart display manager or reboot to test auto-login${NC}"
}

# Handle command line arguments
case "$1" in
    "revert")
        echo -e "${YELLOW}Auto-login revert functionality${NC}"
        echo "To manually revert auto-login:"
        echo "1. Restore display manager config from backup"
        echo "2. Remove /etc/sudoers.d/autologin-* files"
        echo "3. Reset user password with: passwd [username]"
        ;;
    "status")
        target_user=$(get_target_user)
        if [ -f "/home/$target_user/.autologin_configured" ]; then
            echo -e "${GREEN}Auto-login is configured${NC}"
            cat "/home/$target_user/.autologin_configured"
        else
            echo -e "${YELLOW}Auto-login is not configured${NC}"
        fi
        ;;
    *)
        main
        ;;
esac