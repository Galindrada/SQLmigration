#!/bin/bash
# Automated backup system for frequent file backups
# This script can be run manually or scheduled via cron

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration file
CONFIG_FILE="/etc/backup_config.conf"
LOG_FILE="/var/log/backup_system.log"

# Default configuration
DEFAULT_SOURCE_DIRS=(
    "$HOME/Documents"
    "$HOME/Desktop"
    "$HOME/Pictures"
    "$HOME/Downloads"
    "/etc"
)

DEFAULT_BACKUP_DEST="/mnt/backup_drive"
DEFAULT_EXCLUDE_PATTERNS=(
    "*.tmp"
    "*.temp"
    "*~"
    "*.log"
    ".cache/*"
    ".trash/*"
    "node_modules/*"
)

# Function to create default config
create_default_config() {
    echo "# Backup System Configuration" > "$CONFIG_FILE"
    echo "# Directories to backup (one per line)" >> "$CONFIG_FILE"
    echo "SOURCE_DIRS=(" >> "$CONFIG_FILE"
    for dir in "${DEFAULT_SOURCE_DIRS[@]}"; do
        echo "    \"$dir\"" >> "$CONFIG_FILE"
    done
    echo ")" >> "$CONFIG_FILE"
    echo "" >> "$CONFIG_FILE"
    echo "# Backup destination" >> "$CONFIG_FILE"
    echo "BACKUP_DEST=\"$DEFAULT_BACKUP_DEST\"" >> "$CONFIG_FILE"
    echo "" >> "$CONFIG_FILE"
    echo "# Exclude patterns" >> "$CONFIG_FILE"
    echo "EXCLUDE_PATTERNS=(" >> "$CONFIG_FILE"
    for pattern in "${DEFAULT_EXCLUDE_PATTERNS[@]}"; do
        echo "    \"$pattern\"" >> "$CONFIG_FILE"
    done
    echo ")" >> "$CONFIG_FILE"
    echo "" >> "$CONFIG_FILE"
    echo "# Retention settings (days)" >> "$CONFIG_FILE"
    echo "KEEP_DAILY=7" >> "$CONFIG_FILE"
    echo "KEEP_WEEKLY=4" >> "$CONFIG_FILE"
    echo "KEEP_MONTHLY=12" >> "$CONFIG_FILE"
}

# Function to log messages
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    echo -e "${BLUE}[$timestamp]${NC} $message"
}

# Function to create backup
perform_backup() {
    local backup_type="$1"  # daily, weekly, monthly, or manual
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_dir="$BACKUP_DEST/${backup_type}_${timestamp}"
    
    log_message "INFO" "Starting $backup_type backup to $backup_dir"
    
    # Create backup directory
    mkdir -p "$backup_dir"
    
    # Build rsync exclude options
    local exclude_opts=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        exclude_opts="$exclude_opts --exclude=$pattern"
    done
    
    # Perform backup for each source directory
    local total_files=0
    local total_size=0
    
    for source_dir in "${SOURCE_DIRS[@]}"; do
        if [ -d "$source_dir" ]; then
            log_message "INFO" "Backing up $source_dir"
            
            # Create destination subdirectory
            local dest_subdir="$backup_dir/$(basename "$source_dir")"
            
            # Use rsync for efficient backup
            rsync -av --stats --human-readable $exclude_opts "$source_dir/" "$dest_subdir/" 2>&1 | \
            while IFS= read -r line; do
                if [[ "$line" =~ ^Number\ of\ files:.*\ ([0-9,]+) ]]; then
                    files="${BASH_REMATCH[1]//,/}"
                    total_files=$((total_files + files))
                elif [[ "$line" =~ ^Total\ file\ size:.*\ ([0-9,]+)\ bytes ]]; then
                    size="${BASH_REMATCH[1]//,/}"
                    total_size=$((total_size + size))
                fi
            done
        else
            log_message "WARN" "Source directory $source_dir does not exist, skipping"
        fi
    done
    
    # Create backup manifest
    echo "Backup Type: $backup_type" > "$backup_dir/backup_manifest.txt"
    echo "Timestamp: $(date)" >> "$backup_dir/backup_manifest.txt"
    echo "Hostname: $(hostname)" >> "$backup_dir/backup_manifest.txt"
    echo "User: $(whoami)" >> "$backup_dir/backup_manifest.txt"
    echo "Source Directories:" >> "$backup_dir/backup_manifest.txt"
    for dir in "${SOURCE_DIRS[@]}"; do
        echo "  - $dir" >> "$backup_dir/backup_manifest.txt"
    done
    
    # Create checksum file for integrity verification
    find "$backup_dir" -type f ! -name "*.md5" -exec md5sum {} \; > "$backup_dir/checksums.md5"
    
    log_message "INFO" "Backup completed successfully"
    log_message "INFO" "Backup location: $backup_dir"
    
    # Clean old backups
    cleanup_old_backups "$backup_type"
}

# Function to cleanup old backups
cleanup_old_backups() {
    local backup_type="$1"
    local keep_days
    
    case "$backup_type" in
        "daily")   keep_days="$KEEP_DAILY" ;;
        "weekly")  keep_days="$KEEP_WEEKLY" ;;
        "monthly") keep_days="$KEEP_MONTHLY" ;;
        *)         return ;;
    esac
    
    log_message "INFO" "Cleaning up old $backup_type backups (keeping $keep_days)"
    
    # Find and remove old backup directories
    find "$BACKUP_DEST" -maxdepth 1 -type d -name "${backup_type}_*" -mtime +"$keep_days" -exec rm -rf {} \; 2>/dev/null || true
}

# Function to verify backup integrity
verify_backup() {
    local backup_dir="$1"
    
    if [ ! -f "$backup_dir/checksums.md5" ]; then
        log_message "ERROR" "Checksum file not found in $backup_dir"
        return 1
    fi
    
    log_message "INFO" "Verifying backup integrity for $backup_dir"
    
    cd "$backup_dir"
    if md5sum -c checksums.md5 >/dev/null 2>&1; then
        log_message "INFO" "Backup integrity verification passed"
        return 0
    else
        log_message "ERROR" "Backup integrity verification failed"
        return 1
    fi
}

# Function to setup backup schedule
setup_schedule() {
    log_message "INFO" "Setting up backup schedule"
    
    # Create cron entries
    (crontab -l 2>/dev/null || echo "") | grep -v "backup_system.sh" > /tmp/crontab_new
    
    # Daily backup at 2 AM
    echo "0 2 * * * $0 daily >/dev/null 2>&1" >> /tmp/crontab_new
    
    # Weekly backup on Sundays at 3 AM
    echo "0 3 * * 0 $0 weekly >/dev/null 2>&1" >> /tmp/crontab_new
    
    # Monthly backup on the 1st at 4 AM
    echo "0 4 1 * * $0 monthly >/dev/null 2>&1" >> /tmp/crontab_new
    
    crontab /tmp/crontab_new
    rm /tmp/crontab_new
    
    log_message "INFO" "Backup schedule installed"
    echo -e "${GREEN}Backup schedule installed:${NC}"
    echo "  - Daily backups at 2:00 AM"
    echo "  - Weekly backups on Sundays at 3:00 AM"
    echo "  - Monthly backups on the 1st at 4:00 AM"
}

# Main script logic
main() {
    # Ensure running as root for system-wide setup
    if [ "$EUID" -ne 0 ] && [ "$1" != "manual" ]; then
        echo -e "${RED}Please run as root (use sudo) for system-wide backup setup${NC}"
        exit 1
    fi
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # Load or create configuration
    if [ ! -f "$CONFIG_FILE" ]; then
        log_message "INFO" "Creating default configuration file"
        create_default_config
        echo -e "${YELLOW}Created default configuration at $CONFIG_FILE${NC}"
        echo -e "${YELLOW}Please review and modify as needed before running backups${NC}"
    fi
    
    # Source configuration
    source "$CONFIG_FILE"
    
    # Ensure backup destination exists
    if [ ! -d "$BACKUP_DEST" ]; then
        log_message "INFO" "Creating backup destination directory"
        mkdir -p "$BACKUP_DEST"
    fi
    
    case "$1" in
        "daily"|"weekly"|"monthly")
            perform_backup "$1"
            ;;
        "manual")
            perform_backup "manual"
            ;;
        "setup")
            setup_schedule
            ;;
        "verify")
            if [ -z "$2" ]; then
                echo -e "${RED}Usage: $0 verify <backup_directory>${NC}"
                exit 1
            fi
            verify_backup "$2"
            ;;
        "list")
            echo -e "${YELLOW}Available backups:${NC}"
            ls -la "$BACKUP_DEST"
            ;;
        *)
            echo -e "${YELLOW}Automated Backup System${NC}"
            echo "========================"
            echo "Usage: $0 {daily|weekly|monthly|manual|setup|verify|list}"
            echo ""
            echo "Commands:"
            echo "  daily    - Perform daily backup"
            echo "  weekly   - Perform weekly backup"
            echo "  monthly  - Perform monthly backup"
            echo "  manual   - Perform manual backup"
            echo "  setup    - Install automatic backup schedule"
            echo "  verify   - Verify backup integrity"
            echo "  list     - List available backups"
            echo ""
            echo "Configuration file: $CONFIG_FILE"
            echo "Log file: $LOG_FILE"
            ;;
    esac
}

# Run main function with all arguments
main "$@"