# Complete System Setup for Windows 10 HDD, Backups, Auto-login, and Parsec

This collection of scripts automates the setup of a Linux system for:
1. **HDD formatting** with NTFS filesystem for Windows 10 compatibility
2. **Automated backup system** for frequent file backups
3. **Auto-login configuration** without password requirement
4. **Parsec server setup** with automatic startup

## Quick Start

1. **Test your system**:
   ```bash
   sudo ./complete_system_setup.sh test
   ```

2. **Interactive setup** (recommended for first-time users):
   ```bash
   sudo ./complete_system_setup.sh interactive
   ```

3. **Automatic setup** (for experienced users):
   ```bash
   sudo ./complete_system_setup.sh auto
   ```

## Individual Scripts

### 1. HDD Formatting (`format_hdd_for_windows.sh`)

Formats a hard drive with NTFS filesystem for Windows 10 compatibility.

**Features:**
- Interactive drive selection with safety checks
- Creates GPT partition table
- Formats with NTFS filesystem
- Sets appropriate partition flags
- Provides mounting instructions

**Usage:**
```bash
sudo ./format_hdd_for_windows.sh
```

**⚠️ WARNING:** This will completely erase the selected drive!

### 2. Automated Backup System (`backup_system.sh`)

Creates a comprehensive backup solution with scheduling and retention.

**Features:**
- Configurable source directories and destinations
- Daily, weekly, and monthly backup schedules
- Automatic cleanup of old backups
- Integrity verification with checksums
- Comprehensive logging
- Exclude patterns for unwanted files

**Usage:**
```bash
# Setup automated backups
sudo ./backup_system.sh setup

# Manual backup
./backup_system.sh manual

# List available backups
./backup_system.sh list

# Verify backup integrity
./backup_system.sh verify <backup_directory>
```

**Default backup schedule:**
- Daily backups at 2:00 AM
- Weekly backups on Sundays at 3:00 AM  
- Monthly backups on the 1st at 4:00 AM

**Configuration:** `/etc/backup_config.conf`

### 3. Auto-Login Setup (`setup_auto_login.sh`)

Configures automatic login without password for seamless system access.

**Features:**
- Supports GDM3, LightDM, and SDDM display managers
- Automatic display manager detection
- Passwordless sudo configuration
- Safety backups of configuration files
- Status checking and revert options

**Usage:**
```bash
# Setup auto-login
sudo ./setup_auto_login.sh

# Check status
sudo ./setup_auto_login.sh status

# View revert instructions
sudo ./setup_auto_login.sh revert
```

**⚠️ WARNING:** This reduces system security by removing password requirements!

### 4. Parsec Auto-Start (`setup_parsec_autostart.sh`)

Installs Parsec and configures it to start automatically as a server.

**Features:**
- Downloads and installs Parsec for Linux
- Creates systemd user service
- Desktop autostart entry
- Startup script with error handling
- Service management commands
- Comprehensive logging

**Usage:**
```bash
# Install and configure Parsec
./setup_parsec_autostart.sh install

# Control Parsec service
./setup_parsec_autostart.sh start
./setup_parsec_autostart.sh stop
./setup_parsec_autostart.sh status
./setup_parsec_autostart.sh logs

# Uninstall auto-start
./setup_parsec_autostart.sh uninstall
```

## System Requirements

### Minimum Requirements:
- Linux distribution (Ubuntu/Debian recommended)
- Root/sudo access
- Internet connection (for Parsec download)
- Desktop environment (for Parsec and auto-login)

### Required Packages:
The scripts will automatically install these if missing:
- `ntfs-3g` - NTFS filesystem support
- `parted` - Disk partitioning
- `rsync` - File synchronization
- `cron` - Task scheduling
- `wget/curl` - File downloading
- `systemd` - Service management

## File Locations

### Configuration Files:
- **Backup config:** `/etc/backup_config.conf`
- **Parsec config:** `~/.parsec/config.txt`
- **Auto-login status:** `~/.autologin_configured`

### Service Files:
- **Parsec systemd service:** `~/.config/systemd/user/parsec.service`
- **Backup cron jobs:** Added to user's crontab
- **Autostart entries:** `~/.config/autostart/parsec.desktop`

### Log Files:
- **Backup logs:** `/var/log/backup_system.log`
- **Parsec logs:** `~/.parsec/startup.log`
- **Parsec service logs:** `~/.parsec/parsec.log`

## Security Considerations

**Auto-login setup removes password requirements, which:**
- ✅ Provides seamless system access
- ❌ Reduces physical security
- ❌ Removes authentication barriers

**Recommendations:**
- Only use on trusted, physically secure systems
- Consider disk encryption for additional security
- Regularly review and update system configurations

## Troubleshooting

### Common Issues:

1. **HDD not detected:**
   - Check if drive is properly connected
   - Verify drive appears in `lsblk` output
   - Ensure sufficient permissions

2. **Backup fails:**
   - Check destination directory permissions
   - Verify sufficient disk space
   - Review logs in `/var/log/backup_system.log`

3. **Auto-login not working:**
   - Verify display manager compatibility
   - Check service status: `systemctl status <display-manager>`
   - Review backup configuration files

4. **Parsec won't start:**
   - Check service status: `systemctl --user status parsec`
   - Review logs: `journalctl --user -u parsec`
   - Ensure X11/Wayland session is available

### Log Locations:
- **System logs:** `journalctl`
- **Backup logs:** `/var/log/backup_system.log`
- **Parsec logs:** `~/.parsec/startup.log`

## Manual Configuration

### Backup System:
Edit `/etc/backup_config.conf` to customize:
- Source directories
- Backup destination
- Exclude patterns
- Retention policies

### Parsec Settings:
Edit `~/.parsec/config.txt` to modify:
- Video quality settings
- Network configuration
- Security settings

## Uninstalling

### Remove Auto-login:
```bash
# Restore display manager config from backup
sudo cp /etc/gdm3/custom.conf.backup.* /etc/gdm3/custom.conf
sudo rm /etc/sudoers.d/autologin-*
sudo passwd <username>  # Reset password
```

### Remove Backup System:
```bash
sudo crontab -l | grep -v backup_system.sh | sudo crontab -
sudo rm /etc/backup_config.conf
sudo rm /var/log/backup_system.log
```

### Remove Parsec Auto-start:
```bash
./setup_parsec_autostart.sh uninstall
```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review log files for error messages
3. Ensure all system requirements are met
4. Test individual components before running complete setup

## License

These scripts are provided as-is for educational and personal use. Use at your own risk and always backup important data before making system changes.