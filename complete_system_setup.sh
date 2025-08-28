#!/bin/bash
# Complete System Setup Script
# Orchestrates HDD formatting, backup automation, auto-login, and Parsec setup

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${PURPLE}========================================${NC}"
echo -e "${PURPLE}    Complete System Setup Script       ${NC}"
echo -e "${PURPLE}========================================${NC}"
echo ""
echo -e "${YELLOW}This script will set up:${NC}"
echo "  1. HDD formatting for Windows 10 compatibility"
echo "  2. Automated backup system"
echo "  3. Auto-login without password"
echo "  4. Parsec auto-start as server"
echo ""

# Function to check if script exists
check_script() {
    local script_name="$1"
    local script_path="$SCRIPT_DIR/$script_name"
    
    if [ ! -f "$script_path" ]; then
        echo -e "${RED}Error: $script_name not found in $SCRIPT_DIR${NC}"
        return 1
    fi
    
    if [ ! -x "$script_path" ]; then
        echo -e "${YELLOW}Making $script_name executable...${NC}"
        chmod +x "$script_path"
    fi
    
    return 0
}

# Function to run with error handling
run_step() {
    local step_name="$1"
    local command="$2"
    
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}Step: $step_name${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    if eval "$command"; then
        echo -e "${GREEN}✓ $step_name completed successfully${NC}"
        return 0
    else
        echo -e "${RED}✗ $step_name failed${NC}"
        return 1
    fi
}

# Function to show system status
show_system_status() {
    echo -e "\n${PURPLE}========================================${NC}"
    echo -e "${PURPLE}           System Status               ${NC}"
    echo -e "${PURPLE}========================================${NC}"
    
    # Check HDD formatting capability
    if command -v mkfs.ntfs >/dev/null 2>&1; then
        echo -e "${GREEN}✓ NTFS formatting tools available${NC}"
    else
        echo -e "${RED}✗ NTFS formatting tools missing${NC}"
    fi
    
    # Check backup tools
    if command -v rsync >/dev/null 2>&1 && command -v cron >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Backup tools available${NC}"
    else
        echo -e "${RED}✗ Backup tools missing${NC}"
    fi
    
    # Check auto-login status
    local current_user="${SUDO_USER:-$(whoami)}"
    if [ -f "/home/$current_user/.autologin_configured" ]; then
        echo -e "${GREEN}✓ Auto-login configured${NC}"
    else
        echo -e "${YELLOW}○ Auto-login not configured${NC}"
    fi
    
    # Check Parsec
    if command -v parsecd >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Parsec installed${NC}"
        if systemctl --user is-enabled parsec >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Parsec auto-start enabled${NC}"
        else
            echo -e "${YELLOW}○ Parsec auto-start not enabled${NC}"
        fi
    else
        echo -e "${YELLOW}○ Parsec not installed${NC}"
    fi
    
    # Show available disks
    echo -e "\n${BLUE}Available storage devices:${NC}"
    lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS
}

# Function to test all components
test_all_components() {
    echo -e "\n${PURPLE}========================================${NC}"
    echo -e "${PURPLE}        Testing All Components         ${NC}"
    echo -e "${PURPLE}========================================${NC}"
    
    local test_results=()
    
    # Test 1: HDD formatting tools
    echo -e "\n${BLUE}Test 1: HDD Formatting Tools${NC}"
    if command -v mkfs.ntfs >/dev/null 2>&1 && command -v parted >/dev/null 2>&1; then
        echo -e "${GREEN}✓ NTFS and partitioning tools available${NC}"
        test_results+=("HDD_TOOLS:PASS")
    else
        echo -e "${RED}✗ Missing HDD formatting tools${NC}"
        test_results+=("HDD_TOOLS:FAIL")
    fi
    
    # Test 2: Backup system
    echo -e "\n${BLUE}Test 2: Backup System${NC}"
    if [ -x "$SCRIPT_DIR/backup_system.sh" ]; then
        # Test backup script syntax
        if bash -n "$SCRIPT_DIR/backup_system.sh"; then
            echo -e "${GREEN}✓ Backup script syntax valid${NC}"
            test_results+=("BACKUP:PASS")
        else
            echo -e "${RED}✗ Backup script has syntax errors${NC}"
            test_results+=("BACKUP:FAIL")
        fi
    else
        echo -e "${RED}✗ Backup script not found${NC}"
        test_results+=("BACKUP:FAIL")
    fi
    
    # Test 3: Auto-login configuration
    echo -e "\n${BLUE}Test 3: Auto-login System${NC}"
    if [ -x "$SCRIPT_DIR/setup_auto_login.sh" ]; then
        # Check if display manager is detectable
        if systemctl list-units --type=service | grep -E "(gdm|lightdm|sddm)" >/dev/null; then
            echo -e "${GREEN}✓ Display manager detected${NC}"
            test_results+=("AUTOLOGIN:PASS")
        else
            echo -e "${YELLOW}○ No display manager detected (may be headless)${NC}"
            test_results+=("AUTOLOGIN:WARN")
        fi
    else
        echo -e "${RED}✗ Auto-login script not found${NC}"
        test_results+=("AUTOLOGIN:FAIL")
    fi
    
    # Test 4: Parsec setup
    echo -e "\n${BLUE}Test 4: Parsec Setup${NC}"
    if [ -x "$SCRIPT_DIR/setup_parsec_autostart.sh" ]; then
        echo -e "${GREEN}✓ Parsec setup script available${NC}"
        if command -v wget >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Download tools available${NC}"
            test_results+=("PARSEC:PASS")
        else
            echo -e "${RED}✗ Missing wget for Parsec download${NC}"
            test_results+=("PARSEC:FAIL")
        fi
    else
        echo -e "${RED}✗ Parsec setup script not found${NC}"
        test_results+=("PARSEC:FAIL")
    fi
    
    # Test 5: System permissions
    echo -e "\n${BLUE}Test 5: System Permissions${NC}"
    if [ "$EUID" -eq 0 ] || sudo -n true 2>/dev/null; then
        echo -e "${GREEN}✓ Root/sudo access available${NC}"
        test_results+=("PERMISSIONS:PASS")
    else
        echo -e "${RED}✗ No root/sudo access${NC}"
        test_results+=("PERMISSIONS:FAIL")
    fi
    
    # Show test summary
    echo -e "\n${PURPLE}Test Summary:${NC}"
    local pass_count=0
    local fail_count=0
    local warn_count=0
    
    for result in "${test_results[@]}"; do
        local test_name="${result%:*}"
        local test_status="${result#*:}"
        
        case "$test_status" in
            "PASS")
                echo -e "${GREEN}✓ $test_name${NC}"
                ((pass_count++))
                ;;
            "FAIL")
                echo -e "${RED}✗ $test_name${NC}"
                ((fail_count++))
                ;;
            "WARN")
                echo -e "${YELLOW}○ $test_name${NC}"
                ((warn_count++))
                ;;
        esac
    done
    
    echo -e "\n${BLUE}Results: ${GREEN}$pass_count passed${NC}, ${RED}$fail_count failed${NC}, ${YELLOW}$warn_count warnings${NC}"
    
    if [ $fail_count -eq 0 ]; then
        echo -e "${GREEN}All critical tests passed! System is ready for setup.${NC}"
        return 0
    else
        echo -e "${RED}Some tests failed. Please resolve issues before proceeding.${NC}"
        return 1
    fi
}

# Function for interactive setup
interactive_setup() {
    echo -e "\n${YELLOW}Interactive Setup Mode${NC}"
    echo "======================"
    
    # Step 1: HDD Formatting
    echo -e "\n${BLUE}Step 1: HDD Formatting${NC}"
    read -p "Do you want to format an HDD for Windows 10? (y/N): " format_hdd
    
    if [[ "$format_hdd" =~ ^[Yy]$ ]]; then
        if ! run_step "HDD Formatting" "$SCRIPT_DIR/format_hdd_for_windows.sh"; then
            echo -e "${RED}HDD formatting failed. Continue anyway? (y/N): ${NC}"
            read -p "" continue_anyway
            if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    fi
    
    # Step 2: Backup System
    echo -e "\n${BLUE}Step 2: Backup System${NC}"
    read -p "Do you want to set up automated backups? (y/N): " setup_backup
    
    if [[ "$setup_backup" =~ ^[Yy]$ ]]; then
        run_step "Backup System Setup" "sudo $SCRIPT_DIR/backup_system.sh setup"
    fi
    
    # Step 3: Auto-login
    echo -e "\n${BLUE}Step 3: Auto-login${NC}"
    read -p "Do you want to enable auto-login without password? (y/N): " setup_autologin
    
    if [[ "$setup_autologin" =~ ^[Yy]$ ]]; then
        run_step "Auto-login Setup" "sudo $SCRIPT_DIR/setup_auto_login.sh"
    fi
    
    # Step 4: Parsec
    echo -e "\n${BLUE}Step 4: Parsec Server${NC}"
    read -p "Do you want to install and auto-start Parsec server? (y/N): " setup_parsec
    
    if [[ "$setup_parsec" =~ ^[Yy]$ ]]; then
        run_step "Parsec Setup" "$SCRIPT_DIR/setup_parsec_autostart.sh install"
    fi
}

# Function for automatic setup
automatic_setup() {
    echo -e "\n${YELLOW}Automatic Setup Mode${NC}"
    echo "===================="
    echo -e "${RED}WARNING: This will configure all components automatically!${NC}"
    read -p "Continue with automatic setup? (y/N): " confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Automatic setup cancelled${NC}"
        return 1
    fi
    
    # Install prerequisites
    run_step "Installing Prerequisites" "sudo apt update && sudo apt install -y wget curl rsync cron ntfs-3g parted gdisk"
    
    # Setup backup system
    run_step "Backup System Setup" "sudo $SCRIPT_DIR/backup_system.sh setup"
    
    # Setup auto-login
    run_step "Auto-login Setup" "sudo $SCRIPT_DIR/setup_auto_login.sh"
    
    # Setup Parsec
    run_step "Parsec Setup" "$SCRIPT_DIR/setup_parsec_autostart.sh install"
    
    echo -e "\n${GREEN}Automatic setup completed!${NC}"
    echo -e "${YELLOW}Note: HDD formatting was skipped in automatic mode for safety.${NC}"
    echo -e "${YELLOW}Run the HDD formatting script manually if needed.${NC}"
}

# Function to show usage
show_usage() {
    echo -e "${YELLOW}Complete System Setup Script${NC}"
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  test        - Test all components and show system status"
    echo "  interactive - Interactive setup with prompts"
    echo "  auto        - Automatic setup (excluding HDD formatting)"
    echo "  status      - Show current system status"
    echo "  help        - Show this help message"
    echo ""
    echo "Individual component scripts:"
    echo "  HDD Format:   ./format_hdd_for_windows.sh"
    echo "  Backup:       ./backup_system.sh"
    echo "  Auto-login:   ./setup_auto_login.sh"
    echo "  Parsec:       ./setup_parsec_autostart.sh"
}

# Main function
main() {
    # Check if all scripts are available
    local scripts=("format_hdd_for_windows.sh" "backup_system.sh" "setup_auto_login.sh" "setup_parsec_autostart.sh")
    local missing_scripts=()
    
    for script in "${scripts[@]}"; do
        if ! check_script "$script"; then
            missing_scripts+=("$script")
        fi
    done
    
    if [ ${#missing_scripts[@]} -gt 0 ]; then
        echo -e "${RED}Missing scripts: ${missing_scripts[*]}${NC}"
        echo -e "${RED}Please ensure all scripts are in the same directory${NC}"
        exit 1
    fi
    
    case "$1" in
        "test")
            test_all_components
            ;;
        "interactive")
            test_all_components && interactive_setup
            ;;
        "auto")
            test_all_components && automatic_setup
            ;;
        "status")
            show_system_status
            ;;
        "help"|"--help"|"-h")
            show_usage
            ;;
        *)
            show_usage
            echo ""
            echo -e "${BLUE}Quick start:${NC}"
            echo "  1. Run: $0 test"
            echo "  2. Run: $0 interactive"
            ;;
    esac
}

# Run main function with all arguments
main "$@"